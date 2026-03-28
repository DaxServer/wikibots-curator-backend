"""Tests for startup recovery of queued uploads after Redis restart."""

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from mwoauth import AccessToken as MWAccessToken

from curator.app.recovery import SENTINEL_KEY, recover_queued_uploads


@pytest.mark.asyncio
async def test_skips_recovery_when_sentinel_key_present(mocker):
    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = None
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_sets_sentinel_key_when_no_queued_uploads(mocker):
    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=[]
    )
    mocker.patch("curator.app.recovery.enqueue_uploads", new_callable=AsyncMock)

    await recover_queued_uploads()

    mock_redis.set.assert_called_once_with(SENTINEL_KEY, "1", nx=True)


@pytest.mark.asyncio
async def test_reenqueues_queued_uploads_after_redis_restart(mocker):
    queued = [
        (1, "user1", "cipher1", "eg1"),
        (2, "user1", "cipher1", "eg1"),
    ]
    mock_token = MWAccessToken("key", "secret")

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch("curator.app.recovery.decrypt_access_token", return_value=mock_token)
    mock_client = MagicMock()
    mock_client.get_user_groups.return_value = set()
    mocker.patch("curator.app.recovery.MediaWikiClient", return_value=mock_client)
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    mock_enqueue.assert_called_once_with(
        upload_ids=[1, 2],
        edit_group_id="eg1",
        userid="user1",
        access_token=mock_token,
    )


@pytest.mark.asyncio
async def test_groups_uploads_by_userid_and_batch(mocker):
    queued = [
        (1, "user1", "cipher1", "eg1"),
        (2, "user2", "cipher2", "eg2"),
    ]
    mock_token1 = MWAccessToken("key1", "secret1")
    mock_token2 = MWAccessToken("key2", "secret2")

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch(
        "curator.app.recovery.decrypt_access_token",
        side_effect=lambda *args, **kwargs: (
            mock_token1 if args[0] == "cipher1" else mock_token2
        ),
    )
    mock_client = MagicMock()
    mock_client.get_user_groups.return_value = set()
    mocker.patch("curator.app.recovery.MediaWikiClient", return_value=mock_client)
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    assert mock_enqueue.call_count == 2


@pytest.mark.asyncio
async def test_marks_uploads_failed_when_token_is_corrupted(mocker):
    queued = [(1, "user1", "bad_cipher", "eg1")]

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch(
        "curator.app.recovery.decrypt_access_token",
        side_effect=Exception("invalid token"),
    )
    mock_fail = mocker.patch("curator.app.recovery.mark_uploads_expired")
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    mock_fail.assert_called_once_with(ANY, [1])
    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_marks_uploads_failed_when_oauth_token_is_invalid(mocker):
    queued = [(1, "user1", "cipher1", "eg1")]
    mock_token = MWAccessToken("key", "secret")

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch("curator.app.recovery.decrypt_access_token", return_value=mock_token)
    mock_client = MagicMock()
    mock_client.get_user_groups.side_effect = Exception("401 Unauthorized")
    mocker.patch("curator.app.recovery.MediaWikiClient", return_value=mock_client)
    mock_fail = mocker.patch("curator.app.recovery.mark_uploads_expired")
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    mock_fail.assert_called_once_with(ANY, [1])
    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_continues_recovering_valid_groups_after_invalid_token(mocker):
    queued = [
        (1, "user1", "bad_cipher", "eg1"),
        (2, "user2", "cipher2", "eg2"),
    ]
    mock_token2 = MWAccessToken("key2", "secret2")
    mock_client = MagicMock()
    mock_client.get_user_groups.return_value = set()

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch(
        "curator.app.recovery.decrypt_access_token",
        side_effect=lambda cipher: (
            (_ for _ in ()).throw(Exception("invalid"))
            if cipher == "bad_cipher"
            else mock_token2
        ),
    )
    mocker.patch("curator.app.recovery.MediaWikiClient", return_value=mock_client)
    mock_fail = mocker.patch("curator.app.recovery.mark_uploads_expired")
    mock_enqueue = mocker.patch(
        "curator.app.recovery.enqueue_uploads", new_callable=AsyncMock
    )

    await recover_queued_uploads()

    mock_fail.assert_called_once_with(ANY, [1])
    mock_enqueue.assert_called_once()
    mock_redis.set.assert_called_once_with(SENTINEL_KEY, "1", nx=True)


@pytest.mark.asyncio
async def test_marks_all_expired_uploads_in_single_session_call(mocker):
    queued = [
        (1, "user1", "bad_cipher1", "eg1"),
        (2, "user2", "bad_cipher2", "eg2"),
    ]

    mock_redis = mocker.patch("curator.app.recovery.redis_client")
    mock_redis.set.return_value = True
    mocker.patch("curator.app.recovery.get_session", MagicMock())
    mocker.patch(
        "curator.app.recovery.get_queued_uploads_for_recovery", return_value=queued
    )
    mocker.patch(
        "curator.app.recovery.decrypt_access_token", side_effect=Exception("invalid")
    )
    mock_fail = mocker.patch("curator.app.recovery.mark_uploads_expired")
    mocker.patch("curator.app.recovery.enqueue_uploads", new_callable=AsyncMock)

    await recover_queued_uploads()

    mock_fail.assert_called_once()
    assert sorted(mock_fail.call_args[0][1]) == [1, 2]
