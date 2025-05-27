import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from curator.toolforge import router as toolforge_router

app = FastAPI()

# Include the toolforge router
app.include_router(toolforge_router)

# Get the project root directory (two levels up from this file)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
static_dir = os.path.join(project_root, "frontend", "dist")

# Mount the static files directory
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


@app.get("/")
async def root():
    """
    Root endpoint that serves the frontend or returns a welcome message.
    """
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to the CuratorBot API"}


def start(reload: bool = True):
    """
    Entry point for the application when run as a script.
    """
    uvicorn.run("curator.main:app", host="0.0.0.0", reload=reload)


if __name__ == "__main__":
    start(reload=False)
