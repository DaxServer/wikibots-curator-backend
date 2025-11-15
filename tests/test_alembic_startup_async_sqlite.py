import os
import asyncio
from alembic.config import Config
from alembic import command


def test_alembic_upgrade_runs_inside_event_loop_with_sqlite():
    db_path = "./test-startup.sqlite"
    db_url = f"sqlite:///{db_path}"
    if os.path.exists(db_path):
        os.remove(db_path)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    async def run_upgrade():
        await asyncio.to_thread(command.upgrade, cfg, "head")

    asyncio.run(run_upgrade())
    try:
        assert os.path.exists(db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
