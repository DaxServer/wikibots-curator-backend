import configparser
import logging
import os
import socket
import subprocess
import time
from contextlib import contextmanager
from typing import Generator

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
