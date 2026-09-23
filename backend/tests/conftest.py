from __future__ import annotations

import logging
import pytest

from engine.core.spark_session import get_spark_session


@pytest.fixture(scope="session", autouse=True)
def silence_py4j():
    logging.getLogger("py4j").setLevel(logging.WARNING)
    logging.getLogger("py4j.clientserver").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def spark():
    session = get_spark_session()
    yield session
    session.stop()
