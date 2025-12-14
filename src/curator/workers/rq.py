import os
import sys

from rq import Queue, Worker

from curator.app.config import redis_client

queue = Queue("ingest", connection=redis_client)


def start():
    if sys.platform == "darwin":
        os.environ.setdefault("NO_PROXY", "*")

    worker = Worker([queue], connection=redis_client)
    worker.work()


if __name__ == "__main__":
    start()
