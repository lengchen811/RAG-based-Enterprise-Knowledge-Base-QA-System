"""API 认证与文档上传接口测试。"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.database import init_db


@pytest.fixture(scope="module")
def client():
    from app.main import app

    asyncio.run(init_db())
    with TestClient(app) as c:
        yield c


def _register(client, username="tester", password="secret123"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


def test_register_and_login(client):
    tok = _register(client, "alice")
    assert tok
    # 登录
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["data"]["user"]["username"] == "alice"


def test_duplicate_register_rejected(client):
    _register(client, "bob")
    r = client.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
    assert r.status_code == 409
    assert r.json()["code"] == 409


def test_wrong_password_rejected(client):
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_token(client):
    tok = _register(client, "carol")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "carol"


def test_upload_unsupported_type_rejected(client):
    tok = _register(client, "dave")
    r = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {tok}"},
        files={"file": ("evil.exe", b"not-a-doc", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_initiates_document(client):
    tok = _register(client, "erin")
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    r = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {tok}"},
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    doc = r.json()["data"]
    assert doc["status"] == "PENDING"
    assert doc["filename"] == "doc.pdf"