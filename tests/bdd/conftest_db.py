"""
Database fixtures for BDD tests.
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="engine", scope="session")
def engine_fixture(session_mocker):
    """
    Use strictly in-memory SQLite with StaticPool to ensure all connections
    share the same state without creating any files on disk.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # Patch the global engine in the db module
    session_mocker.patch("curator.app.db.engine", engine)

    yield engine


@pytest.fixture(autouse=True)
def clean_db(engine):
    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.exec(table.delete())
        session.commit()
