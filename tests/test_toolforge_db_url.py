import importlib
import os
import sys


def test_toolforge_db_url_builds_mysqlconnector():
    os.environ["TOOL_TOOLSDB_USER"] = "tools.curator"
    os.environ["TOOL_TOOLSDB_PASSWORD"] = "x"

    for m in ["curator.app.db"]:
        if m in sys.modules:
            del sys.modules[m]

    db = importlib.import_module("curator.app.db")

    assert db.DB_URL.startswith("mysql+mysqlconnector://")
    assert db.DB_URL.endswith("tools.curator__curator")
