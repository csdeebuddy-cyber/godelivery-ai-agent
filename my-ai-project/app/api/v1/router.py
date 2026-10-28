from fastapi import APIRouter

from app.api.v1.endpoints import chat, health, integrations, knowledge, live, member, site, widget
from app.api.admin import api_router as admin_api_router

api_router = APIRouter()
api_router.include_router(admin_api_router)
api_router.include_router(health.router, prefix="/health")
api_router.include_router(integrations.router)
api_router.include_router(knowledge.router)
api_router.include_router(site.router)
api_router.include_router(member.router)
api_router.include_router(chat.router)
api_router.include_router(live.router)
api_router.include_router(widget.router)
