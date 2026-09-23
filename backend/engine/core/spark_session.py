"""Process-wide Spark session used by every engine component that reads or writes bulk table data."""

from __future__ import annotations

import os
import sys
from threading import Lock

from pyspark.sql import SparkSession


_spark_session: SparkSession | None = None
_spark_session_lock = Lock()

# JDBC/connector drivers the engine's database data sources need on Spark's
# classpath, as Maven coordinates rather than jar files committed to the repo.
# Spark resolves and caches these itself (via Ivy, under ~/.ivy2) the first time
# a session starts - only that first run needs internet access, and every run
# after is offline, same as a bundled jar would have been. Bump a version here
# when a driver needs upgrading; nothing else to package or commit.
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
    """Return the single Spark session used by this application process, creating it on first use."""
    global _spark_session

    if _spark_session is None:
        with _spark_session_lock:
            if _spark_session is None:
                _spark_session = _build_spark_session()

    return _spark_session


def _build_spark_session() -> SparkSession:
    """Configure and create the process's Spark session."""
    python_executable = os.getenv(
        "PYSPARK_PYTHON",
        sys.executable,
    )
    os.environ.setdefault("PYSPARK_PYTHON", python_executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    driver_host = os.getenv("SPARK_DRIVER_HOST", "127.0.0.1")
    os.environ.setdefault("SPARK_LOCAL_IP", driver_host)
    os.environ.setdefault("SPARK_LOCAL_HOSTNAME", driver_host)

    # PySpark's default 15s socket timeout for a UDF worker connecting back to the JVM
    # (pyspark.util.local_connect_and_auth) can be too tight on a machine whose endpoint
    # security software inspects/delays loopback traffic from newly-spawned processes (e.g.
    # Sophos's Network Threat Protection) - the connection succeeds, just not within 15s.
    # Raised here rather than left to fail outright; harmless where it isn't needed.
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
        # Spark 3's default here is EXCEPTION, which makes to_date/to_timestamp
        # throw for input the legacy parser would have accepted. Date format
        # detection (engine/profiling/date_inference.py) deliberately parses
        # every column against every candidate format and counts what sticks, so
        # a non-match must be a NULL result, not an exception that aborts the
        # read. CORRECTED also refuses to silently reinterpret input the way
        # LEGACY does, which is the behaviour that detection depends on.
        .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
        .config("spark.ui.showConsoleProgress", "false")
        # Wide tables push the profiler's single combined aggregate query (4 expressions
        # per column, e.g. _profile_dataframe() in base_profiler.py) past Catalyst's
        # default 100-iteration cap for the "Operator Optimization after Inferring
        # Filters" batch - Spark just logs a WARN and runs the plan as far as it got.
        # Raised so wide tables actually reach a fixed point instead of an early cutoff.
        .config("spark.sql.optimizer.maxIterations", "500")
        # Same rationale as SPARK_AUTH_SOCKET_TIMEOUT above: on a machine where loopback
        # traffic is inspected/delayed, the driver's own executor-heartbeat RPC (default
        # every 10s, via spark.network.timeout's ~2min ceiling for the underlying ask) can
        # miss its window and trigger a re-registration loop. Widening both gives that RPC
        # more slack; harmless where it isn't needed.
        .config("spark.network.timeout", "300s")
        .config("spark.executor.heartbeatInterval", "30s")
        .config("spark.jars.packages", ",".join(_JDBC_PACKAGES))
    )

    return builder.getOrCreate()
