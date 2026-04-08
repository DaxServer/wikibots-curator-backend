import logging
from typing import Optional

from sqlalchemy import or_
from sqlmodel import Session, col, func, select

from curator.db.models import User

logger = logging.getLogger(__name__)


def _apply_user_filter(query, filter_text: Optional[str]):
    """Apply text filter to a user query."""
    if filter_text:
        return query.where(
            or_(
                col(User.userid).ilike(f"%{filter_text}%"),
                col(User.username).ilike(f"%{filter_text}%"),
            )
        )
    return query


def get_users(
    session: Session,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[User]:
    """Fetch all users."""
    query = _apply_user_filter(select(User), filter_text)
    return list(session.exec(query.offset(offset).limit(limit)).all())


def count_users(session: Session, filter_text: Optional[str] = None) -> int:
    """Count all users."""
    query = _apply_user_filter(select(func.count(col(User.userid))), filter_text)
    return session.exec(query).one()


def ensure_user(session: Session, userid: str, username: str) -> User:
    """Ensure a `User` row exists for `userid`; set username.

    Returns the `User` instance (possibly newly created).
    """
    user: Optional[User] = session.get(User, userid)

    if user is None:
        user = User(userid=userid, username=username)
        session.add(user)
        session.flush()

        logger.info(f"[dal] Created user {userid} {username}")

    return user
