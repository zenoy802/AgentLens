from fastapi import APIRouter

from app.api.connections import router as connections_router
from app.api.execute import router as execute_router
from app.api.health import router as health_router
from app.api.queries import router as queries_router
from app.api.query_history import router as query_history_router

api_router = APIRouter()
api_router.include_router(connections_router)
api_router.include_router(execute_router)
api_router.include_router(health_router)
api_router.include_router(queries_router)
api_router.include_router(query_history_router)

__all__ = ["api_router"]
