from __future__ import annotations

from threading import RLock
from typing import Type

from engine.core.execution_context import ExecutionContext
from engine.rules.base_rule import BaseRule
from utils.logger import get_logger


logger = get_logger(__name__)


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, Type[BaseRule]] = {}
        self._lock = RLock()

    def register(
        self,
        rule_class: Type[BaseRule],
    ) -> Type[BaseRule]:
        try:
            rule_id = self._get_rule_id(rule_class)

            with self._lock:
                if rule_id in self._rules:
                    raise ValueError(
                        f"Rule '{rule_id}' is already registered."
                    )

                self._rules[rule_id] = rule_class

            logger.info("Registered rule '%s'", rule_id)
            return rule_class
        except Exception:
            logger.exception("Failed to register rule")
            raise

    def unregister(
        self,
        rule_id: str,
    ) -> None:
        try:
            normalized_id = self._normalize_rule_id(rule_id)
            with self._lock:
                removed = self._rules.pop(normalized_id, None)
            logger.info(
                "Unregistered rule '%s' (found=%s)",
                normalized_id,
                removed is not None,
            )
        except Exception:
            logger.exception("Failed to unregister rule '%s'", rule_id)
            raise

    def get(
        self,
        rule_id: str,
        context: ExecutionContext,
    ) -> BaseRule:
        try:
            normalized_id = self._normalize_rule_id(rule_id)

            with self._lock:
                rule_class = self._rules.get(normalized_id)

            if rule_class is None:
                raise KeyError(
                    f"No rule registered for rule ID '{rule_id}'."
                )

            rule = rule_class()
            logger.debug("Created rule '%s'", normalized_id)
            return rule
        except Exception:
            logger.exception("Failed to create rule '%s'", rule_id)
            raise

    def contains(
        self,
        rule_id: str,
    ) -> bool:
        try:
            normalized_id = self._normalize_rule_id(rule_id)
            with self._lock:
                result = normalized_id in self._rules
            logger.debug("Checked rule '%s': %s", normalized_id, result)
            return result
        except Exception:
            logger.exception("Failed to check rule '%s'", rule_id)
            raise

    def all(self) -> dict[str, Type[BaseRule]]:
        try:
            with self._lock:
                rules = dict(self._rules)
            logger.debug("Retrieved %s registered rules", len(rules))
            return rules
        except Exception:
            logger.exception("Failed to retrieve registered rules")
            raise

    def rule_ids(self) -> list[str]:
        try:
            with self._lock:
                rule_ids = list(self._rules.keys())
            logger.debug("Retrieved registered rule IDs: %s", rule_ids)
            return rule_ids
        except Exception:
            logger.exception("Failed to retrieve registered rule IDs")
            raise

    def clear(self) -> None:
        try:
            with self._lock:
                count = len(self._rules)
                self._rules.clear()
            logger.info("Cleared %s registered rules", count)
        except Exception:
            logger.exception("Failed to clear registered rules")
            raise

    @staticmethod
    def _get_rule_id(
        rule_class: Type[BaseRule],
    ) -> str:
        rule_id = getattr(
            rule_class,
            "rule_id",
            "",
        )

        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(
                f"Rule class '{rule_class.__name__}' "
                "must define a non-empty 'rule_id'."
            )

        return RuleRegistry._normalize_rule_id(rule_id)

    @staticmethod
    def _normalize_rule_id(
        rule_id: str,
    ) -> str:
        if not isinstance(rule_id, str):
            raise TypeError(
                "rule_id must be a string."
            )

        return rule_id.strip().upper()

    def register_instance(
        self,
        rule: BaseRule,
    ) -> BaseRule:
        try:
            self.register(type(rule))
            logger.debug("Registered rule instance '%s'", type(rule).__name__)
            return rule
        except Exception:
            logger.exception("Failed to register rule instance")
            raise


default_rule_registry = RuleRegistry()


def register_rule(
    rule_class: Type[BaseRule],
) -> Type[BaseRule]:
    return default_rule_registry.register(rule_class)
