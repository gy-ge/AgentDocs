from collections.abc import Mapping
from typing import Protocol, Any


class TaskApiClient(Protocol):
    def pickup_next_task(self, agent_name: str) -> dict[str, Any] | None: ...

    def complete_task(
        self,
        task_id: int,
        *,
        result: str | None,
        error_message: str | None,
    ) -> dict[str, Any]: ...


def build_simulated_result(task: Mapping[str, Any], mode: str = "append") -> str:
    source_text = str(task.get("source_text") or "")
    instruction = str(task.get("instruction") or "").strip()

    if mode == "uppercase":
        return source_text.upper()

    suffix = " [simulated-agent]"
    if instruction:
        suffix = f" [simulated-agent: {instruction}]"

    if source_text.endswith("\n"):
        return f"{source_text[:-1]}{suffix}\n"
    return f"{source_text}{suffix}"


def process_next_task(
    api_client: TaskApiClient,
    *,
    agent_name: str,
    mode: str = "append",
) -> dict[str, Any] | None:
    task = api_client.pickup_next_task(agent_name)
    if task is None:
        return None

    if mode == "fail":
        return api_client.complete_task(
            task["id"],
            result=None,
            error_message="simulated agent failure",
        )

    result = build_simulated_result(task, mode=mode)
    return api_client.complete_task(task["id"], result=result, error_message=None)