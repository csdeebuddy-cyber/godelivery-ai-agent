from fastapi import APIRouter

from app.api.v1.endpoints import chat, health, integrations, knowledge, live

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health")
api_router.include_router(integrations.router)
api_router.include_router(knowledge.router)
api_router.include_router(chat.router)
api_router.include_router(live.router)
