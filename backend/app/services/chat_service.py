"""对话服务：RAG 问答主流程。

流程：检索上下文 → 拼装 Prompt → LLM 生成 → 构建引用 → 持久化历史。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.chat import ChatHistory, ChatSession
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.rag import pipeline

logger = logging.getLogger(__name__)


async def answer_question(
    session: AsyncSession, user: User, payload: ChatRequest
) -> ChatResponse:
    """执行一次 RAG 问答，并持久化到历史会话。"""
    # 1. 获取或创建会话
    if payload.session_id:
        db_session = await session.get(ChatSession, payload.session_id)
        if db_session is None or db_session.user_id != user.id:
            db_session = ChatSession(user_id=user.id, title=_make_title(payload.question))
            session.add(db_session)
    else:
        db_session = ChatSession(user_id=user.id, title=_make_title(payload.question))
        session.add(db_session)

    # 保存用户消息（先 flush 拿到 session_id）
    user_msg = ChatHistory(
        session_id=0,  # 占位，flush 后回填
        user_id=user.id,
        role="user",
        content=payload.question,
        sources=None,
    )
    session.add(user_msg)
    await session.flush()
    user_msg.session_id = db_session.id or user_msg.session_id

    # 2. RAG 检索
    retrieved = pipeline.retrieve_context(payload.question, top_k=payload.top_k)
    context = pipeline.build_context(retrieved)
    sources = pipeline.build_sources(retrieved)

    # 3. 生成
    if not retrieved:
        answer = "抱歉，知识库中暂未检索到与该问题相关的资料，请检查是否已上传相关文档。"
    else:
        # 加载历史（最近若干条）
        history_msgs = await _load_history(session, db_session, user.id)
        messages = pipeline.build_prompt_with_history(payload.question, context, history_msgs)
        answer = await pipeline.generate(messages)

    # 4. 持久化回答
    assistant_msg = ChatHistory(
        session_id=db_session.id,
        user_id=user.id,
        role="assistant",
        content=answer,
        sources=sources,
    )
    session.add(assistant_msg)
    db_session.title = _make_title(payload.question)
    await session.commit()

    return ChatResponse(
        session_id=db_session.id,
        answer=answer,
        sources=[ChatSource(**s) for s in sources],
    )


def _make_title(question: str) -> str:
    """根据首个问题生成会话标题。"""
    q = question.strip().replace("\n", " ")
    return q[:30] if len(q) > 30 else q or "新对话"


async def _load_history(
    session: AsyncSession, db_session: ChatSession, user_id: int
) -> list[dict]:
    """加载会话历史成 (role, content) 列表。

    显式查询而非访问关系，避免 async 下 relationship 懒加载触发 MissingGreenlet。
    """
    result = await session.execute(
        select(ChatHistory)
        .where(ChatHistory.session_id == db_session.id)
        .order_by(ChatHistory.id)
    )
    rows = result.scalars().all()
    return [
        {"role": m.role, "content": m.content}
        for m in rows
        if m.role in {"user", "assistant"}
    ][-6:]


# ---------------------------------------------------------------------------
# 流式问答（SSE）
# ---------------------------------------------------------------------------

async def stream_answer_question(
    user_id: int,
    question: str,
    session_id: int | None = None,
    top_k: int = 5,
) -> AsyncIterator[dict]:
    """流式问答生成器，逐段产出 SSE 事件。

    说明：使用独立会话处理持久化，不依赖请求级 session，避免流式场景下
    依赖会话提前关闭的问题。事件类型：
      - {"type": "start", "session_id": ...}
      - {"type": "token", "content": ...}
      - {"type": "sources", "sources": [...]}
      - {"type": "done"}
    """
    from app.services.rag.llm import get_llm

    # 1. 检索（在流式前先完成，让用户先看到引用）
    retrieved = pipeline.retrieve_context(question, top_k=top_k)
    context = pipeline.build_context(retrieved)
    sources = pipeline.build_sources(retrieved)

    async with AsyncSessionLocal() as session:
        # 2. 获取或创建会话
        if session_id:
            db_session = await session.get(ChatSession, session_id)
            if db_session is None or db_session.user_id != user_id:
                db_session = ChatSession(user_id=user_id, title=_make_title(question))
                session.add(db_session)
        else:
            db_session = ChatSession(user_id=user_id, title=_make_title(question))
            session.add(db_session)
        await session.flush()

        # 3. 持久化用户消息
        session.add(
            ChatHistory(
                session_id=db_session.id,
                user_id=user_id,
                role="user",
                content=question,
            )
        )
        await session.commit()

        yield {"type": "start", "session_id": db_session.id}

        # 4. 生成回答
        if not retrieved:
            answer = "抱歉，知识库中暂未检索到与该问题相关的资料，请检查是否已上传相关文档。"
            yield {"type": "token", "content": answer}
        else:
            history_msgs = await _load_history(session, db_session, user_id)
            messages = pipeline.build_prompt_with_history(question, context, history_msgs)
            answer_parts: list[str] = []
            async for chunk in get_llm().astream(messages):
                content = getattr(chunk, "content", "") or ""
                if content:
                    answer_parts.append(content)
                    yield {"type": "token", "content": content}
            answer = "".join(answer_parts)

        # 5. 持久化回答（含引用）
        session.add(
            ChatHistory(
                session_id=db_session.id,
                user_id=user_id,
                role="assistant",
                content=answer or "（无回答）",
                sources=sources,
            )
        )
        db_session.title = _make_title(question)
        await session.commit()

        yield {"type": "sources", "sources": sources}
        yield {"type": "done"}