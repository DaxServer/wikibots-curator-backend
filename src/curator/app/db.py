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
if TOOLSDB_USER and TOOLSDB_PASSWORD:
    DB_URL = (
        f"mysql+mysqlconnector://{TOOLSDB_USER}:{TOOLSDB_PASSWORD}"
        f"@tools.db.svc.wikimedia.cloud/{TOOLSDB_USER}__curator"
    )
    CONNECT_ARGS.update({"ssl_disabled": True})
else:
    DB_URL = os.getenv(
        "DB_URL", "mysql+mysqlconnector://curator:curator@localhost/curator"
    )

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
    retry=retry_if_exception_type(OperationalError),
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
    - Handles PendingRollbackError by rolling back first.
    - Uses retries for session creation.
    """
    session = _create_session()
    try:
        yield session
        session.commit()
    except (OperationalError, PendingRollbackError) as e:
        logger.warning(f"Database session error, rolling back: {e}")
        session.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database session, rolling back: {e}")
        session.rollback()
        raise
    finally:
        session.close()
