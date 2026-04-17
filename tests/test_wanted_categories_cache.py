"""Unit tests for wanted_categories_cache."""

from unittest.mock import MagicMock, patch


def _make_conn(fetchone_value=None, fetchall_value=None):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = fetchone_value
    conn.execute.return_value.fetchall.return_value = fetchall_value or []
    return conn


def test_count_returns_total_rows():
    conn = _make_conn(fetchone_value=(42,))
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import count

        result = count()
    assert result == 42
    sql = conn.execute.call_args[0][0]
    assert "COUNT(*)" in sql
    assert "NOT contains" in sql


def test_query_passes_offset_to_sql():
    conn = _make_conn(fetchall_value=[])
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import query

        query(offset=200)
    sql = conn.execute.call_args[0][0]
    assert "OFFSET 200" in sql


def test_query_default_offset_is_zero():
    conn = _make_conn(fetchall_value=[])
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import query

        query()
    sql = conn.execute.call_args[0][0]
    assert "OFFSET 0" in sql


def test_query_with_filter_adds_like_clause():
    conn = _make_conn(fetchall_value=[])
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import query

        query(filter_text="Germany")
    sql, params = conn.execute.call_args[0]
    assert "lower(title) LIKE ?" in sql
    assert params == ["%germany%"]


def test_query_without_filter_omits_like_clause():
    conn = _make_conn(fetchall_value=[])
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import query

        query()
    sql = conn.execute.call_args[0][0]
    assert "lower(title)" not in sql


def test_count_with_filter_adds_like_clause():
    conn = _make_conn(fetchone_value=(5,))
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import count

        result = count(filter_text="Germany")
    assert result == 5
    sql, params = conn.execute.call_args[0]
    assert "lower(title) LIKE ?" in sql
    assert params == ["%germany%"]


def test_query_excludes_created_categories():
    conn = _make_conn(fetchall_value=[])
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import query

        query(excluded=set())
    sql = conn.execute.call_args[0][0]
    assert "created" in sql


def test_count_excludes_created_categories():
    conn = _make_conn(fetchone_value=(0,))
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import count

        count(excluded=set())
    sql = conn.execute.call_args[0][0]
    assert "created" in sql


def test_mark_created_updates_row():
    conn = MagicMock()
    with patch(
        "curator.db.wanted_categories_cache._get_duck_conn",
        return_value=conn,
    ):
        from curator.db.wanted_categories_cache import mark_created

        mark_created("Some_Category")
    conn.execute.assert_called_once()
    sql, params = conn.execute.call_args[0]
    assert "UPDATE" in sql
    assert "created" in sql
    assert params == ["Some_Category"]
