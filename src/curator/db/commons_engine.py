import configparser
import logging
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Generator, TypedDict

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlmodel import create_engine

logger = logging.getLogger(__name__)

_COMMONS_HOST = "commonswiki.analytics.db.svc.wikimedia.cloud"
_TUNNEL_PORT = 4711
_TOOLFORGE_SSH = os.getenv("TOOLFORGE_SSH_HOST", "login.toolforge.org")

_env_user = os.getenv("TOOL_TOOLSDB_USER")
_env_password = os.getenv("TOOL_TOOLSDB_PASSWORD")
_AUTO_TUNNEL = not bool(_env_user)

if _env_user and _env_password:
    logger.info("Commons DB: using TOOL_TOOLSDB_USER/PASSWORD env vars")
    _commons_engine = create_engine(
        f"mysql+pymysql://{_env_user}:{_env_password}@{_COMMONS_HOST}/commonswiki_p",
        pool_recycle=280,
        pool_pre_ping=True,
    )
else:
    logger.info("Commons DB: tunnel mode — engine created lazily on first request")
    _commons_engine = None

_NAMESPACE_PREFIX_CASE = """
        CASE p_from.page_namespace
            WHEN 0  THEN ''
            WHEN 1  THEN 'Talk:'
            WHEN 2  THEN 'User:'
            WHEN 3  THEN 'User talk:'
            WHEN 4  THEN 'Commons:'
            WHEN 5  THEN 'Commons talk:'
            WHEN 6  THEN 'File:'
            WHEN 7  THEN 'File talk:'
            WHEN 8  THEN 'MediaWiki:'
            WHEN 9  THEN 'MediaWiki talk:'
            WHEN 10 THEN 'Template:'
            WHEN 11 THEN 'Template talk:'
            WHEN 12 THEN 'Help:'
            WHEN 13 THEN 'Help talk:'
            WHEN 14 THEN 'Category:'
            WHEN 15 THEN 'Category talk:'
            WHEN 100 THEN 'Creator:'
            WHEN 101 THEN 'Creator talk:'
            WHEN 102 THEN 'TimedText:'
            WHEN 103 THEN 'TimedText talk:'
            WHEN 104 THEN 'Sequence:'
            WHEN 105 THEN 'Sequence talk:'
            WHEN 106 THEN 'Institution:'
            WHEN 107 THEN 'Institution talk:'
            WHEN 460 THEN 'Campaign:'
            WHEN 461 THEN 'Campaign talk:'
            WHEN 486 THEN 'Data:'
            WHEN 487 THEN 'Data talk:'
            WHEN 828 THEN 'Module:'
            WHEN 829 THEN 'Module talk:'
            WHEN 1198 THEN 'Translations:'
            WHEN 1199 THEN 'Translations talk:'
            WHEN 1728 THEN 'Event:'
            WHEN 1729 THEN 'Event talk:'
            WHEN 2600 THEN 'Topic:'
            ELSE CONCAT(p_from.page_namespace, ':')
        END"""

_REDLINKS_SQL = text(f"""
    SELECT DISTINCT lt_title AS title,
        CONCAT(
            {_NAMESPACE_PREFIX_CASE},
            p_from.page_title
        ) AS linked_from
    FROM pagelinks pl
    JOIN linktarget ON pl.pl_target_id = lt_id
    LEFT JOIN page AS p_target ON (p_target.page_namespace = lt_namespace AND p_target.page_title = lt_title)
    JOIN page AS p_from ON p_from.page_id = pl.pl_from
    WHERE p_target.page_id IS NULL
      AND lt_namespace = 14
      AND NOT EXISTS (
          SELECT 1
          FROM templatelinks tl
          JOIN linktarget lt_tmpl ON tl.tl_target_id = lt_tmpl.lt_id
          JOIN page p_tmpl ON p_tmpl.page_title = lt_tmpl.lt_title AND p_tmpl.page_namespace = 10
          JOIN pagelinks pl_tmpl ON pl_tmpl.pl_from = p_tmpl.page_id AND pl_tmpl.pl_target_id = pl.pl_target_id
          WHERE tl.tl_from = pl.pl_from
      )
    LIMIT 100
""")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _read_bastion_credentials() -> tuple[str, str]:
    """Read replica.my.cnf credentials from the Toolforge bastion via SSH."""
    logger.info(f"Reading replica.my.cnf from {_TOOLFORGE_SSH}")
    result = subprocess.run(
        ["ssh", _TOOLFORGE_SSH, "cat ~/replica.my.cnf"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to read replica.my.cnf from bastion: {result.stderr.strip()}"
        )
    cfg = configparser.ConfigParser()
    cfg.read_string(result.stdout)
    user = cfg.get("client", "user")
    password = cfg.get("client", "password")
    return user, password


def _ensure_tunnel() -> None:
    """Start SSH tunnel and create engine lazily on first use. Tunnel is detached so it survives restarts."""
    global _commons_engine
    if _commons_engine is not None:
        return

    user, password = _read_bastion_credentials()

    if _port_open(_TUNNEL_PORT):
        logger.debug(f"SSH tunnel already open on port {_TUNNEL_PORT}")
    else:
        logger.info(
            f"Opening SSH tunnel to {_COMMONS_HOST} via {_TOOLFORGE_SSH} on port {_TUNNEL_PORT}"
        )
        subprocess.Popen(
            ["ssh", "-N", "-L", f"{_TUNNEL_PORT}:{_COMMONS_HOST}:3306", _TOOLFORGE_SSH],
            start_new_session=True,
        )
        for attempt in range(20):
            if _port_open(_TUNNEL_PORT):
                logger.info(f"SSH tunnel ready after {(attempt + 1) * 0.5:.1f}s")
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(
                f"SSH tunnel to {_COMMONS_HOST} failed to open on port {_TUNNEL_PORT}"
            )

    _commons_engine = create_engine(
        f"mysql+pymysql://{user}:{password}@127.0.0.1:{_TUNNEL_PORT}/commonswiki_p",
        pool_recycle=280,
        pool_pre_ping=True,
    )


@contextmanager
def get_commons_connection() -> Generator[Connection, None, None]:
    """Context manager for Commons replica DB connection."""
    if _AUTO_TUNNEL:
        _ensure_tunnel()
    if _commons_engine is None:
        raise RuntimeError("Commons DB not configured — set TOOL_TOOLSDB_USER/PASSWORD")
    with _commons_engine.connect() as conn:
        yield conn


_WANTED_CATEGORIES_SQL = text("""
    SELECT c.cat_title AS title,
        c.cat_subcats AS subcats,
        c.cat_files AS files,
        (c.cat_pages - c.cat_subcats - c.cat_files) AS pages,
        c.cat_pages AS total
    FROM category c
    LEFT JOIN page p ON p.page_namespace = 14 AND p.page_title = c.cat_title
    WHERE p.page_id IS NULL
    ORDER BY c.cat_pages DESC
    LIMIT 100
""")


class _WantedCategoryRow(TypedDict):
    title: str
    subcats: int
    files: int
    pages: int
    total: int


def get_wanted_categories() -> list[_WantedCategoryRow]:
    """Query Commons replica for category pages that are referenced but don't exist."""
    logger.info("Querying Commons replica for wanted categories")
    with get_commons_connection() as conn:
        rows = conn.execute(_WANTED_CATEGORIES_SQL).fetchall()
    logger.info(f"Wanted categories query returned {len(rows)} rows")
    return [
        {
            "title": row.title,
            "subcats": row.subcats,
            "files": row.files,
            "pages": row.pages,
            "total": row.total,
        }
        for row in rows
    ]


def get_redlinks() -> list[dict[str, str]]:
    """Query Commons replica for category redlinks not generated by template transclusions."""
    logger.info("Querying Commons replica for redlinks")
    with get_commons_connection() as conn:
        rows = conn.execute(_REDLINKS_SQL).fetchall()
    logger.info(f"Redlinks query returned {len(rows)} rows")
    return [{"title": row.title, "linked_from": row.linked_from} for row in rows]
