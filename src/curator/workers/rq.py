import logging
import os
import sys

from rq import Queue, Worker

from curator.app.config import redis_client

# Configure logging only for the worker process
# Avoid calling basicConfig to prevent affecting the main application logging
worker_logger = logging.getLogger(__name__)
worker_logger.setLevel(logging.INFO)

# Set levels for noisy libraries without basicConfig
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

queue = Queue("ingest", connection=redis_client)


def start():
    if sys.platform == "darwin":
        os.environ.setdefault("NO_PROXY", "*")

    worker = Worker([queue], connection=redis_client)
    worker.work(max_jobs=100, max_idle_time=3600 * 4)  # 4 hours


if __name__ == "__main__":
    start()
