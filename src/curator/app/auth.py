from typing import Annotated
from fastapi import Depends, HTTPException, status
from starlette.requests import HTTPConnection
from mwoauth import AccessToken


async def check_login(request: HTTPConnection):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    username: str | None = user_data.get("username")
    userid: str | None = user_data.get("sub")
    access_token: AccessToken | None = request.session.get("access_token")

    if not username or not userid or not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return {"username": username, "userid": userid, "access_token": access_token}


LoggedInUser = Annotated[dict, Depends(check_login)]
