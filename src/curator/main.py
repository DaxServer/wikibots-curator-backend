import asyncio
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starsessions import SessionAutoloadMiddleware, SessionMiddleware
from starsessions.stores.cookie import CookieStore

from alembic import command
from alembic.config import Config
from curator.admin import router as admin_router
from curator.app.config import TOKEN_ENCRYPTION_KEY
from curator.app.db import DB_URL
from curator.auth import router as auth_router
from curator.frontend_utils import frontend_dir, setup_frontend_assets
from curator.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    user = os.environ.get("TOOL_TOOLSDB_USER")
    password = os.environ.get("TOOL_TOOLSDB_PASSWORD")
    if not user or not password:
        yield
        return

    # Run database migrations
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    await asyncio.to_thread(command.upgrade, cfg, "head")

    # Download and set up frontend assets
    setup_frontend_assets()

    # Mount static files after frontend assets are set up
    assets_dir = os.path.join(frontend_dir, "dist/assets")
    if not os.path.exists(assets_dir):
        print(f"Assets directory not found at {assets_dir}")
        sys.exit(1)

    app.mount("/assets", StaticFiles(directory=assets_dir))
    app.add_api_route(
        "/",
        lambda: FileResponse(os.path.join(frontend_dir, "dist/index.html")),
        methods=["GET"],
    )

    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionAutoloadMiddleware)  # ty: ignore
app.add_middleware(
    SessionMiddleware,  # ty: ignore
    store=CookieStore(TOKEN_ENCRYPTION_KEY),
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            # "stacktrace": traceback.format_exc().splitlines(),
        },
    )


# Include the routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(ws_router)


def start(reload: bool = True):
    """
    Entry point for the application when run as a script.
    """
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "curator": {"handlers": ["default"], "level": "INFO", "propagate": True},
            "httpx": {"level": "WARNING", "propagate": True},
            "uvicorn": {"level": "WARNING", "propagate": True},
            "uvicorn.error": {"level": "ERROR"},
        },
    }

    uvicorn.run(
        "curator.main:app",
        host="0.0.0.0",
        reload=reload,
        port=8000,
        reload_dirs=["src/curator"],
        reload_excludes=["__pycache__"],
        log_level=level.lower(),
        log_config=log_config,
    )


if __name__ == "__main__":
    start(reload=False)
