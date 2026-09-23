from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

from pyspark.sql import DataFrame
from pyspark.sql.functions import base64 as spark_base64, col, to_json
from pyspark.sql.types import ArrayType, BinaryType, BooleanType, MapType, StructType
from sqlalchemy.engine import URL


BIGQUERY_DIALECT = "bigquery"

DIALECTS_WITHOUT_SPARK_MAPPING = {"redshift", "snowflake", "databricks"}


@dataclass(frozen=True)
class JdbcTarget:
    url: str
    driver: str
    properties: dict[str, str]


def dialect_of(connection_url: URL) -> str:
    return connection_url.drivername.split("+", 1)[0].lower()


def is_bigquery(connection_url: URL | str) -> bool:
    if isinstance(connection_url, str):
        return connection_url.strip().lower().startswith(f"{BIGQUERY_DIALECT}://")

    return dialect_of(connection_url) == BIGQUERY_DIALECT


def build_jdbc_target(connection_url: URL) -> JdbcTarget:
    dialect = dialect_of(connection_url)
    builder = _BUILDERS.get(dialect)

    if builder is None:
        raise ValueError(
            f"No JDBC driver is configured for database dialect '{dialect}'."
        )

    return builder(connection_url)


def apply_jdbc_target(reader_or_writer: Any, target: JdbcTarget) -> Any:
    result = (
        reader_or_writer
        .option("url", target.url)
        .option("driver", target.driver)
    )

    for key, value in target.properties.items():
        result = result.option(key, value)

    return result


def needs_explicit_column_types(dialect: str) -> bool:
    return dialect.strip().lower() in DIALECTS_WITHOUT_SPARK_MAPPING


def prepare_dataframe_for_jdbc_write(
    dataframe: DataFrame,
    dialect: str,
) -> tuple[DataFrame, str | None]:
    if not needs_explicit_column_types(dialect):
        return dataframe, None

    overrides: list[str] = []

    for field in dataframe.schema.fields:
        data_type = field.dataType
        quoted_name = f"`{field.name}`"

        if isinstance(data_type, BooleanType):
            overrides.append(f"{quoted_name} BOOLEAN")

        elif isinstance(data_type, BinaryType):
            dataframe = dataframe.withColumn(
                field.name,
                spark_base64(col(field.name)).cast("string"),
            )
            overrides.append(f"{quoted_name} STRING")

        elif isinstance(data_type, (ArrayType, MapType, StructType)):
            dataframe = dataframe.withColumn(
                field.name,
                to_json(col(field.name)),
            )
            overrides.append(f"{quoted_name} STRING")

    return dataframe, ", ".join(overrides) if overrides else None


def build_bigquery_options(
    db_config: Mapping[str, Any],
    table_reference: str,
) -> dict[str, str]:
    service_account_json = str(db_config.get("service_account_json", "")).strip()
    project_id = str(db_config.get("project_id", "")).strip()

    if not service_account_json:
        raise ValueError("BigQuery access requires service_account_json.")

    if not project_id:
        raise ValueError("BigQuery access requires project_id.")

    return {
        "table": table_reference,
        "parentProject": project_id,
        "credentials": base64.b64encode(
            service_account_json.encode("utf-8")
        ).decode("ascii"),
    }


def _credentials(connection_url: URL) -> dict[str, str]:
    properties: dict[str, str] = {}

    if connection_url.username:
        properties["user"] = connection_url.username

    if connection_url.password:
        properties["password"] = connection_url.password

    return properties


def _require_host(connection_url: URL, engine_name: str) -> None:
    if not connection_url.host:
        raise ValueError(
            f"{engine_name} connection_string must include a host."
        )


def _postgres_like(jdbc_scheme: str, driver: str):
    def build(connection_url: URL) -> JdbcTarget:
        _require_host(connection_url, jdbc_scheme)

        url = f"jdbc:{jdbc_scheme}://{connection_url.host}"

        if connection_url.port:
            url += f":{connection_url.port}"

        if connection_url.database:
            url += f"/{connection_url.database}"

        if connection_url.query:
            url += "?" + urlencode(dict(connection_url.query), doseq=True)

        return JdbcTarget(
            url=url,
            driver=driver,
            properties=_credentials(connection_url),
        )

    return build


def _build_mysql(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "mysql")

    url = f"jdbc:mysql://{connection_url.host}"

    if connection_url.port:
        url += f":{connection_url.port}"

    if connection_url.database:
        url += f"/{connection_url.database}"

    query = dict(connection_url.query)
    jdbc_params: dict[str, str] = {}

    ssl_mode = query.pop("ssl_mode", None)
    if ssl_mode:
        jdbc_params["sslMode"] = ssl_mode

    jdbc_params.update(query)

    if jdbc_params:
        url += "?" + urlencode(jdbc_params, doseq=True)

    return JdbcTarget(
        url=url,
        driver="com.mysql.cj.jdbc.Driver",
        properties=_credentials(connection_url),
    )


def _yes_no(value: Any, default: str) -> str:
    normalized = str(value).strip().lower()

    if normalized in ("yes", "true", "1"):
        return "true"

    if normalized in ("no", "false", "0"):
        return "false"

    return default


def _build_mssql(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "SQL Server")

    query = dict(connection_url.query)

    url = f"jdbc:sqlserver://{connection_url.host}"

    if connection_url.port:
        url += f":{connection_url.port}"

    if connection_url.database:
        url += f";databaseName={connection_url.database}"

    encrypt = _yes_no(query.get("Encrypt", query.get("encrypt", "yes")), "true")
    trust = _yes_no(
        query.get("TrustServerCertificate", query.get("trust_server_certificate", "no")),
        "false",
    )
    url += f";encrypt={encrypt};trustServerCertificate={trust}"

    authentication = query.get("Authentication") or query.get("authentication")
    if authentication:
        url += f";authentication={authentication}"

    return JdbcTarget(
        url=url,
        driver="com.microsoft.sqlserver.jdbc.SQLServerDriver",
        properties=_credentials(connection_url),
    )


def _build_oracle(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "Oracle")

    port = connection_url.port or 1521
    query = dict(connection_url.query)
    service_name = query.get("service_name")
    sid = query.get("sid")

    if service_name:
        url = f"jdbc:oracle:thin:@//{connection_url.host}:{port}/{service_name}"
    elif sid:
        url = f"jdbc:oracle:thin:@{connection_url.host}:{port}:{sid}"
    else:
        raise ValueError(
            "Oracle connection_string must include a service_name or sid."
        )

    return JdbcTarget(
        url=url,
        driver="oracle.jdbc.OracleDriver",
        properties=_credentials(connection_url),
    )


def _build_snowflake(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "Snowflake")

    database, _, schema = (connection_url.database or "").partition("/")
    params = {key: value for key, value in dict(connection_url.query).items() if value}

    if database:
        params.setdefault("db", database)

    if schema:
        params.setdefault("schema", schema)

    url = f"jdbc:snowflake://{connection_url.host}.snowflakecomputing.com/"

    if params:
        url += "?" + urlencode(params, doseq=True)

    return JdbcTarget(
        url=url,
        driver="net.snowflake.client.jdbc.SnowflakeDriver",
        properties=_credentials(connection_url),
    )


def _build_redshift(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "Redshift")

    url = f"jdbc:redshift://{connection_url.host}"

    if connection_url.port:
        url += f":{connection_url.port}"

    if connection_url.database:
        url += f"/{connection_url.database}"

    query = dict(connection_url.query)
    jdbc_params: dict[str, str] = {}

    sslmode = query.pop("sslmode", None)
    if sslmode and sslmode in ("require", "verify-ca", "verify-full"):
        jdbc_params["ssl"] = "true"

    jdbc_params.update(query)

    if jdbc_params:
        url += "?" + urlencode(jdbc_params, doseq=True)

    return JdbcTarget(
        url=url,
        driver="com.amazon.redshift.jdbc.Driver",
        properties=_credentials(connection_url),
    )


def _build_databricks(connection_url: URL) -> JdbcTarget:
    _require_host(connection_url, "Databricks")

    query = dict(connection_url.query)
    http_path = query.get("http_path", "")

    if not http_path:
        raise ValueError(
            "Databricks connection_string must include an http_path."
        )

    url = (
        f"jdbc:databricks://{connection_url.host}:443/default;"
        f"transportMode=http;ssl=1;AuthMech=3;httpPath={http_path}"
    )

    if query.get("catalog"):
        url += f";ConnCatalog={query['catalog']}"

    if query.get("schema"):
        url += f";ConnSchema={query['schema']}"

    return JdbcTarget(
        url=url,
        driver="com.databricks.client.jdbc.Driver",
        properties={
            "UID": "token",
            "PWD": connection_url.password or "",
        },
    )


_BUILDERS = {
    "postgresql": _postgres_like("postgresql", "org.postgresql.Driver"),
    "redshift": _build_redshift,
    "mysql": _build_mysql,
    "mssql": _build_mssql,
    "oracle": _build_oracle,
    "snowflake": _build_snowflake,
    "databricks": _build_databricks,
}
