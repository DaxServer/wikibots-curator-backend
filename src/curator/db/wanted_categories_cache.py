import asyncio
import csv
import logging
import os
import tempfile
import threading
import time

import duckdb

from curator.core.config import WANTED_CATEGORIES_DUCKDB_PATH, redis_client
from curator.db.commons_engine import WantedCategoryRow, get_all_wanted_categories

logger = logging.getLogger(__name__)

WANTED_CATEGORIES_LOCK_KEY = "curator:wanted_categories:lock"

# TODO: replace with Redis SMEMBERS per user when filter UI is added
EXCLUDED_WANTED_CATEGORIES: set[str] = {
    "TODO",
    "Maps_showing_",
    "_maps_of_",
    "Demographics_of_",
    "_Mapillary_",
    "Orthophotos_of_",
    "ДА_",
    "Lingua_Libre_",
    "Files_uploaded_by_NguoiDungKhongDinhDanh",
    "in_Boston",
    "in_the_Northern_Hemisphere",
}

_QUERY_LIMIT = 100
_LOCK_TTL = 3600

_duck_conn: duckdb.DuckDBPyConnection | None = None
_duck_lock = threading.Lock()


def _get_duck_conn() -> duckdb.DuckDBPyConnection:
    """Return module-level DuckDB connection, opening lazily."""
    global _duck_conn
    if _duck_conn is None:
        _duck_conn = duckdb.connect(WANTED_CATEGORIES_DUCKDB_PATH)
    return _duck_conn


def _reload_duck_conn() -> None:
    """Close and reopen the DuckDB connection after a file refresh."""
    global _duck_conn
    if _duck_conn is not None:
        _duck_conn.close()
        _duck_conn = None
    _duck_conn = duckdb.connect(WANTED_CATEGORIES_DUCKDB_PATH)


def is_ready() -> bool:
    """Return True if the DuckDB cache file exists."""
    return os.path.exists(WANTED_CATEGORIES_DUCKDB_PATH)


def populate() -> None:
    """Fetch all wanted categories from MySQL and write to DuckDB."""
    logger.info("DuckDB populate: querying Commons replica (no limit)")
    t0 = time.monotonic()
    sql_rows = get_all_wanted_categories()
    fetch_secs = time.monotonic() - t0
    logger.info(f"DuckDB populate: fetched {len(sql_rows):,} rows in {fetch_secs:.1f}s")

    logger.info(
        f"DuckDB populate: writing {len(sql_rows):,} rows to {WANTED_CATEGORIES_DUCKDB_PATH}"
    )
    t1 = time.monotonic()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_path = f.name
        writer = csv.writer(f)
        for r in sql_rows:
            writer.writerow(
                [r["title"], r["subcats"], r["files"], r["pages"], r["total"]]
            )
    csv_secs = time.monotonic() - t1
    logger.info(f"DuckDB populate: CSV written in {csv_secs:.1f}s")

    with _duck_lock:
        _reload_duck_conn()
        conn = _get_duck_conn()
        conn.execute("DROP TABLE IF EXISTS wanted_categories")
        conn.execute(f"""
            CREATE TABLE wanted_categories AS
            SELECT column0 AS title, column1 AS subcats, column2 AS files, column3 AS pages, column4 AS total,
                   FALSE AS created
            FROM read_csv('{tmp_path}', header=false,
                columns={{'column0': 'VARCHAR', 'column1': 'INTEGER', 'column2': 'INTEGER',
                          'column3': 'INTEGER', 'column4': 'INTEGER'}})
        """)
    os.unlink(tmp_path)

    write_secs = time.monotonic() - t1
    logger.info(
        f"DuckDB populate: done — {len(sql_rows):,} rows written in {write_secs:.1f}s "
        f"(total {fetch_secs + write_secs:.1f}s)"
    )


def mark_created(title: str) -> None:
    """Mark a category as created so it is excluded from future queries."""
    with _duck_lock:
        _get_duck_conn().execute(
            "UPDATE wanted_categories SET created = TRUE WHERE title = ?", [title]
        )


def query(
    excluded: set[str] = EXCLUDED_WANTED_CATEGORIES,
    limit: int = _QUERY_LIMIT,
    offset: int = 0,
    filter_text: str | None = None,
) -> list[WantedCategoryRow]:
    """Query wanted categories from DuckDB with exclusion filter."""
    conditions = [
        "NOT created",
        *[f"NOT contains(title, '{term}')" for term in excluded],
    ]
    params: list[str] = []
    if filter_text:
        conditions.append("lower(title) LIKE ?")
        params.append(f"%{filter_text.lower()}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    t0 = time.monotonic()
    with _duck_lock:
        rows = (
            _get_duck_conn()
            .execute(
                f"SELECT title, subcats, files, pages, total FROM wanted_categories {where} ORDER BY total DESC LIMIT {limit} OFFSET {offset}",
                params,
            )
            .fetchall()
        )
    logger.info(
        f"DuckDB query: returned {len(rows)} rows in {time.monotonic() - t0:.3f}s"
    )
    return [
        {"title": r[0], "subcats": r[1], "files": r[2], "pages": r[3], "total": r[4]}
        for r in rows
    ]


def count(
    excluded: set[str] = EXCLUDED_WANTED_CATEGORIES,
    filter_text: str | None = None,
) -> int:
    """Return total wanted category rows after applying exclusion filter."""
    conditions = [
        "NOT created",
        *[f"NOT contains(title, '{term}')" for term in excluded],
    ]
    params: list[str] = []
    if filter_text:
        conditions.append("lower(title) LIKE ?")
        params.append(f"%{filter_text.lower()}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _duck_lock:
        row = (
            _get_duck_conn()
            .execute(f"SELECT COUNT(*) FROM wanted_categories {where}", params)
            .fetchone()
        )
    return row[0] if row else 0


async def populate_with_lock() -> None:
    """Populate the DuckDB cache, guarded by a Redis lock."""
    acquired = await asyncio.to_thread(
        lambda: redis_client.set(WANTED_CATEGORIES_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL)
    )
    if not acquired:
        logger.info("DuckDB populate: skipped — lock already held")
        return
    logger.info("DuckDB populate: lock acquired, starting background populate")
    try:
        await asyncio.to_thread(populate)
    except Exception:
        logger.exception("DuckDB populate: failed")
        raise
    finally:
        await asyncio.to_thread(lambda: redis_client.delete(WANTED_CATEGORIES_LOCK_KEY))
    logger.info("DuckDB populate: lock released")
