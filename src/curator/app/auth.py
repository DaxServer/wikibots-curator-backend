from typing import Annotated
from fastapi import Depends, HTTPException, Request, status
from mwoauth import AccessToken


async def check_login(request: Request):
    username: str | None = request.session.get("user", {}).get("username")
    userid: str | None = request.session.get("user", {}).get("sub")
    access_token: AccessToken | None = request.session.get("access_token")

    if not username or not userid or not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return {"username": username, "userid": userid, "access_token": access_token}


LoggedInUser = Annotated[dict, Depends(check_login)]
