from mwoauth import ConsumerToken, Handshaker, RequestToken
from fastapi import APIRouter, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import os
from typing import Optional


router = APIRouter(prefix="/auth", tags=["auth"])

consumer_token = ConsumerToken(
    os.environ.get("OAUTH_CLIENT_ID"), os.environ.get("OAUTH_CLIENT_SECRET")
)

handshaker = Handshaker(
    "https://commons.wikimedia.org/w/index.php",
    consumer_token,
    user_agent="Curator / Toolforge curator.toolforge.org / Wikimedia Commons User:DaxServer",
)


@router.get("/login")
async def login(request: Request):
    try:
        redirect, request_token = handshaker.initiate()
        request.session["request_token"] = request_token
        return RedirectResponse(url=redirect)
    except Exception as e:
        return HTMLResponse(f"Failed to initiate OAuth: {str(e)}", status_code=500)


@router.get("/callback")
async def auth(request: Request):
    if "request_token" not in request.session:
        return HTMLResponse("No request token in session", status_code=400)

    # Validate that we have the required callback parameters
    if not request.query_params.get("oauth_token") or not request.query_params.get(
        "oauth_verifier"
    ):
        return HTMLResponse("Missing required OAuth parameters", status_code=400)

    request_token = RequestToken(
        key=request.session["request_token"][0],
        secret=request.session["request_token"][1],
    )
    response_qs = str(request.url.query)

    try:
        access_token = handshaker.complete(request_token, response_qs)
        identity = handshaker.identify(access_token)
        request.session["user"] = dict(identity)

        # Clear the request token as it's no longer needed
        request.session.pop("request_token", None)

        return RedirectResponse(url="/")
    except ValueError as e:
        return HTMLResponse(f"Invalid OAuth response: {str(e)}", status_code=400)
    except Exception as e:
        return HTMLResponse(f"Authentication failed: {str(e)}", status_code=500)


@router.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    request.session.pop("request_token", None)
    return RedirectResponse(url="/")


@router.get("/whoami", name="whoami")
async def whoami(request: Request):
    user = request.session.get("user")
    if user:
        return JSONResponse(
            {
                "username": user.get("username"),
                "authorized": os.getenv("X_USERNAME") == user.get("username"),
            }
        )
    return JSONResponse({"message": "Not authenticated"}, status_code=401)


@router.post("/register")
async def register_api_key(
    request: Request, x_api_key: Optional[str] = Header(None, alias="X-API-KEY")
):
    env_api_key = os.environ.get("X_API_KEY")
    env_username = os.environ.get("X_USERNAME")

    if not env_api_key or not env_username:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Server configuration error: API key or username not set"
            },
        )

    if x_api_key is None:
        return JSONResponse(
            status_code=400, content={"detail": "Missing X-API-KEY header"}
        )

    if x_api_key == env_api_key:
        request.session["user"] = {"username": env_username}
        return JSONResponse(
            status_code=200,
            content={
                "message": "User registered successfully",
                "username": env_username,
            },
        )
    else:
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
