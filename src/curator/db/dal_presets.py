import logging
from typing import Optional

from sqlalchemy import String
from sqlalchemy import cast as sqlalchemy_cast
from sqlalchemy import or_
from sqlmodel import Session, col, func, select, update

from curator.asyncapi import Label
from curator.db.models import Preset

logger = logging.getLogger(__name__)


def _apply_preset_filter(query, filter_text: Optional[str]):
    """Apply text filter to a preset query."""
    if filter_text:
        return query.where(
            or_(
                sqlalchemy_cast(col(Preset.id), String).ilike(f"%{filter_text}%"),
                col(Preset.userid).ilike(f"%{filter_text}%"),
                col(Preset.title).ilike(f"%{filter_text}%"),
            )
        )
    return query


def get_presets_for_handler(
    session: Session, userid: str, handler: str
) -> list[Preset]:
    """Fetch all presets for user and handler, ordered by created_at desc."""
    return list(
        session.exec(
            select(Preset)
            .where(col(Preset.userid) == userid, col(Preset.handler) == handler)
            .order_by(col(Preset.created_at).desc())
        ).all()
    )


def get_all_presets(
    session: Session,
    offset: int = 0,
    limit: int = 100,
    filter_text: Optional[str] = None,
) -> list[Preset]:
    """Fetch all presets across all users."""
    query = select(Preset).order_by(col(Preset.created_at).desc())
    query = _apply_preset_filter(query, filter_text)
    return list(session.exec(query.offset(offset).limit(limit)).all())


def count_all_presets(session: Session, filter_text: Optional[str] = None) -> int:
    """Count total presets across all users."""
    query = select(func.count(col(Preset.id)))
    query = _apply_preset_filter(query, filter_text)
    return session.exec(query).one()


def get_default_preset(session: Session, userid: str, handler: str) -> Optional[Preset]:
    """Fetch single default preset for user and handler."""
    return session.exec(
        select(Preset).where(
            col(Preset.userid) == userid,
            col(Preset.handler) == handler,
            col(Preset.is_default).is_(True),
        )
    ).first()


def create_preset(
    session: Session,
    userid: str,
    handler: str,
    title: str,
    title_template: str,
    labels: Optional[Label] = None,
    categories: Optional[str] = None,
    exclude_from_date_category: bool = False,
    is_default: bool = False,
) -> Preset:
    """Create new preset, clearing existing defaults if is_default=True."""
    if is_default:
        session.exec(
            update(Preset)
            .where(
                col(Preset.userid) == userid,
                col(Preset.handler) == handler,
                col(Preset.is_default),
            )
            .values(is_default=False)
        )

    preset = Preset(
        userid=userid,
        handler=handler,
        title=title,
        title_template=title_template,
        labels=labels,
        categories=categories,
        exclude_from_date_category=exclude_from_date_category,
        is_default=is_default,
    )
    session.add(preset)
    session.flush()

    logger.info(f"[dal] Created preset {preset.id} for {userid} handler={handler}")

    return preset


def update_preset(
    session: Session,
    preset_id: int,
    userid: str,
    title: str,
    title_template: str,
    labels: Optional[Label] = None,
    categories: Optional[str] = None,
    exclude_from_date_category: bool = False,
    is_default: bool = False,
) -> Optional[Preset]:
    """Update existing preset, clearing other defaults if is_default=True."""
    preset = session.get(Preset, preset_id)
    if not preset or preset.userid != userid:
        return None

    if is_default:
        session.exec(
            update(Preset)
            .where(
                col(Preset.userid) == userid,
                col(Preset.handler) == preset.handler,
                col(Preset.is_default),
                col(Preset.id) != preset_id,
            )
            .values(is_default=False)
        )

    preset.title = title
    preset.title_template = title_template
    preset.labels = labels
    preset.categories = categories
    preset.exclude_from_date_category = exclude_from_date_category
    preset.is_default = is_default
    session.add(preset)
    session.flush()

    logger.info(f"[dal] Updated preset {preset_id} for {userid}")

    return preset


def delete_preset(session: Session, preset_id: int, userid: str) -> bool:
    """Delete preset if owned by user."""
    preset = session.get(Preset, preset_id)
    if not preset or preset.userid != userid:
        return False

    session.delete(preset)
    session.flush()

    logger.info(f"[dal] Deleted preset {preset_id} for {userid}")

    return True
