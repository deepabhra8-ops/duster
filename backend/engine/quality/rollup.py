"""Scores for a run, computed from its raw per-binding counts.

Three kinds of number, always labelled, because mixing them is how DQ dashboards
mislead:

* row-weighted (micro): sum(pass_count) / sum(total_count) over additive results
  (row-level and cross-table checks). Large tables dominate.
* simple average (macro): for a table, the mean of its bindings' pass rates; above a
  table, the mean of its tables' row-weighted rates. Every table counts once.
* status: how many evaluated bindings met their threshold. Skipped bindings aren't
  evaluated, so they don't count either way.

Aggregate metrics (uniqueness ratio, freshness hours, row counts) aren't additive, so
they contribute only through their status.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from engine.quality.models import (
    ADDITIVE_LEVELS,
    DIMENSIONS,
    SEVERITIES,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_WARN,
    STATUSES,
    STATUS_ERROR,
)


STATUS_RANK = {status: rank for rank, status in enumerate(STATUSES)}
ATTENTION = "attention"
ALL = "ALL"


def needs_attention(status: str) -> bool:
    return status not in (STATUS_PASS, STATUS_SKIPPED)


def _is_scored(record: Mapping[str, Any]) -> bool:
    return (
        record.get("rule_level") in ADDITIVE_LEVELS
        and record.get("status") in (STATUS_PASS, STATUS_WARN, STATUS_FAIL)
        and (record.get("total_count") or 0) > 0
        and record.get("pass_count") is not None
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def worst_status(statuses: Iterable[str]) -> str | None:
    statuses = set(statuses)
    evaluated = statuses - {STATUS_SKIPPED}

    if evaluated:
        return min(evaluated, key=STATUS_RANK.__getitem__)

    return STATUS_SKIPPED if statuses else None


class _Node:
    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.kind = kind
        self.children: dict[str, _Node] = {}
        self.passed = 0
        self.total = 0
        self.binding_rates: list[float] = []
        self.evaluated = 0
        self.passing = 0
        self.statuses: set[str] = set()

    def add(self, record: Mapping[str, Any]) -> None:
        status = record["status"]
        self.statuses.add(status)

        if status != STATUS_SKIPPED:
            self.evaluated += 1
            self.passing += status == STATUS_PASS

        if _is_scored(record):
            self.passed += int(record["pass_count"])
            self.total += int(record["total_count"])
            self.binding_rates.append(int(record["pass_count"]) / int(record["total_count"]))

    @property
    def row_weighted(self) -> float | None:
        return self.passed / self.total if self.total else None

    def tables(self) -> list["_Node"]:
        if self.kind == "table":
            return [self]

        return [table for child in self.children.values() for table in child.tables()]

    @property
    def simple_average(self) -> float | None:
        if self.kind == "table":
            return _mean(self.binding_rates)

        return _mean([t.row_weighted for t in self.tables() if t.row_weighted is not None])

    def to_dict(self) -> dict[str, Any]:
        node = {
            "name": self.name,
            "kind": self.kind,
            "rowWeighted": self.row_weighted,
            "simpleAverage": self.simple_average,
            "bindings": self.evaluated,
            "notPassing": self.evaluated - self.passing,
            "worstStatus": worst_status(self.statuses),
        }

        if self.kind != "table":
            children = [child.to_dict() for child in self.children.values()]
            children.sort(key=lambda c: (STATUS_RANK.get(c["worstStatus"], len(STATUSES)), c["name"].lower()))
            node["children"] = children

        return node


def _build_tree(results: list[Mapping[str, Any]]) -> _Node:
    root = _Node("", "root")

    for record in results:
        path = [
            (record.get("catalog"), "catalog"),
            (record.get("schema"), "schema"),
            (record.get("table"), "table"),
        ]
        node = root
        root.add(record)

        for name, kind in path:
            if name is None:
                break

            node = node.children.setdefault(name, _Node(name, kind))
            node.add(record)

    return root


def _kpis(root: _Node, result_count: int) -> dict[str, Any]:
    return {
        "rowWeighted": root.row_weighted,
        "tableAverage": root.simple_average,
        "thresholdsMet": root.passing,
        "thresholdsEvaluated": root.evaluated,
        "resultCount": result_count,
    }


def kpis(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    return _kpis(_build_tree(results), len(results))


def status_counts(results: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(STATUSES, 0)

    for record in results:
        counts[record["status"]] += 1

    counts[ATTENTION] = sum(counts[status] for status in STATUSES if needs_attention(status))
    counts[ALL] = sum(counts[status] for status in STATUSES)
    return counts


def _dimensions(results: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    met: dict[str, int] = {}
    total: dict[str, int] = {}

    for record in results:
        if record["status"] == STATUS_SKIPPED:
            continue

        dimension = record.get("dimension") or "other"
        total[dimension] = total.get(dimension, 0) + 1
        met[dimension] = met.get(dimension, 0) + (record["status"] == STATUS_PASS)

    order = {name: rank for rank, name in enumerate(DIMENSIONS)}
    return [
        {"dimension": name, "met": met[name], "total": total[name]}
        for name in sorted(total, key=lambda name: (order.get(name, len(order)), name))
    ]


def _worst_severity(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    failing = [r for r in results if r["status"] in (STATUS_FAIL, STATUS_WARN)]
    errors = sum(1 for r in results if r["status"] == STATUS_ERROR)

    if not failing:
        return {"severity": None, "bindings": 0, "rules": 0, "errors": errors}

    rank = {severity: index for index, severity in enumerate(SEVERITIES)}
    severity = max((r.get("severity") or "error" for r in failing), key=lambda s: rank.get(s, -1))
    worst = [r for r in failing if (r.get("severity") or "error") == severity]

    return {
        "severity": severity,
        "bindings": len(worst),
        "rules": len({r["rule_id"] for r in worst}),
        "errors": errors,
    }


def summarize(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    root = _build_tree(results)

    return {
        "kpis": _kpis(root, len(results)),
        "worstSeverity": _worst_severity(results),
        "statusCounts": status_counts(results),
        "dimensions": _dimensions(results),
        "tree": root.to_dict()["children"],
    }


def rule_status_counts(results: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    by_rule: dict[str, dict[str, int]] = {}

    for record in results:
        counts = by_rule.setdefault(record["rule_id"], {})
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    return by_rule
