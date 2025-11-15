from celery import Celery
from curator.app.db import DB_URL

celery_app = Celery(
    "curator",
    include=["curator.workers.mapillary"],
)

celery_app.conf.update(
    broker_url=f"sqla+{DB_URL}",
    result_backend=f"db+{DB_URL}",
    result_extended=True,
    result_persistent=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3500,  # 58 minutes 20 seconds
)


def start():
    celery_app.worker_main(argv=["worker", "-P", "solo", "-l", "info"])


if __name__ == "__main__":
    start()
