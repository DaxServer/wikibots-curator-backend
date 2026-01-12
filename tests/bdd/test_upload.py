"""BDD tests for upload.feature"""
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import curator.app.auth as auth_mod
from curator.app.handler import Handler
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import UploadItem, UploadSliceData
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync


# --- Scenarios ---


@scenario("features/upload.feature", "Creating a new batch")
def test_create_batch_scenario():
    pass


@scenario("features/upload.feature", "Uploading multiple images to a batch")
def test_upload_slice_scenario():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
    target_fixture="active_user",
)
@given(
    parsers.re(
        r'I have an active session for "(?P<username>[^"]+)" with id "(?P<userid>[^"]+)"'
    ),
    target_fixture="active_user",
)
def step_given_user(userid, mocker, username="testuser"):
    u = {"username": username, "userid": userid, "sub": userid, "access_token": "v"}
    from curator.main import app

    app.dependency_overrides[auth_mod.check_login] = lambda: u
    mocker.patch(
        "starlette.requests.Request.session",
        new_callable=PropertyMock,
        return_value={"user": u},
    )
    return u


# --- WHENS ---


@when("I request to create a new batch", target_fixture="created_batch_id")
def when_create(active_user, mock_sender, event_loop):
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.create_batch(), event_loop)
    return mock_sender.send_batch_created.call_args[0][0]


@when(
    parsers.parse("I upload a slice with {count:d} images to batch {batch_id:d}"),
    target_fixture="u_res",
)
def when_upload(active_user, mock_sender, count, batch_id, mocker, event_loop):
    mock_d = mocker.patch("curator.app.handler.process_upload.delay")
    items = [
        UploadItem(id=f"img{i}", input=f"in{i}", title=f"T{i}", wikitext="W")
        for i in range(count)
    ]
    data = UploadSliceData(
        batchid=batch_id, sliceid=1, handler="mapillary", items=items
    )
    h = Handler(active_user, mock_sender, MagicMock())
    run_sync(h.upload_slice(data), event_loop)
    return {"delay": mock_d}


# --- THENS ---


@then("a new batch should exist in the database for my user")
def then_batch_exists(engine, active_user, created_batch_id):
    from sqlmodel import select, Session

    with Session(engine) as s:
        b = s.exec(select(Batch).where(Batch.id == created_batch_id)).first()
        assert b is not None
        assert b.userid == active_user["userid"]


@then("I should receive a message with the new batch id")
def then_batch_msg(mock_sender, created_batch_id):
    mock_sender.send_batch_created.assert_called_once_with(created_batch_id)


@then(
    parsers.parse(
        "{count:d} upload requests should be created in the database for batch {batch_id:d}"
    )
)
def then_req_count(engine, count, batch_id):
    from sqlmodel import select, Session

    with Session(engine) as s:
        ups = s.exec(
            select(UploadRequest).where(UploadRequest.batchid == batch_id)
        ).all()
        assert len(ups) == count


@then(
    parsers.parse("these {count:d} uploads should be enqueued for background processing")
)
def then_enqueued(u_res, count):
    assert u_res["delay"].call_count == count


@then(parsers.parse("I should receive an acknowledgment for slice {slice_id:d}"))
def then_ack(mock_sender, slice_id):
    mock_sender.send_upload_slice_ack.assert_called_once()
    # Verify the correct slice_id was acknowledged
    call_kwargs = mock_sender.send_upload_slice_ack.call_args.kwargs
    assert call_kwargs.get("sliceid") == slice_id
