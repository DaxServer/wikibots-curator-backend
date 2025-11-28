import os
import sys
import importlib


def test_celery_uses_db_url():
    os.environ["DB_URL"] = "mysql+mysqlconnector://curator:curator@localhost/curator"

    for m in ["curator.app.db", "curator.workers.celery"]:
        if m in sys.modules:
            del sys.modules[m]

    db = importlib.import_module("curator.app.db")
    cel = importlib.import_module("curator.workers.celery")

    assert cel.celery_app.conf.broker_url == f"sqla+{db.DB_URL}"
    assert cel.celery_app.conf.result_backend == f"db+{db.DB_URL}"
