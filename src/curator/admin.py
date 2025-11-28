from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.orm import Session

from curator.app.db import get_session
from curator.app.dal import (
    get_batches,
    count_batches,
    get_users,
    count_users,
    get_all_upload_requests,
    count_all_upload_requests,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def check_admin(request: Request):
    username = request.session.get("user", {}).get("username")
    if username != "DaxServer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


@router.get("/batches")
async def admin_get_batches(
    request: Request,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    check_admin(request)
    offset = (page - 1) * limit
    items = get_batches(session, offset=offset, limit=limit)
    total = count_batches(session)
    return {"items": items, "total": total}


@router.get("/users")
async def admin_get_users(
    request: Request,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    check_admin(request)
    offset = (page - 1) * limit
    items = get_users(session, offset=offset, limit=limit)
    total = count_users(session)
    return {"items": items, "total": total}


@router.get("/upload_requests")
async def admin_get_upload_requests(
    request: Request,
    page: int = 1,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    check_admin(request)
    offset = (page - 1) * limit
    items = get_all_upload_requests(session, offset=offset, limit=limit)
    total = count_all_upload_requests(session)
    return {"items": items, "total": total}
