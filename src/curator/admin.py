from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from curator.app.dal import (
    count_all_upload_requests,
    count_batches,
    count_users,
    get_all_upload_requests,
    get_batches,
    get_users,
)
from curator.app.db import get_session


def check_admin(request: Request):
    username = request.session.get("user", {}).get("username")
    if username != "DaxServer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(check_admin)]
)


@router.get("/batches")
async def admin_get_batches(
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    items = get_batches(session, offset=offset, limit=limit)
    total = count_batches(session)
    return {"items": items, "total": total}


@router.get("/users")
async def admin_get_users(
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    items = get_users(session, offset=offset, limit=limit)
    total = count_users(session)
    return {"items": items, "total": total}


@router.get("/upload_requests")
async def admin_get_upload_requests(
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    offset = (page - 1) * limit
    items = get_all_upload_requests(session, offset=offset, limit=limit)
    total = count_all_upload_requests(session)
    return {"items": items, "total": total}
