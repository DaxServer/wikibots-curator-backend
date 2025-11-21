import sys
from unittest.mock import MagicMock, patch

# Mock pywikibot and its modules before importing curator.app.wcqs
sys.modules["pywikibot"] = MagicMock()
sys.modules["pywikibot.login"] = MagicMock()
sys.modules["pywikibot.data"] = MagicMock()
sys.modules["pywikibot.data.api"] = MagicMock()

import pytest
from datetime import datetime, timezone, timedelta
from curator.app.wcqs import WcqsSession
from curator.app.config import REDIS_PREFIX


@pytest.fixture
def mock_redis():
    with patch("curator.app.wcqs.redis_client") as mock:
        yield mock


@pytest.fixture
def mock_requests_session():
    with patch("requests.Session") as mock:
        yield mock.return_value


@pytest.fixture
def wcqs_session(mock_requests_session):
    request = MagicMock()
    request.session.get.return_value = "[]"
    return WcqsSession(request)


def test_query_success(wcqs_session, mock_redis, mock_requests_session):
    mock_redis.get.return_value = None
    mock_requests_session.post.return_value.status_code = 200
    mock_requests_session.post.return_value.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_session.post.return_value.json.return_value = {"results": {}}

    result = wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")
    assert result == {"results": {}}
    mock_requests_session.post.assert_called_once()
    mock_redis.get.assert_called_with(f"{REDIS_PREFIX}:wcqs:retry-after")


def test_query_rate_limited_in_redis(wcqs_session, mock_redis):
    future_time = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    mock_redis.get.return_value = future_time

    with pytest.raises(RuntimeError, match="Too many requests"):
        wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    mock_redis.get.assert_called_with(f"{REDIS_PREFIX}:wcqs:retry-after")


def test_query_rate_limited_response(wcqs_session, mock_redis, mock_requests_session):
    mock_redis.get.return_value = None
    mock_requests_session.post.return_value.status_code = 429
    mock_requests_session.post.return_value.headers = {"Retry-After": "30"}

    with pytest.raises(RuntimeError, match="Too many requests"):
        wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")

    mock_redis.setex.assert_called_once()
    args, _ = mock_redis.setex.call_args
    assert args[0] == f"{REDIS_PREFIX}:wcqs:retry-after"
    assert args[1] == 30


def test_query_retry_expired(wcqs_session, mock_redis, mock_requests_session):
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    mock_redis.get.return_value = past_time
    mock_requests_session.post.return_value.status_code = 200
    mock_requests_session.post.return_value.headers = {
        "Content-Type": "application/sparql-results+json;charset=utf-8"
    }
    mock_requests_session.post.return_value.json.return_value = {"results": {}}

    result = wcqs_session.query("SELECT * WHERE { ?s ?p ?o }")
    assert result == {"results": {}}
    mock_requests_session.post.assert_called_once()
    mock_redis.get.assert_called_with(f"{REDIS_PREFIX}:wcqs:retry-after")
