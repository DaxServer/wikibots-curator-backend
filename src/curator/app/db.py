import os
from sqlmodel import create_engine, Session


TOOLSDB_USER = os.getenv("TOOL_TOOLSDB_USER")
TOOLSDB_PASSWORD = os.getenv("TOOL_TOOLSDB_PASSWORD")

CONNECT_ARGS = {}
if TOOLSDB_USER and TOOLSDB_PASSWORD:
    DB_URL = (
        f"mysql+mysqlconnector://{TOOLSDB_USER}:{TOOLSDB_PASSWORD}"
        f"@tools.db.svc.wikimedia.cloud/{TOOLSDB_USER}__curator"
    )
    CONNECT_ARGS = {"ssl_disabled": True}
else:
    DB_URL = os.getenv("DB_URL", "sqlite:///./curator.sqlite")

engine = create_engine(DB_URL, connect_args=CONNECT_ARGS)


def get_session():
    with Session(engine) as session:
        yield session
