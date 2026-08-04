"""对话服务测试：问答、持久化、流式。"""
import asyncio

import pytest

from app.database import AsyncSessionLocal, init_db
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.chat_service import answer_question, stream_answer_question
from app.services.rag.splitter import build_child_store, build_parent_lookup, split_markdown
from app.services.rag.vectorstore import get_vector_store

SAMPLE = """# 员工手册
## 休假制度
员工入职满一年后，每年享有5天带薪年假。
"""


@pytest.fixture(scope="module", autouse=True)
def _setup():
    asyncio.run(init_db())
    # 预置向量库
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    vs = get_vector_store()
    vs.add_children(build_child_store(parents), build_parent_lookup(parents))
    vs.save()


@pytest.fixture()
async def user():
    import uuid

    async with AsyncSessionLocal() as s:
        u = User(username=f"chatter_{uuid.uuid4().hex[:8]}", password_hash="x")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


@pytest.mark.asyncio
async def test_answer_question_persists(user, mock_llm):
    async with AsyncSessionLocal() as s:
        u = await s.get(User, user.id)
        resp = await answer_question(s, u, ChatRequest(question="年假有几天？"))
        assert resp.answer
        assert resp.session_id
        assert resp.sources is not None


@pytest.mark.asyncio
async def test_stream_answer_events(user, mock_llm):
    events = []
    async for evt in stream_answer_question(user_id=user.id, question="年假几天？"):
        events.append(evt)
    types = [e["type"] for e in events]
    assert "start" in types
    assert "token" in types
    assert "sources" in types
    assert "done" in types
    # 拼接 token
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert text
    assert events[0]["type"] == "start"