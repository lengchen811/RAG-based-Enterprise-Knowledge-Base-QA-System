"""对话路由：新建会话、历史会话、发起问答。"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.responses import ok
from app.database import get_session
from app.models.chat import ChatSession
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionOut,
)
from app.services.chat_service import answer_question, stream_answer_question

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/sessions")
async def create_session(
    payload: SessionCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """新建一个对话会话。"""
    db_session = ChatSession(user_id=user.id, title=payload.title or "新对话")
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)
    return ok(SessionOut.model_validate(db_session).model_dump(mode="json"))


@router.get("/sessions")
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """列出当前用户的会话（按更新时间倒序）。"""
    result = await session.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    items = result.scalars().all()
    return ok(
        {
            "total": len(items),
            "items": [SessionOut.model_validate(s).model_dump(mode="json") for s in items],
        }
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除一个会话及其全部历史消息。"""
    db_session = await session.get(ChatSession, session_id)
    if db_session is None or db_session.user_id != user.id:
        raise NotFoundError("会话不存在")
    await session.delete(db_session)
    await session.commit()
    return ok({"deleted": True, "id": session_id})


@router.post("/ask")
async def ask(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """发起一问：RAG 检索 + 生成，返回答案与引用来源，并持久化历史。"""
    result = await answer_question(session=session, user=user, payload=payload)
    return ok(result.model_dump(mode="json"))


@router.post("/stream")
async def ask_stream(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """流式问答（SSE）：逐 token 返回答案，最后附引用来源。"""

    async def event_stream():
        async for evt in stream_answer_question(
            user_id=user.id,
            question=payload.question,
            session_id=payload.session_id,
            top_k=payload.top_k,
        ):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """读取一个会话的全部消息（用于前端恢复历史）。"""
    db_session = await session.get(ChatSession, session_id)
    if db_session is None or db_session.user_id != user.id:
        raise NotFoundError("会话不存在")
    # 显式查询，避免 async 下 relationship 懒加载触发 MissingGreenlet
    from app.models.chat import ChatHistory

    result = await session.execute(
        select(ChatHistory)
        .where(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.id)
    )
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "sources": m.sources,
            "created_at": m.created_at.isoformat(),
        }
        for m in result.scalars().all()
    ]
    return ok({"session_id": session_id, "messages": messages})