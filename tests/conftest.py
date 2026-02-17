"""Test configuration - imports shared fixtures."""

# Import all shared fixtures from fixtures.py
# This ensures backward compatibility for tests that import from conftest
import sys
from pathlib import Path

# Add tests directory to path if not already there
tests_dir = str(Path(__file__).parent)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

from fixtures import *  # noqa: E402, F403, F406
