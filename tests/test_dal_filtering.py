from unittest.mock import Mock, call

from sqlalchemy import String, func
from sqlmodel import select

from curator.app.dal import count_batches, get_batches
from curator.app.models import Batch, User


def test_get_batches_filtering_integration(tmp_path):
    """Integration test using in-memory SQLite"""
    from sqlmodel import Session, SQLModel, create_engine

    # Setup DB
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Create users
        user1 = User(userid="u1", username="alice")
        user2 = User(userid="u2", username="bob")
        session.add(user1)
        session.add(user2)
        session.commit()

        # Create batches
        # Batch 1: alice
        b1 = Batch(userid="u1", id=101)
        # Batch 2: bob
        b2 = Batch(userid="u2", id=102)
        # Batch 3: alice (but different id)
        b3 = Batch(userid="u1", id=201)

        session.add(b1)
        session.add(b2)
        session.add(b3)
        session.commit()

        # Test filtering by username "ali"
        batches = get_batches(session, filter_text="ali")
        ids = [b.id for b in batches]
        assert 101 in ids
        assert 201 in ids
        assert 102 not in ids

        # Test filtering by ID "10"
        batches = get_batches(session, filter_text="10")
        ids = [b.id for b in batches]
        assert 101 in ids
        assert 102 in ids
        assert 201 not in ids

        # Test count
        count = count_batches(session, filter_text="ali")
        assert count == 2

        count = count_batches(session, filter_text="10")
        assert count == 2
