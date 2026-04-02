import json
from dataclasses import dataclass
from itertools import count
from queue import Empty, Full, Queue
from threading import Lock
from typing import Iterator


@dataclass(frozen=True)
class TaskEventMessage:
    id: int
    event: str
    data: dict[str, object]


class TaskEventBroker:
    def __init__(self) -> None:
        self._event_ids = count(1)
        self._subscriber_ids = count(1)
        self._subscribers: dict[int, Queue[TaskEventMessage]] = {}
        self._lock = Lock()

    def publish(self, event: str, data: dict[str, object]) -> TaskEventMessage:
        message = TaskEventMessage(
            id=next(self._event_ids),
            event=event,
            data=data,
        )
        with self._lock:
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(message)
            except Full:
                try:
                    subscriber.get_nowait()
                except Empty:
                    pass
                try:
                    subscriber.put_nowait(message)
                except Full:
                    continue
        return message

    def publish_task(
        self,
        *,
        kind: str,
        task_id: int,
        doc_id: int,
        status: str,
        doc_revision: int,
        agent_name: str | None = None,
        document_changed: bool = False,
    ) -> TaskEventMessage:
        payload: dict[str, object] = {
            "kind": kind,
            "task_id": task_id,
            "doc_id": doc_id,
            "status": status,
            "doc_revision": doc_revision,
            "document_changed": document_changed,
        }
        if agent_name:
            payload["agent_name"] = agent_name
        return self.publish("task.changed", payload)

    def publish_tasks(
        self,
        *,
        kind: str,
        doc_id: int,
        doc_revision: int | None = None,
        document_changed: bool = False,
        accepted_task_ids: list[int] | None = None,
        skipped: int | None = None,
        cancelled: int | None = None,
        rejected: int | None = None,
    ) -> TaskEventMessage:
        payload: dict[str, object] = {
            "kind": kind,
            "doc_id": doc_id,
            "document_changed": document_changed,
        }
        if doc_revision is not None:
            payload["doc_revision"] = doc_revision
        if accepted_task_ids is not None:
            payload["accepted_task_ids"] = accepted_task_ids
        if skipped is not None:
            payload["skipped"] = skipped
        if cancelled is not None:
            payload["cancelled"] = cancelled
        if rejected is not None:
            payload["rejected"] = rejected
        return self.publish("tasks.changed", payload)

    def publish_document(
        self,
        *,
        kind: str,
        doc_id: int,
        revision: int | None,
    ) -> TaskEventMessage:
        payload: dict[str, object] = {
            "kind": kind,
            "doc_id": doc_id,
        }
        if revision is not None:
            payload["revision"] = revision
        return self.publish("document.changed", payload)

    def stream(self, *, heartbeat_seconds: float = 15.0) -> Iterator[str]:
        subscriber_id = next(self._subscriber_ids)
        subscriber: Queue[TaskEventMessage] = Queue(maxsize=128)
        with self._lock:
            self._subscribers[subscriber_id] = subscriber
        try:
            yield self._format_message(
                TaskEventMessage(
                    id=next(self._event_ids),
                    event="ready",
                    data={"stream": "tasks"},
                )
            )
            while True:
                try:
                    message = subscriber.get(timeout=heartbeat_seconds)
                except Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield self._format_message(message)
        finally:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

    def _format_message(self, message: TaskEventMessage) -> str:
        payload = json.dumps(message.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {message.id}\nevent: {message.event}\ndata: {payload}\n\n"


task_event_broker = TaskEventBroker()