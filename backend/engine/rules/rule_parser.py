from __future__ import annotations

from typing import Any

from utils.logger import get_logger


logger = get_logger(__name__)


class RuleParameterParser:
    @staticmethod
    def parse(parameters: str | None) -> list[str]:
        try:
            if not isinstance(parameters, str):
                return []

            if not parameters.strip():
                return []

            return [
                parameter.strip()
                for parameter in parameters.split("|")
            ]
        except Exception:
            logger.exception("Failed to parse rule parameters")
            raise

    @classmethod
    def get(
        cls,
        parameters: str | None,
        position: int,
        default: str = "",
    ) -> str:
        parsed = cls.parse(parameters)

        if position < 0 or position >= len(parsed):
            return default

        return parsed[position]

    @classmethod
    def get_int(
        cls,
        parameters: str | None,
        position: int,
        default: int,
    ) -> int:
        value = cls.get(
            parameters=parameters,
            position=position,
            default="",
        )

        if not value:
            return default

        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid integer rule parameter '%s'; using default %s",
                value,
                default,
                exc_info=True,
            )
            return default

    @classmethod
    def get_float(
        cls,
        parameters: str | None,
        position: int,
        default: float,
    ) -> float:
        value = cls.get(
            parameters=parameters,
            position=position,
            default="",
        )

        if not value:
            return default

        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid float rule parameter '%s'; using default %s",
                value,
                default,
                exc_info=True,
            )
            return default

    @classmethod
    def get_bool(
        cls,
        parameters: str | None,
        position: int,
        default: bool = False,
    ) -> bool:
        value = cls.get(
            parameters=parameters,
            position=position,
            default="",
        ).strip().lower()

        if not value:
            return default

        if value in {"true", "yes", "y", "1", "x"}:
            return True

        if value in {"false", "no", "n", "0"}:
            return False

        return default

    @classmethod
    def get_list(
        cls,
        parameters: str | None,
        position: int,
        separator: str = ",",
    ) -> list[str]:
        value = cls.get(
            parameters=parameters,
            position=position,
            default="",
        )

        if not value:
            return []

        return [
            item.strip()
            for item in value.split(separator)
            if item.strip()
        ]

    @classmethod
    def as_dict(
        cls,
        parameters: str | None,
        keys: list[str],
    ) -> dict[str, Any]:
        try:
            values = cls.parse(parameters)

            return {
                key: values[index] if index < len(values) else ""
                for index, key in enumerate(keys)
            }
        except Exception:
            logger.exception("Failed to convert rule parameters to a mapping")
            raise
