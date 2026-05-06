from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.connections import router as connections_router
from app.api.execute import router as execute_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.label_schemas import router as label_schemas_router
from app.api.queries import router as queries_router
from app.api.query_history import router as query_history_router
from app.api.render_rules import router as render_rules_router
from app.api.trajectories import router as trajectories_router
from app.api.view_configs import router as view_configs_router

api_router = APIRouter()
api_router.include_router(admin_router)
api_router.include_router(connections_router)
api_router.include_router(execute_router)
api_router.include_router(export_router)
api_router.include_router(health_router)
api_router.include_router(label_schemas_router)
api_router.include_router(queries_router)
api_router.include_router(query_history_router)
api_router.include_router(render_rules_router)
api_router.include_router(trajectories_router)
api_router.include_router(view_configs_router)

__all__ = ["api_router"]
