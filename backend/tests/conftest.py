"""Shared pytest fixtures.

`spark` is session-scoped and reuses the app's own get_spark_session() - the same one
production code calls - so Spark-dependent tests exercise the exact driver/session
configuration the app actually runs with (Windows workarounds, JAR discovery, etc.) rather
than a bespoke test SparkSession that might mask environment-specific issues.

Only request this fixture from a test explicitly decorated `@pytest.mark.spark` (or in a
module using `pytestmark = pytest.mark.spark`), so `pytest -m "not spark"` still gives fast
feedback without ever booting a JVM.
"""
from __future__ import annotations

import logging
import pytest

from engine.core.spark_session import get_spark_session


@pytest.fixture(scope="session", autouse=True)
def silence_py4j():
    """Prevent Py4J from logging to closed stdout/stderr during Python exit."""
    logging.getLogger("py4j").setLevel(logging.WARNING)
    logging.getLogger("py4j.clientserver").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def spark():
    session = get_spark_session()
    yield session
    session.stop()
