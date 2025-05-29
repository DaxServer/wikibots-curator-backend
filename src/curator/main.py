import uvicorn
from fastapi import FastAPI

from curator.harbor import router as harbor_router
from curator.toolforge import router as toolforge_router

app = FastAPI()

# Include the routers
app.include_router(toolforge_router)
app.include_router(harbor_router)


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
