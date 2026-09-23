from __future__ import annotations

import os
import sys
from threading import Lock

from pyspark.sql import SparkSession


_spark_session: SparkSession | None = None
_spark_session_lock = Lock()

_JDBC_PACKAGES = (
    "org.postgresql:postgresql:42.7.7",
    "com.amazon.redshift:redshift-jdbc42:2.1.0.33",
    "com.mysql:mysql-connector-j:9.3.0",
    "com.microsoft.sqlserver:mssql-jdbc:12.10.0.jre11",
    "com.oracle.database.jdbc:ojdbc11:23.8.0.25.04",
    "net.snowflake:snowflake-jdbc:3.24.2",
    "com.databricks:databricks-jdbc:2.7.3",
    "com.google.cloud.spark:spark-bigquery-with-dependencies_2.12:0.44.2",
)


def get_spark_session() -> SparkSession:
    global _spark_session

    if _spark_session is None:
        with _spark_session_lock:
            if _spark_session is None:
                _spark_session = _build_spark_session()

    return _spark_session


def _build_spark_session() -> SparkSession:
    python_executable = os.getenv(
        "PYSPARK_PYTHON",
        sys.executable,
    )
    os.environ.setdefault("PYSPARK_PYTHON", python_executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    driver_host = os.getenv("SPARK_DRIVER_HOST", "127.0.0.1")
    os.environ.setdefault("SPARK_LOCAL_IP", driver_host)
    os.environ.setdefault("SPARK_LOCAL_HOSTNAME", driver_host)

    os.environ.setdefault("SPARK_AUTH_SOCKET_TIMEOUT", "60")

    builder = (
        SparkSession.builder
        .appName("DUSTER")
        .master(os.getenv("SPARK_MASTER", "local[*]"))
        .config("spark.driver.host", driver_host)
        .config("spark.driver.bindAddress", driver_host)
        .config("spark.pyspark.python", python_executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .config("spark.executorEnv.PYSPARK_PYTHON", python_executable)
        .config("spark.python.worker.reuse", "true")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.optimizer.maxIterations", "500")
        .config("spark.network.timeout", "300s")
        .config("spark.executor.heartbeatInterval", "30s")
        .config("spark.jars.packages", ",".join(_JDBC_PACKAGES))
    )

    return builder.getOrCreate()
