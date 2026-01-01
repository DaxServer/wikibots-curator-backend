import logging
import os
import sys
from enum import Enum
from typing import Optional

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


class QueuePriority(Enum):
    """Queue priority levels."""

    URGENT = "urgent"
    NORMAL = "normal"
    LATER = "later"


# Create queues with different priorities
urgent_queue = Queue(QueuePriority.URGENT.value, connection=redis_client)
normal_queue = Queue(QueuePriority.NORMAL.value, connection=redis_client)
later_queue = Queue(QueuePriority.LATER.value, connection=redis_client)


def get_queue(priority: Optional[QueuePriority] = QueuePriority.NORMAL) -> Queue:
    """Get queue by priority. Defaults to normal priority."""
    if priority == QueuePriority.URGENT:
        return urgent_queue
    elif priority == QueuePriority.NORMAL:
        return normal_queue
    elif priority == QueuePriority.LATER:
        return later_queue
    else:
        return normal_queue


def start():
    """Start worker that listens to all queues in priority order."""
    if sys.platform == "darwin":
        os.environ.setdefault("NO_PROXY", "*")

    # Worker processes queues in order: urgent first, then normal, then later
    worker = Worker([urgent_queue, normal_queue, later_queue], connection=redis_client)
    worker.work(max_jobs=100, max_idle_time=3600 * 4)  # 4 hours


if __name__ == "__main__":
    start()
