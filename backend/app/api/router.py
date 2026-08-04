"""聚合所有子路由为统一 API 路由。"""
from fastapi import APIRouter

from app.api import chat, documents
from app.api import auth

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)