"""Tests for Wikimedia Commons Query Service integration."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from curator.app import wcqs
from curator.app.wcqs import WcqsSession


@pytest.fixture
def wcqs_session(mock_request):
    """Create a WcqsSession instance for testing"""
    return WcqsSession(mock_request)


def test_query_success(wcqs_session, mock_redis, mock_requests_response):
    """Test successful query execution"""
    # Setup
    mock_redis.get.return_value = None
    mock_requests_response.status_code = 200
    mock_requests_response.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_response.json.return_value = {"results": {}}

    # Execute
    with (
        patch.object(
            wcqs_session.session, "post", return_value=mock_requests_response
        ) as mock_post,
        patch.object(wcqs, "redis_client", mock_redis),
    ):
        result = wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    # Verify
    assert result == {"results": {}}
    mock_post.assert_called_once()
    mock_redis.get.assert_called_once()


def test_query_rate_limited_in_redis(wcqs_session, mock_redis, mock_requests_response):
    """Test query when rate limited in Redis"""
    # Setup
    future_time = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    mock_redis.get.return_value = future_time.encode("utf-8")
    mock_requests_response.status_code = 200
    mock_requests_response.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_response.json.return_value = {"results": {}}

    # Execute & Verify
    with (
        pytest.raises(RuntimeError, match="Too many requests"),
        patch.object(wcqs_session.session, "post", return_value=mock_requests_response),
        patch.object(wcqs, "redis_client", mock_redis),
    ):
        wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    mock_redis.get.assert_called_once()


def test_query_rate_limited_response(wcqs_session, mock_redis, mock_requests_response):
    """Test query when rate limited by response"""
    # Setup
    mock_redis.get.return_value = None
    mock_requests_response.status_code = 429
    mock_requests_response.headers = {"Retry-After": "30"}

    # Execute & Verify
    with (
        pytest.raises(RuntimeError, match="Too many requests"),
        patch.object(wcqs_session.session, "post", return_value=mock_requests_response),
        patch.object(wcqs, "redis_client", mock_redis),
    ):
        wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    mock_redis.setex.assert_called_once()
    args, _ = mock_redis.setex.call_args
    assert args[0] == "wcqs:retry-after"
    assert args[1] == 30


def test_query_retry_expired(wcqs_session, mock_redis, mock_requests_response):
    """Test query when retry time has expired"""
    # Setup
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    mock_redis.get.return_value = past_time.encode("utf-8")
    mock_requests_response.status_code = 200
    mock_requests_response.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_response.json.return_value = {"results": {}}

    # Execute
    with (
        patch.object(wcqs_session.session, "post", return_value=mock_requests_response),
        patch.object(wcqs, "redis_client", mock_redis),
    ):
        result = wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    # Verify
    assert result == {"results": {}}
    # When retry time has expired, the query should proceed normally
    # No delete call should be made since the expired time is just ignored
    mock_redis.delete.assert_not_called()


def test_query_invalid_json_response(wcqs_session, mock_redis, mock_requests_response):
    """Test query with invalid JSON response"""
    # Setup
    mock_redis.get.return_value = None
    mock_requests_response.status_code = 200
    mock_requests_response.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_response.json.side_effect = ValueError("Invalid JSON")

    # Execute & Verify
    with (
        pytest.raises(ValueError, match="Invalid JSON"),
        patch.object(wcqs_session.session, "post", return_value=mock_requests_response),
        patch.object(wcqs, "redis_client", mock_redis),
    ):
        wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")
