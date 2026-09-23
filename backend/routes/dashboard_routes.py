from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from routes.auth_routes import require_auth
from services.dashboard_service import dashboard_service
from utils.logger import get_logger


logger = get_logger(__name__)


dashboard_bp = APIRouter()


@dashboard_bp.get("/api/dashboard/summary")
def dashboard_summary(username: str = Depends(require_auth)):
    try:
        return {"ok": True, "data": dashboard_service.build_summary(username)}
    except Exception:
        logger.exception("Failed to build dashboard summary")
        return JSONResponse(
            {"ok": False, "error": "Failed to load dashboard data"},
            status_code=500,
        )
