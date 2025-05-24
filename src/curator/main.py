from fastapi import FastAPI

from curator.toolforge import router as toolforge_router

app = FastAPI()

# Include the toolforge router
app.include_router(toolforge_router)


@app.get("/")
async def root():
    """
    Root endpoint that returns a welcome message.
    """
    return {"message": "Welcome to the CuratorBot API"}


def start():
    """
    Entry point for the application when run as a script.
    """
    import uvicorn
    uvicorn.run("curator.main:app", host="0.0.0.0", reload=True)


if __name__ == "__main__":
    start()
