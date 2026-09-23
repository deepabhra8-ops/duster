"""Reads and edits stored profile-map rows.

Only four cells per row are editable - everything else is computed by profiling
and is read-only. Edits are validated here, applied atomically with a version
bump, and recorded per cell in the audit table.

An analyst can also add a rule row to a profiled column, for a rule profiling
did not suggest. An added row clones its source row's profiling metadata (so the
column's stats stay identical across its rules) and carries only its own rule,
parameters and notes. Its row_id is minted here, server-side, and returned in the
same response - a client never invents one.

Rule IDs are checked against core.config.VALID_RULE_IDS rather than the
engine's rule registry: the web container ships without the engine package (see
Dockerfile stage 2). The engine remains the authority at execution time; this is
an earlier, friendlier rejection of typos.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.config import (
    PROFILE_MAP_EDITABLE_FIELDS,
    PROFILE_MAP_NOTES_MAX_LEN,
    PROFILE_MAP_TEXT_FIELD_MAX_LEN,
    VALID_RULE_IDS,
)
from repositories.profile_map_repository import (
    ProfileMapVersionConflict,
    profile_map_repository,
)
from engine.profile_map.normalize_rows import normalize_rows
from utils.logger import get_logger


logger = get_logger(__name__)

TABLE_KEY = "Table"
COLUMN_KEY = "Column"
RULES_FIELD = "Applicable Rules"
PARAMS_FIELD = "Rule Parameters"
NOTES_FIELD = "Analyst Notes"
CDE_FIELD = "CDE (X=Yes)"

# What an analyst may set on a rule row they add. Everything else on the new row
# is inherited from the source row's profiling output, not client input.
ADDABLE_FIELDS = (RULES_FIELD, PARAMS_FIELD, NOTES_FIELD)

# Audit `field` values marking a row that did not exist before / no longer exists
# (the column is a plain VARCHAR(64) with no CHECK, so a label rather than a real
# field name is fine).
ROW_ADDED_FIELD = "(rule row added)"
ROW_REMOVED_FIELD = "(rule row removed)"

_VALID_RULE_IDS_UPPER = {rule.upper() for rule in VALID_RULE_IDS}


class ProfileMapService:
    """Validation and orchestration around ProfileMapRepository."""

    def get_results(self, job_id: str) -> dict[str, Any] | None:
        """Return {rows, version} for a job, or None if profiling hasn't produced any."""
        return profile_map_repository.get_or_backfill(job_id)

    def save_results(
        self,
        job_id: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Store freshly profiled rows (version resets to 1)."""
        normalized_rows = normalize_rows(rows)
        return profile_map_repository.save(job_id, normalized_rows)

    def apply_edits(
        self,
        job_id: str,
        version: int,
        edits: list[dict[str, Any]],
        edited_by: str,
        additions: list[dict[str, Any]] | None = None,
        removals: list[str] | None = None,
    ) -> dict[str, Any]:
        """Validate and apply a batch of cell edits, added rule rows and removals.

        `edits` is [{row_id, changes: {field: value}}]. Rows are matched by
        row_id, never by array index.

        `additions` is [{source_row_id, changes: {rule/params/notes}}] - each one
        appends a rule row to the column that `source_row_id` belongs to.

        `removals` is [row_id] - rule rows to drop.

        All three are applied in one transaction, so a Save carrying any mix of them
        lands whole or not at all. Removals run before additions, so swapping one rule
        for another in a single save doesn't trip the duplicate-rule check.

        Raises ValueError on invalid input, KeyError if the job has no profile map,
        and ProfileMapVersionConflict if `version` is stale.
        """
        stored = profile_map_repository.get_or_backfill(job_id)

        if stored is None:
            raise KeyError(f"No profile map for job: {job_id}")

        rows = [dict(row) for row in stored["rows"]]
        index = {
            str(row.get("row_id", "")): row
            for row in rows if row.get("row_id")
        }

        audit_entries: list[dict[str, Any]] = []

        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("Each edit must be an object")

            row_id = str(edit.get("row_id", "")).strip()
            changes = edit.get("changes")

            if not row_id:
                raise ValueError("Each edit requires a row_id")

            if not isinstance(changes, dict) or not changes:
                raise ValueError(
                    f"No changes supplied for row_id {row_id}"
                )

            row = index.get(row_id)

            if row is None:
                raise ValueError(f"Unknown row_id: {row_id}")

            table = str(row.get(TABLE_KEY, ""))
            column = str(row.get(COLUMN_KEY, ""))

            for field, raw_value in changes.items():
                value = self._validate_cell(field, raw_value)
                old_value = row.get(field)

                if str(old_value or "") == value:
                    # Client echoed an unchanged value - nothing to record.
                    continue

                row[field] = value
                audit_entries.append(
                    {
                        "table": table,
                        "column": column,
                        "row_id": row_id,
                        "field": field,
                        "old_value": None if old_value is None else str(old_value),
                        "new_value": value,
                    }
                )

        for row_id in removals or []:
            self._remove_rule_row(rows, index, row_id, audit_entries)

        for addition in additions or []:
            self._add_rule_row(rows, index, addition, audit_entries)

        if not audit_entries:
            # Nothing actually changed; don't burn a version on a no-op save.
            return {"rows": stored["rows"], "version": stored["version"]}

        return profile_map_repository.apply_edits(
            job_id=job_id,
            expected_version=version,
            rows=rows,
            audit_entries=audit_entries,
            edited_by=edited_by,
        )

    def list_edits(self, job_id: str, limit: int = 200) -> list[dict[str, Any]]:
        """Return a job's profile-map edit history, newest first."""
        return profile_map_repository.list_edits(job_id, limit)

    def _add_rule_row(
        self,
        rows: list[dict[str, Any]],
        index: dict[str, dict[str, Any]],
        addition: dict[str, Any],
        audit_entries: list[dict[str, Any]],
    ) -> None:
        """Append one analyst-added rule row to its source row's column, in place."""
        if not isinstance(addition, dict):
            raise ValueError("Each added row must be an object")

        source_row_id = str(addition.get("source_row_id", "")).strip()

        if not source_row_id:
            raise ValueError("Each added row requires a source_row_id")

        source = index.get(source_row_id)

        if source is None:
            # Same contract as an edit: the client identifies the column by a row
            # the server gave it, never by inventing an id of its own.
            raise ValueError(f"Unknown source_row_id: {source_row_id}")

        changes = addition.get("changes")

        if not isinstance(changes, dict):
            raise ValueError("Each added row requires a changes object")

        for field in changes:
            if field not in ADDABLE_FIELDS:
                raise ValueError(f"'{field}' cannot be set on an added rule row")

        rule = self._validate_cell(RULES_FIELD, changes.get(RULES_FIELD, ""))

        if not rule:
            raise ValueError("An added rule row needs an applicable rule")

        table = str(source.get(TABLE_KEY, ""))
        column = str(source.get(COLUMN_KEY, ""))

        # One rule may only apply to a column once - two rows for the same rule would
        # run it twice and score the column twice, with no way to tell them apart.
        if rule in self._rules_for_column(rows, table, column):
            raise ValueError(f"'{column}' already has a {rule} rule")

        new_row = dict(source)
        new_row["row_id"] = str(uuid.uuid4())
        new_row[RULES_FIELD] = rule
        new_row[PARAMS_FIELD] = self._validate_cell(
            PARAMS_FIELD, changes.get(PARAMS_FIELD, "")
        )
        new_row[NOTES_FIELD] = self._validate_cell(
            NOTES_FIELD, changes.get(NOTES_FIELD, "")
        )

        rows.insert(self._insert_position(rows, table, column), new_row)
        index[new_row["row_id"]] = new_row

        audit_entries.append(
            {
                "table": table,
                "column": column,
                "row_id": new_row["row_id"],
                "field": ROW_ADDED_FIELD,
                "old_value": None,
                "new_value": rule,
            }
        )

    def _remove_rule_row(
        self,
        rows: list[dict[str, Any]],
        index: dict[str, dict[str, Any]],
        raw_row_id: Any,
        audit_entries: list[dict[str, Any]],
    ) -> None:
        """Drop one rule row, in place, keeping its column present in the map."""
        row_id = str(raw_row_id or "").strip()

        if not row_id:
            raise ValueError("Each removal requires a row_id")

        row = index.get(row_id)

        if row is None:
            raise ValueError(f"Unknown row_id: {row_id}")

        table = str(row.get(TABLE_KEY, ""))
        column = str(row.get(COLUMN_KEY, ""))

        # A column with no rows at all would vanish from the profile map - and with it
        # the source row an analyst needs to add a rule back. Skipping a column is what
        # Enabled is for, so keep the last rule and point the user at it.
        siblings = [
            candidate
            for candidate in rows
            if candidate is not row
            and str(candidate.get(TABLE_KEY, "")) == table
            and str(candidate.get(COLUMN_KEY, "")) == column
        ]

        if not siblings:
            raise ValueError(
                f"'{column}' must keep at least one rule - untick Enabled to skip the "
                "column instead of removing its last rule"
            )

        for offset, candidate in enumerate(rows):
            # Identity, not equality: two rows could be value-equal.
            if candidate is row:
                del rows[offset]
                break

        del index[row_id]

        audit_entries.append(
            {
                "table": table,
                "column": column,
                "row_id": row_id,
                "field": ROW_REMOVED_FIELD,
                "old_value": str(row.get(RULES_FIELD, "")),
                "new_value": None,
            }
        )

    @staticmethod
    def _rules_for_column(
        rows: list[dict[str, Any]],
        table: str,
        column: str,
    ) -> set[str]:
        """Rule ids already applied to one column, upper-cased."""
        return {
            str(row.get(RULES_FIELD, "")).strip().upper()
            for row in rows
            if str(row.get(TABLE_KEY, "")) == table
            and str(row.get(COLUMN_KEY, "")) == column
        }

    @staticmethod
    def _insert_position(
        rows: list[dict[str, Any]],
        table: str,
        column: str,
    ) -> int:
        """Index just past this column's last row, keeping a column's rules contiguous.

        The UI groups rows by column and the exported workbook preserves row order,
        so an added rule belongs beside its siblings rather than at the end.
        """
        position = len(rows)

        for offset, row in enumerate(rows):
            if (
                str(row.get(TABLE_KEY, "")) == table
                and str(row.get(COLUMN_KEY, "")) == column
            ):
                position = offset + 1

        return position

    @classmethod
    def _validate_cell(cls, field: str, raw_value: Any) -> str:
        """Return the normalized value for one edited cell, or raise ValueError."""
        if field not in PROFILE_MAP_EDITABLE_FIELDS:
            raise ValueError(f"'{field}' is not editable")

        value = "" if raw_value is None else str(raw_value).strip()

        limit = PROFILE_MAP_NOTES_MAX_LEN if field == NOTES_FIELD else PROFILE_MAP_TEXT_FIELD_MAX_LEN
        if len(value) > limit:
            raise ValueError(f"'{field}' is limited to {limit} characters")

        if field == CDE_FIELD:
            return cls._normalize_cde(value)

        if field == RULES_FIELD:
            return cls._normalize_rule_ids(value)

        return value

    @staticmethod
    def _normalize_cde(value: str) -> str:
        """CDE is a flag rendered as a checkbox: 'X' when set, empty when not."""
        return "X" if value.strip().upper() in ("X", "TRUE", "YES", "1") else ""

    @staticmethod
    def _normalize_rule_ids(value: str) -> str:
        """Validate and normalize a single rule ID (from one-rule-per-row UI)."""
        if not value:
            return ""

        rule_id = value.strip().upper()

        if rule_id not in _VALID_RULE_IDS_UPPER:
            raise ValueError(f"Unknown rule id: {rule_id}")

        return rule_id


profile_map_service = ProfileMapService()
