from fastapi import APIRouter

from core.config import ACCEL_PATH
from utils.logger import get_logger


logger = get_logger(__name__)


health_bp = APIRouter()


@health_bp.get("/api/health")
def health():
    try:
        result = {
            "ok": True,
            "accelerator_path": str(ACCEL_PATH),
        }
        logger.debug("Health check succeeded")
        return result
    except Exception:
        logger.exception("Health check failed")
        raise
