from __future__ import annotations

import threading
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Callable, Iterable, Protocol, TypeVar

from engine.quality.models import Scope, TableRef


T = TypeVar("T")

KIND_TABLE = "TABLE"
KIND_VIEW = "VIEW"

# Skipped when a schema pattern contains a wildcard, so "*" means "the user's data",
# not the database's own bookkeeping. Naming one of these exactly still reaches it.
SYSTEM_SCHEMAS = frozenset({
    "information_schema",
    "pg_catalog",
    "pg_toast",
    "sys",
    "mysql",
    "performance_schema",
    "guest",
    "db_owner",
    "db_accessadmin",
    "db_securityadmin",
    "db_ddladmin",
    "db_backupoperator",
    "db_datareader",
    "db_datawriter",
    "db_denydatareader",
    "db_denydatawriter",
})


class CatalogProvider(Protocol):
    def list_catalogs(self) -> list[str]: ...

    def list_schemas(self, catalog: str) -> list[str]: ...

    def list_tables(self, catalog: str, schema: str) -> list[tuple[str, str]]: ...

    def list_columns(self, catalog: str, schema: str, table: str) -> list[tuple[str, str]]: ...


def is_wildcard(pattern: str | None) -> bool:
    return pattern is None or any(char in pattern for char in "*?[")


def glob_match(pattern: str | None, value: str) -> bool:
    # Case-insensitive on purpose: SQL Server and MySQL identifiers are, and Postgres
    # folds unquoted names to lower case, so "Orders" and "orders" mean the same table.
    if pattern is None or pattern.strip() in ("", "*"):
        return True

    return fnmatchcase(str(value).lower(), pattern.strip().lower())


def is_excluded(
    patterns: Iterable[str],
    catalog: str,
    schema: str,
    table: str,
    column: str | None = None,
) -> bool:
    """3-part patterns (catalog.schema.table) exclude tables, 4-part ones exclude
    columns. Anything else is matched against the dotted table name as a whole,
    where * also spans dots, so "main.*" excludes the whole catalog."""
    table_parts = (catalog, schema, table)
    joined = ".".join(table_parts)

    for pattern in patterns:
        parts = pattern.split(".")

        if column is None:
            if len(parts) == 3 and all(glob_match(p, v) for p, v in zip(parts, table_parts)):
                return True

            if len(parts) not in (3, 4) and glob_match(pattern, joined):
                return True
        elif len(parts) == 4 and all(glob_match(p, v) for p, v in zip(parts, (*table_parts, column))):
            return True

    return False


def kind_allowed(kind: str, table_types: Iterable[str]) -> bool:
    # JDBC sources can't tell Unity Catalog's MANAGED from EXTERNAL apart; both are
    # plain base tables there, so either flag admits them.
    table_types = set(table_types)

    if kind == KIND_VIEW:
        return "VIEW" in table_types

    return bool(table_types & {"MANAGED", "EXTERNAL"})


@dataclass
class Resolution:
    tables: list[TableRef] = field(default_factory=list)
    excluded: list[TableRef] = field(default_factory=list)
    # (catalog, schema or None, message) for metadata calls that failed, e.g. a
    # connection that is down. The rest of the scope still resolves.
    errors: list[tuple[str, str | None, str]] = field(default_factory=list)


class ScopeResolver:
    def __init__(self, provider: CatalogProvider) -> None:
        self.provider = provider
        self._cache: dict[tuple, object] = {}
        self._lock = threading.Lock()

    def _memo(self, key: tuple, load: Callable[[], T]) -> T:
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                if isinstance(cached, Exception):
                    raise cached
                return cached

        try:
            value = load()
        except Exception as exc:
            with self._lock:
                self._cache[key] = exc
            raise

        with self._lock:
            self._cache[key] = value

        return value

    def catalogs(self) -> list[str]:
        return self._memo(("catalogs",), self.provider.list_catalogs)

    def schemas(self, catalog: str) -> list[str]:
        return self._memo(("schemas", catalog), lambda: self.provider.list_schemas(catalog))

    def tables(self, catalog: str, schema: str) -> list[tuple[str, str]]:
        return self._memo(("tables", catalog, schema), lambda: self.provider.list_tables(catalog, schema))

    def columns(self, catalog: str, schema: str, table: str) -> list[tuple[str, str]]:
        return self._memo(
            ("columns", catalog, schema, table),
            lambda: self.provider.list_columns(catalog, schema, table),
        )

    def resolve(self, scope: Scope) -> Resolution:
        resolution = Resolution()

        for catalog in sorted(c for c in self.catalogs() if glob_match(scope.catalog, c)):
            try:
                schemas = self.schemas(catalog)
            except Exception as exc:
                resolution.errors.append((catalog, None, f"Couldn't list schemas: {exc}"))
                continue

            for schema in sorted(schemas):
                if not glob_match(scope.schema, schema):
                    continue

                if is_wildcard(scope.schema) and schema.lower() in SYSTEM_SCHEMAS:
                    continue

                self._resolve_schema(scope, catalog, schema, resolution)

        return resolution

    def _resolve_schema(self, scope: Scope, catalog: str, schema: str, resolution: Resolution) -> None:
        try:
            tables = self.tables(catalog, schema)
        except Exception as exc:
            resolution.errors.append((catalog, schema, f"Couldn't list tables: {exc}"))
            return

        for name, kind in sorted(tables):
            if not glob_match(scope.table, name) or not kind_allowed(kind, scope.table_types):
                continue

            ref = TableRef(catalog, schema, name, kind)

            if is_excluded(scope.exclude, catalog, schema, name):
                resolution.excluded.append(ref)
            else:
                resolution.tables.append(ref)
