"""Tests for fair queue registration and worker lifecycle."""

from curator.workers.celery import (
    cleanup_user_queue_if_empty,
    on_task_postrun,
    register_user_queue,
    start,
)


def test_start_includes_active_user_queues(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_redis.smembers.return_value = {"uploads-user1", "uploads-user2"}
    mock_app = mocker.patch("curator.workers.celery.app")

    start()

    call_args = mock_app.worker_main.call_args[0][0]
    queues_arg = next(a for a in call_args if a.startswith("--queues="))
    queues = set(queues_arg.removeprefix("--queues=").split(","))
    assert queues == {"uploads-normal", "uploads-user1", "uploads-user2"}


def test_start_no_active_user_queues(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_redis.smembers.return_value = set()
    mock_app = mocker.patch("curator.workers.celery.app")

    start()

    call_args = mock_app.worker_main.call_args[0][0]
    queues_arg = next(a for a in call_args if a.startswith("--queues="))
    assert queues_arg == "--queues=uploads-normal"


def test_register_user_queue_new(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_redis.sadd.return_value = 1
    mock_app = mocker.patch("curator.workers.celery.app")

    register_user_queue("user42")

    mock_redis.sadd.assert_called_once_with(
        "curator:active_user_queues", "uploads-user42"
    )
    mock_app.control.add_consumer.assert_called_once_with("uploads-user42", reply=False)


def test_register_user_queue_existing(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_redis.sadd.return_value = 0
    mock_app = mocker.patch("curator.workers.celery.app")

    register_user_queue("user42")

    mock_app.control.add_consumer.assert_not_called()


def test_task_postrun_triggers_cleanup_for_process_upload(mocker):
    mock_cleanup = mocker.patch("curator.workers.celery.cleanup_user_queue_if_empty")
    mocker.patch("curator.workers.celery.task_counter")

    mock_task = mocker.MagicMock()
    mock_task.name = "curator.workers.tasks.process_upload"
    on_task_postrun(task=mock_task, args=[1, "eg1", "user42"])

    mock_cleanup.assert_called_once_with("user42")


def test_task_postrun_skips_cleanup_for_other_tasks(mocker):
    mock_cleanup = mocker.patch("curator.workers.celery.cleanup_user_queue_if_empty")
    mocker.patch("curator.workers.celery.task_counter")

    mock_task = mocker.MagicMock()
    mock_task.name = "curator.workers.tasks.some_other_task"
    on_task_postrun(task=mock_task, args=[1])

    mock_cleanup.assert_not_called()


def test_cleanup_user_queue_removes_when_empty(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_redis.srem.return_value = 1
    mock_app = mocker.patch("curator.workers.celery.app")
    mocker.patch(
        "curator.workers.celery.count_active_uploads_for_user",
        return_value=0,
    )

    cleanup_user_queue_if_empty("user42")

    mock_redis.srem.assert_called_once_with(
        "curator:active_user_queues", "uploads-user42"
    )
    mock_app.control.cancel_consumer.assert_called_once_with(
        "uploads-user42", reply=False
    )


def test_cleanup_user_queue_skips_when_uploads_remain(mocker):
    mock_redis = mocker.patch("curator.workers.celery.redis_client")
    mock_app = mocker.patch("curator.workers.celery.app")
    mocker.patch(
        "curator.workers.celery.count_active_uploads_for_user",
        return_value=3,
    )

    cleanup_user_queue_if_empty("user42")

    mock_redis.srem.assert_not_called()
    mock_app.control.cancel_consumer.assert_not_called()
