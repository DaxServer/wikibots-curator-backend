import os
import secrets

from fastapi import FastAPI
import uvicorn

from curator.auth import router as auth_router
from curator.harbor import router as harbor_router
from curator.toolforge import router as toolforge_router

from starlette.middleware.sessions import SessionMiddleware


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get('SECRET_KEY', secrets.token_hex(32)))

# Include the routers
app.include_router(auth_router)
app.include_router(harbor_router)
app.include_router(toolforge_router)


@app.get("/")
async def root():
    """
    Root endpoint that returns a welcome message.
    """
    return {"message": "Welcome to the CuratorBot API"}


def start(reload: bool = True):
    """
    Entry point for the application when run as a script.
    """
    uvicorn.run("curator.main:app", host="0.0.0.0", reload=reload)


if __name__ == "__main__":
    start(reload=False)
