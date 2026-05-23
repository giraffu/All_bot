from dashboard.backend.schemas import WorkerHistoryItemResponse


def build_worker_history_item(log) -> WorkerHistoryItemResponse:
    return WorkerHistoryItemResponse(
        id=log.id,
        worker_id=log.worker_id,
        task_id=log.task_id,
        task_type=log.task_type,
        status=log.status,
        start_time=log.start_time.isoformat() if log.start_time else None,
        end_time=log.end_time.isoformat() if log.end_time else None,
        duration=log.duration,
        error_message=log.error_message,
    )
