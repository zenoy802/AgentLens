from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(connections_router)
api_router.include_router(health_router)

__all__ = ["api_router"]
