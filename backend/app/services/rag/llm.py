"""大模型生成：基于通义千问（DashScope）。

通过 LangChain 的 ChatTongyi 集成，支持流式输出。模型工厂抽象，便于替换。
Prompts 的拼装统一在 pipeline 模块完成。
"""
from __future__ import annotations

from functools import lru_cache

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import BaseMessage, BaseMessageChunk

from app.config import settings


@lru_cache
def get_llm() -> ChatTongyi:
    """返回缓存的大模型实例（单例）。"""
    return ChatTongyi(
        model=settings.LLM_MODEL,
        dashscope_api_key=settings.DASHSCOPE_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        streaming=True,
    )


async def generate_answer(messages: list[BaseMessage]) -> str:
    """非流式生成完整回答。"""
    llm = get_llm()
    resp = await llm.ainvoke(messages)
    return resp.content if isinstance(resp.content, str) else str(resp.content)


async def stream_answer(messages: list[BaseMessage]) -> list[BaseMessageChunk]:
    """流式生成回答，返回 chunk 序列。"""
    llm = get_llm()
    return [chunk async for chunk in llm.astream(messages)]


def chunks_to_text(chunks: list[BaseMessageChunk]) -> str:
    """将流式 chunk 合并为完整文本。"""
    return "".join(getattr(c, "content", "") or "" for c in chunks)