import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlmodel import Session, create_engine
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

TOOLSDB_USER = os.getenv("TOOL_TOOLSDB_USER")
TOOLSDB_PASSWORD = os.getenv("TOOL_TOOLSDB_PASSWORD")

CONNECT_ARGS = {"connect_timeout": 10}
# Note: pymysql doesn't use 'ssl_disabled' key, it uses 'ssl' dict or nothing
if TOOLSDB_USER and TOOLSDB_PASSWORD:
    DB_URL = (
        f"mysql+pymysql://{TOOLSDB_USER}:{TOOLSDB_PASSWORD}"
        f"@tools.db.svc.wikimedia.cloud/{TOOLSDB_USER}__curator"
    )
else:
    DB_URL = os.getenv("DB_URL", "mysql+pymysql://curator:curator@localhost/curator")

engine = create_engine(
    DB_URL,
    connect_args=CONNECT_ARGS,
    pool_recycle=280,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, PendingRollbackError)),
    reraise=True,
)
def _create_session() -> Session:
    return Session(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Robust session context manager.
    - Automatically rolls back on any exception.
    - Closes the session on exit.
    - Uses retries for session creation.
    """
    session = _create_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.warning(f"Database session error, rolling back: {e}")
        session.rollback()
        raise
    finally:
        session.close()
