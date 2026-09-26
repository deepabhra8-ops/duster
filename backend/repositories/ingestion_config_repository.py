from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import get_db_session
from repositories.models import IngestionConfig
from utils.logger import get_logger


logger = get_logger(__name__)


class IngestionConfigRepository:
    def get(self, connection_id: str) -> dict[str, Any] | None:
        try:
            with get_db_session() as session:
                row = session.get(IngestionConfig, connection_id)
                return self._to_dict(row) if row is not None else None
        except Exception:
            logger.exception("Failed to read ingestion config for '%s'", connection_id)
            raise

    def upsert(
        self,
        connection_id: str,
        system_type: str,
        latency_requirement: str,
        scheduling_ownership: str,
        ingestion_mode: str,
    ) -> dict[str, Any]:
        try:
            with get_db_session() as session:
                row = session.get(IngestionConfig, connection_id)

                if row is None:
                    row = IngestionConfig(connection_id=connection_id)
                    session.add(row)

                row.system_type = system_type
                row.latency_requirement = latency_requirement
                row.scheduling_ownership = scheduling_ownership
                row.ingestion_mode = ingestion_mode
                row.updated_at = datetime.utcnow()

                session.commit()

                logger.info(
                    "Saved ingestion config for connection '%s' (mode=%s)",
                    connection_id,
                    ingestion_mode,
                )
                return self._to_dict(row)
        except Exception:
            logger.exception("Failed to save ingestion config for '%s'", connection_id)
            raise

    @staticmethod
    def _to_dict(row: IngestionConfig) -> dict[str, Any]:
        return {
            "connectionId": row.connection_id,
            "systemType": row.system_type,
            "latencyRequirement": row.latency_requirement,
            "schedulingOwnership": row.scheduling_ownership,
            "ingestionMode": row.ingestion_mode,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }


ingestion_config_repository = IngestionConfigRepository()
