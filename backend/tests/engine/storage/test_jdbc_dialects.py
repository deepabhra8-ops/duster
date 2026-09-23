from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import make_url

from engine.storage.jdbc_dialects import (
    apply_jdbc_target,
    build_jdbc_target,
    dialect_of,
    is_bigquery,
    needs_explicit_column_types,
    prepare_dataframe_for_jdbc_write,
)


def test_dialect_of_strips_the_driver_suffix():
    assert dialect_of(make_url("postgresql+psycopg2://u:p@host/db")) == "postgresql"


def test_is_bigquery_detects_the_bigquery_scheme():
    assert is_bigquery("bigquery://project/dataset") is True
    assert is_bigquery(make_url("postgresql+psycopg2://u:p@host/db")) is False


@pytest.mark.parametrize(
    "db_type, expected_prefix, expected_driver",
    [
        ("postgresql", "jdbc:postgresql://", "org.postgresql.Driver"),
        ("redshift", "jdbc:redshift://", "com.amazon.redshift.jdbc.Driver"),
        ("mysql", "jdbc:mysql://", "com.mysql.cj.jdbc.Driver"),
    ],
)
def test_postgres_like_dialects_build_the_expected_jdbc_url(
    db_type, expected_prefix, expected_driver
):
    url = make_url(f"{db_type}+driver://user:pass@myhost:5432/mydb")
    target = build_jdbc_target(url)

    assert target.url.startswith(expected_prefix)
    assert "myhost:5432/mydb" in target.url
    assert target.driver == expected_driver
    assert target.properties == {"user": "user", "password": "pass"}


def test_mssql_renders_encrypt_and_trust_server_certificate_flags():
    url = make_url("mssql+pyodbc://user:pass@myhost/mydb?Encrypt=no")
    target = build_jdbc_target(url)

    assert "encrypt=false" in target.url
    assert "trustServerCertificate=false" in target.url


def test_oracle_requires_a_service_name_or_sid():
    url = make_url("oracle+oracledb://user:pass@myhost")
    with pytest.raises(ValueError, match="service_name or sid"):
        build_jdbc_target(url)


def test_oracle_builds_a_service_name_url():
    url = make_url("oracle+oracledb://user:pass@myhost/?service_name=ORCLPDB")
    target = build_jdbc_target(url)
    assert "ORCLPDB" in target.url


def test_databricks_requires_an_http_path():
    url = make_url("databricks://token:abc@myhost")
    with pytest.raises(ValueError, match="http_path"):
        build_jdbc_target(url)


def test_unrecognized_dialect_raises_a_clear_error():
    url = make_url("sqlite:///local.db")
    with pytest.raises(ValueError, match="No JDBC driver is configured"):
        build_jdbc_target(url)


def test_apply_jdbc_target_sets_url_driver_and_properties_as_options():
    target = build_jdbc_target(make_url("postgresql+psycopg2://user:pass@host/db"))
    reader = MagicMock()
    reader.option.return_value = reader

    result = apply_jdbc_target(reader, target)

    reader.option.assert_any_call("url", target.url)
    reader.option.assert_any_call("driver", target.driver)
    reader.option.assert_any_call("user", "user")
    reader.option.assert_any_call("password", "pass")
    assert result is reader


@pytest.mark.parametrize(
    "dialect, expected",
    [("redshift", True), ("snowflake", True), ("databricks", True), ("postgresql", False)],
)
def test_needs_explicit_column_types_flags_only_dialects_without_a_spark_mapping(
    dialect, expected
):
    assert needs_explicit_column_types(dialect) is expected


@pytest.mark.spark
def test_prepare_dataframe_for_jdbc_write_overrides_boolean_binary_and_nested_columns(spark):
    from pyspark.sql.types import (
        ArrayType,
        BinaryType,
        BooleanType,
        IntegerType,
        StringType,
        StructField,
        StructType,
    )

    schema = StructType(
        [
            StructField("id", IntegerType()),
            StructField("is_active", BooleanType()),
            StructField("payload", BinaryType()),
            StructField("tags", ArrayType(StringType())),
        ]
    )
    data = spark.createDataFrame([(1, True, b"hi", ["a", "b"])], schema=schema)

    transformed, overrides = prepare_dataframe_for_jdbc_write(data, "redshift")

    assert overrides == "`is_active` BOOLEAN, `payload` STRING, `tags` STRING"
    row = transformed.collect()[0]
    assert row["is_active"] is True
    assert row["payload"] == "aGk="
    assert row["tags"] == '["a","b"]'


@pytest.mark.spark
def test_prepare_dataframe_for_jdbc_write_is_a_no_op_for_dialects_with_a_spark_mapping(spark):
    data = spark.createDataFrame([(1, True)], schema=["id", "flag"])

    transformed, overrides = prepare_dataframe_for_jdbc_write(data, "postgresql")

    assert overrides is None
    assert transformed is data
