"""BDD tests for worker.feature"""
from unittest.mock import PropertyMock

import curator.app.auth as auth_mod
from curator.app.commons import DuplicateUploadError
from curator.app.models import Batch, UploadRequest, User
from curator.asyncapi import Creator, Dates, ErrorLink, GeoLocation, MediaImage
from pytest_bdd import given, parsers, scenario, then, when

from .conftest import run_sync
from curator.workers.ingest import process_one


# --- Scenarios ---


@scenario("features/worker.feature", "Successfully processing a queued upload")
def test_worker_processing_scenario():
    pass


@scenario("features/worker.feature", "Handling a blacklisted title")
def test_worker_blacklist_scenario():
    pass


@scenario("features/worker.feature", "Handling a duplicate upload with SDC merge")
def test_worker_duplicate_scenario():
    pass


# --- GIVENS ---


@given(
    parsers.re(r'I am a logged-in user with id "(?P<userid>[^"]+)"'),
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


@given(
    parsers.parse('an upload request exists with status "{status}" and key "{key}"')
)
def step_given_upload_req(engine, status, key):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))

        # Use existing batch or create one
        b = s.get(Batch, 1)  # Try to get batch with id=1
        if not b:
            # Create a batch for the upload request
            b = Batch(id=1, userid="12345")
            s.add(b)
            s.commit()

        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status=status,
                key=key,
                handler="mapillary",
                filename=f"{key}.jpg",
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


@given(parsers.parse('the title "{title}" is on the Commons blacklist'))
def step_given_bl(mocker, title):
    mocker.patch(
        "curator.workers.ingest.check_title_blacklisted",
        return_value=(True, "blacklisted"),
    )


@given("the file already exists on Commons")
def step_given_dup(mocker):
    e = DuplicateUploadError(
        duplicates=[ErrorLink(title="D.jpg", url="http://d")], message="D"
    )
    mocker.patch("curator.workers.ingest.upload_file_chunked", side_effect=e)
    mocker.patch(
        "curator.workers.ingest._handle_duplicate_with_sdc_merge",
        return_value=("http://d", "duplicated_sdc_updated"),
    )


@given(parsers.parse('an upload request exists with status "{status}" and title "{title}"'))
def step_given_upload_title(engine, status, title):
    from sqlmodel import Session

    with Session(engine) as s:
        s.merge(User(userid="12345", username="testuser"))
        b = Batch(userid="12345")
        s.add(b)
        s.commit()
        s.refresh(b)
        s.add(
            UploadRequest(
                batchid=b.id,
                userid="12345",
                status=status,
                key="img-t",
                handler="mapillary",
                filename=title,
                wikitext="W",
                access_token="E",
            )
        )
        s.commit()


# --- WHENS ---


@when("the ingestion worker processes this upload request")
def when_worker(engine, event_loop):
    from sqlmodel import select, Session

    with Session(engine) as s:
        up = s.exec(
            select(UploadRequest).where(UploadRequest.status == "queued")
        ).first()
        assert up is not None
        uid = up.id
    run_sync(process_one(uid, "test_edit_group_abc123"), event_loop)


# --- THENS ---


@then('the upload status should be updated to "completed" in the database')
def then_worker_completed(engine):
    from sqlmodel import select, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert u is not None


@then("the success URL should be recorded for the request")
def then_worker_success(engine):
    from sqlmodel import select, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert u.success is not None


@then("the access token for this request should be cleared for security")
def then_token_cleared(engine):
    from sqlmodel import select, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "completed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert u.access_token is None


@then('the upload status should be updated to "failed"')
def then_worker_failed(engine):
    from sqlmodel import select, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "failed")
        ).first()
        assert u is not None


@then(parsers.parse('the error message should include "{text}"'))
def then_worker_err(engine, text):
    from sqlmodel import select, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(UploadRequest.status == "failed")
        ).first()
        assert isinstance(u, UploadRequest)
        assert text.lower() in str(u.error).lower()


@then("the SDC should be merged with the existing file")
@then(parsers.parse('the upload status should be "{status1}" or "{status2}"'))
def then_dup_merge(
    engine, status1="duplicated_sdc_updated", status2="duplicated_sdc_not_updated"
):
    from sqlmodel import select, col, Session

    with Session(engine) as s:
        u = s.exec(
            select(UploadRequest).where(
                col(UploadRequest.status).in_([status1, status2])
            )
        ).first()
        assert u is not None
