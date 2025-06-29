from contextlib import asynccontextmanager
import os
import secrets
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from curator.frontend_utils import frontend_dir, setup_frontend_assets
from curator.auth import router as auth_router
from curator.harbor import router as harbor_router
from curator.toolforge import router as toolforge_router

from starlette.middleware.sessions import SessionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_frontend_assets()

    # Mount static files after frontend assets are set up
    assets_dir = os.path.join(frontend_dir, 'dist/assets')
    if not os.path.exists(assets_dir):
        print(f"Assets directory not found at {assets_dir}")
        sys.exit(1)

    app.mount('/assets', StaticFiles(directory=assets_dir))
    app.add_api_route("/", lambda: FileResponse(os.path.join(frontend_dir, 'dist/index.html')), methods=["GET"])

    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SECRET_KEY', secrets.token_hex(32)))

# Include the routers
app.include_router(auth_router)
app.include_router(harbor_router)
app.include_router(toolforge_router)


def start(reload: bool = True):
    """
    Entry point for the application when run as a script.
    """
    uvicorn.run("curator.main:app", host="0.0.0.0", reload=reload, port=8000, reload_dirs=['src/curator'], reload_excludes=['__pycache__'])


if __name__ == "__main__":
    start(reload=False)
