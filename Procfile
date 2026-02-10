web: python -m curator.main
worker: python -m curator.workers.celery
worker-privileged: WORKER_QUEUE=privileged python -m curator.workers.celery
worker-ratelimited: WORKER_QUEUE=normal python -m curator.workers.celery
