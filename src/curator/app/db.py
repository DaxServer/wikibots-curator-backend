import os

from sqlmodel import create_engine, Session


DB_URL = os.getenv("DB_URL", "sqlite:///./curator.sqlite")
engine = create_engine(DB_URL)


def get_session():
    with Session(engine) as session:
        yield session
