import logging
import os
import sys

from rq import Queue, Worker

from curator.app.config import redis_client

# Configure logging for the worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# Ensure curator logs are visible
logging.getLogger("curator").setLevel(logging.INFO)

queue = Queue("ingest", connection=redis_client)


def start():
    if sys.platform == "darwin":
        os.environ.setdefault("NO_PROXY", "*")

    worker = Worker([queue], connection=redis_client)
    worker.work(max_jobs=100, max_idle_time=3600 * 4) # 4 hours


if __name__ == "__main__":
    start()
