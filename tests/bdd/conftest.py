"""Global fixtures and helpers for BDD tests."""

import inspect
import sys
from pathlib import Path

import pytest

# Add tests directory to path if not already there
tests_dir = str(Path(__file__).parent.parent)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

# Import all shared fixtures from fixtures.py
from fixtures import *  # noqa: E402, F403, F406

# Import step definitions so pytest-bdd can discover them
# Import the module to trigger decorator registration
from . import conftest_steps  # noqa: E402, F406

# Import database fixtures
from .conftest_db import *  # noqa: E402, F403, F406

# Copy the step definition fixtures to this module so pytest-bdd can find them
for name, obj in inspect.getmembers(conftest_steps):
    if name.startswith("pytestbdd_stepdef_"):
        globals()[name] = obj


@pytest.fixture
def client(engine, mocker):
    """Test client fixture for BDD tests"""
    from fastapi.testclient import TestClient

    from curator.main import app

    app.dependency_overrides = {}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides = {}
