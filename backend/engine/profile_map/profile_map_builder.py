from __future__ import annotations

from typing import Any, Mapping

from engine.core.result_models import (
    ProfileRunResult,
    RuleConfiguration,
    TableProfileResult,
    TableRuleConfiguration,
)
from utils.logger import get_logger


logger = get_logger(__name__)


class ProfileMapBuilder:
    def build(
        self,
        profile_result: ProfileRunResult,
        inferred_rules: Mapping[str, Mapping[str, list[str]]] | None = None,
        existing_configuration: Mapping[str, TableRuleConfiguration]
        | None = None,
    ) -> dict[str, TableRuleConfiguration]:
        try:
            inferred_rules = inferred_rules or {}
            existing_configuration = existing_configuration or {}

            result: dict[str, TableRuleConfiguration] = {}

            for table_name, table_profile in profile_result.tables.items():
                table_rules = inferred_rules.get(
                    table_name,
                    {},
                )

                existing_table = existing_configuration.get(
                    table_name
                )

                result[table_name] = self.build_table(
                    profile=table_profile,
                    inferred_rules=table_rules,
                    existing_configuration=existing_table,
                )

            logger.info(
                "Built profile-map configuration for %s tables",
                len(result),
            )
            return result
        except Exception:
            logger.exception("Failed to build profile-map configuration")
            raise

    def build_table(
        self,
        profile: TableProfileResult,
        inferred_rules: Mapping[str, list[str]] | None = None,
        existing_configuration: TableRuleConfiguration | None = None,
    ) -> TableRuleConfiguration:
        try:
            inferred_rules = inferred_rules or {}

            existing_columns = self._index_existing_columns(
                existing_configuration
            )

            primary_key_columns = self._get_primary_key_columns(
                profile
            )

            columns: list[RuleConfiguration] = []

            for column_profile in profile.columns:
                column_name = column_profile.column_name

                existing_list = existing_columns.get(
                    column_name,
                    []
                )

                is_primary_key = (
                    column_name in primary_key_columns
                )

                if existing_list:
                    for existing in existing_list:
                        if len(existing.rule_ids) > 1:
                            for rule_id in existing.rule_ids:
                                columns.append(
                                    RuleConfiguration(
                                        column_name=column_name,
                                        rule_ids=(rule_id,),
                                        parameters=existing.parameters,
                                        cde=existing.cde,
                                        analyst_notes=existing.analyst_notes,
                                        metadata=self._build_column_metadata(
                                            column_profile=column_profile,
                                            existing=existing,
                                        ),
                                    )
                                )
                        else:
                            columns.append(
                                RuleConfiguration(
                                    column_name=column_name,
                                    rule_ids=existing.rule_ids,
                                    parameters=existing.parameters,
                                    cde=existing.cde,
                                    analyst_notes=existing.analyst_notes,
                                    metadata=self._build_column_metadata(
                                        column_profile=column_profile,
                                        existing=existing,
                                    ),
                                )
                            )
                else:
                    rule_ids = list(
                        inferred_rules.get(
                            column_name,
                            [],
                        )
                    )

                    if is_primary_key:
                        rule_ids = list(
                            dict.fromkeys(
                                ["DQ10"] + rule_ids
                            )
                        )

                    cde = is_primary_key

                    if not rule_ids:
                        columns.append(
                            RuleConfiguration(
                                column_name=column_name,
                                rule_ids=(),
                                parameters=self._default_parameters(column_profile),
                                cde=cde,
                                analyst_notes="",
                                metadata=self._build_column_metadata(
                                    column_profile=column_profile,
                                    existing=None,
                                ),
                            )
                        )
                    else:
                        for rule_id in rule_ids:
                            columns.append(
                                RuleConfiguration(
                                    column_name=column_name,
                                    rule_ids=(rule_id,),
                                    parameters=self._default_parameters(column_profile),
                                    cde=cde,
                                    analyst_notes="",
                                    metadata=self._build_column_metadata(
                                        column_profile=column_profile,
                                        existing=None,
                                    ),
                                )
                            )

            result = TableRuleConfiguration(
                table_name=profile.table_name,
                columns=tuple(columns),
                metadata={
                    "profile_metadata": dict(
                        profile.metadata
                    ),
                },
            )
            logger.debug(
                "Built profile-map configuration for table '%s'",
                profile.table_name,
            )
            return result
        except Exception:
            logger.exception(
                "Failed to build profile-map configuration for table '%s'",
                profile.table_name,
            )
            raise

    def build_from_profiles(
        self,
        profiles: Mapping[str, TableProfileResult],
        inferred_rules: Mapping[str, Mapping[str, list[str]]]
        | None = None,
    ) -> dict[str, TableRuleConfiguration]:
        try:
            result = ProfileRunResult(
                project_name="",
                run_timestamp="",
                tables=profiles,
            )

            return self.build(
                profile_result=result,
                inferred_rules=inferred_rules,
            )
        except Exception:
            logger.exception("Failed to build profile map from profiles")
            raise

    @staticmethod
    def _get_primary_key_columns(
        profile: TableProfileResult,
    ) -> set[str]:
        try:
            table_config = profile.metadata.get(
                "table_config",
                {},
            )

            primary_key = table_config.get(
                "primary_key",
                [],
            )

            if not isinstance(primary_key, (list, tuple, set)):
                return set()

            return {
                str(column).strip()
                for column in primary_key
            }
        except Exception:
            logger.exception(
                "Failed to resolve primary-key columns for table '%s'",
                profile.table_name,
            )
            raise

    @staticmethod
    def _index_existing_columns(
        configuration: TableRuleConfiguration | None,
    ) -> dict[str, list[RuleConfiguration]]:
        try:
            if configuration is None:
                return {}

            result: dict[str, list[RuleConfiguration]] = {}
            for column in configuration.columns:
                result.setdefault(column.column_name, []).append(column)
            return result
        except Exception:
            logger.exception("Failed to index existing profile-map columns")
            raise

    @staticmethod
    def _default_parameters(
        column_profile: Any,
    ) -> str:
        return ""

    @staticmethod
    def _build_column_metadata(
        column_profile: Any,
        existing: RuleConfiguration | None,
    ) -> dict[str, Any]:
        try:
            metadata = {
                "dtype": column_profile.dtype,
                "total_count": column_profile.total_count,
                "null_count": column_profile.null_count,
                "distinct_count": column_profile.distinct_count,
                "min_value": column_profile.min_value,
                "max_value": column_profile.max_value,
            }

            if existing is not None:
                metadata.update(
                    dict(existing.metadata)
                )

            return metadata
        except Exception:
            logger.exception("Failed to build profile-map column metadata")
            raise
