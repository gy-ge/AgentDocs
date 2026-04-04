import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / ".agentdocs.config.json"


class AgentDocsClientError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.status is not None:
            payload["error"]["status"] = self.status
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


def build_cli_success(
    *, command: str, data: Any, event: str | None = None
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "command": command,
        "data": data,
    }
    if event is not None:
        payload["event"] = event
    return payload


def _raise_api_error(*, status: int | None, body_text: str) -> None:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise AgentDocsClientError(
            code="http_error",
            message=body_text or "request failed",
            status=status,
        ) from exc

    error_payload = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error_payload, dict):
        raise AgentDocsClientError(
            code=str(error_payload.get("code") or "api_error"),
            message=str(error_payload.get("message") or "request failed"),
            status=status,
            details=error_payload.get("details"),
        )

    raise AgentDocsClientError(
        code="invalid_response",
        message="request failed",
        status=status,
        details=parsed,
    )


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def has_saved_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> bool:
    return Path(config_path).exists()


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"missing config file: {path}. Run the setup command first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(
    *,
    base_url: str,
    api_key: str,
    agent_name: str,
    timeout: float = 10.0,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "base_url": _normalize_base_url(base_url),
        "api_key": api_key,
        "agent_name": agent_name,
        "timeout": timeout,
    }
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "config_path": path.name,
        "base_url": config["base_url"],
        "agent_name": config["agent_name"],
        "timeout": config["timeout"],
        "api_key_saved": True,
    }


def resolve_config(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    base_url: str | None = None,
    api_key: str | None = None,
    agent_name: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    saved = load_config(config_path)
    resolved = {
        "base_url": _normalize_base_url(str(base_url or saved.get("base_url") or "")),
        "api_key": str(api_key or saved.get("api_key") or ""),
        "agent_name": str(agent_name or saved.get("agent_name") or ""),
        "timeout": float(
            timeout if timeout is not None else saved.get("timeout", 10.0)
        ),
    }
    if not resolved["base_url"]:
        raise ValueError("missing base_url")
    if not resolved["api_key"]:
        raise ValueError("missing api_key")
    if not resolved["agent_name"]:
        raise ValueError("missing agent_name")
    return resolved


def _json_request(
    base_url: str,
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> Any:
    body = None
    response_payload: dict[str, Any] = {}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "AgentDocsSkillClient/1.0",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = request.Request(
        f"{_normalize_base_url(base_url)}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8")
        _raise_api_error(status=exc.code, body_text=details or exc.reason)

    if response_payload.get("ok") is not True:
        _raise_api_error(
            status=None,
            body_text=json.dumps(response_payload, ensure_ascii=False),
        )
    return response_payload.get("data")


def build_result(task: dict[str, Any], *, mode: str) -> str:
    source_text = str(task.get("source_text") or "")
    instruction = str(task.get("instruction") or "").strip()

    if mode == "uppercase":
        return source_text.upper()

    suffix = " [agentdocs-skill]"
    if instruction:
        suffix = f" [agentdocs-skill: {instruction}]"

    if source_text.endswith("\n"):
        return f"{source_text[:-1]}{suffix}\n"
    return f"{source_text}{suffix}"


def build_complete_payload(
    *, result: str | None, error_message: str | None
) -> dict[str, Any]:
    if (result is None) == (error_message is None):
        raise ValueError("provide exactly one of result or error_message")
    return {"result": result, "error_message": error_message}


def build_recover_payload(*, mode: str, actor: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"mode": mode}
    if actor:
        payload["actor"] = actor
    return payload


class AgentDocsClient:
    def __init__(self, *, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.api_key = api_key
        self.timeout = timeout

    def pickup_next_task(self, agent_name: str) -> dict[str, Any] | None:
        return _json_request(
            self.base_url,
            self.api_key,
            "/api/tasks/next",
            method="POST",
            payload={"agent_name": agent_name},
            timeout=self.timeout,
        )

    def get_task(self, task_id: int) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}",
            timeout=self.timeout,
        )

    def get_task_diff(self, task_id: int) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}/diff",
            timeout=self.timeout,
        )

    def get_task_recovery_preview(self, task_id: int) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}/recovery-preview",
            timeout=self.timeout,
        )

    def complete_task(
        self,
        task_id: int,
        *,
        result: str | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}/complete",
            method="POST",
            payload=build_complete_payload(result=result, error_message=error_message),
            timeout=self.timeout,
        )

    def relocate_task(self, task_id: int) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}/relocate",
            method="POST",
            timeout=self.timeout,
        )

    def recover_task(
        self,
        task_id: int,
        *,
        mode: str,
        actor: str | None = None,
    ) -> dict[str, Any]:
        return _json_request(
            self.base_url,
            self.api_key,
            f"/api/tasks/{task_id}/recover",
            method="POST",
            payload=build_recover_payload(mode=mode, actor=actor),
            timeout=self.timeout,
        )


def setup_runtime(
    *,
    base_url: str,
    api_key: str,
    agent_name: str,
    timeout: float = 10.0,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    return save_config(
        base_url=base_url,
        api_key=api_key,
        agent_name=agent_name,
        timeout=timeout,
        config_path=config_path,
    )


def pickup_one_task(
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    agent_name: str | None = None,
) -> dict[str, Any] | None:
    config = resolve_config(config_path=config_path, agent_name=agent_name)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.pickup_next_task(str(config["agent_name"]))


def complete_one_task(
    *,
    task_id: int,
    result: str | None,
    error_message: str | None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.complete_task(
        int(task_id),
        result=result,
        error_message=error_message,
    )


def get_one_task(
    *, task_id: int, config_path: str | Path = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.get_task(int(task_id))


def get_task_diff(
    *, task_id: int, config_path: str | Path = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.get_task_diff(int(task_id))


def get_task_recovery_preview(
    *, task_id: int, config_path: str | Path = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.get_task_recovery_preview(int(task_id))


def relocate_one_task(
    *, task_id: int, config_path: str | Path = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.relocate_task(int(task_id))


def recover_one_task(
    *,
    task_id: int,
    mode: str,
    actor: str | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    config = resolve_config(config_path=config_path)
    client = AgentDocsClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=float(config["timeout"]),
    )
    return client.recover_task(int(task_id), mode=mode, actor=actor)


def run_continuous(
    *,
    mode: str = "append",
    poll_interval: float = 2.0,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    agent_name: str | None = None,
) -> dict[str, Any]:
    processed = 0
    idle_loops = 0

    while True:
        completed_task = process_one_task(
            mode=mode,
            config_path=config_path,
            agent_name=agent_name,
        )
        if completed_task is None:
            idle_loops += 1
            time.sleep(poll_interval)
            continue

        processed += 1
        idle_loops = 0
        print(
            json.dumps(
                build_cli_success(
                    command="continuous",
                    event="task_processed",
                    data=completed_task,
                ),
                ensure_ascii=False,
            ),
            flush=True,
        )

    return {"processed": processed, "idle_loops": idle_loops}


def process_one_task(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    agent_name: str | None = None,
    mode: str = "append",
    timeout: float = 10.0,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any] | None:
    if base_url is None or api_key is None or agent_name is None:
        config = resolve_config(
            config_path=config_path,
            base_url=base_url,
            api_key=api_key,
            agent_name=agent_name,
            timeout=timeout,
        )
    else:
        config = {
            "base_url": _normalize_base_url(base_url),
            "api_key": api_key,
            "agent_name": agent_name,
            "timeout": timeout,
        }

    client = AgentDocsClient(
        base_url=str(config["base_url"]),
        api_key=str(config["api_key"]),
        timeout=float(config["timeout"]),
    )
    task = client.pickup_next_task(str(config["agent_name"]))
    if task is None:
        return None

    if mode == "fail":
        return client.complete_task(
            int(task["id"]),
            result=None,
            error_message="agentdocs skill client simulated failure",
        )

    return client.complete_task(
        int(task["id"]),
        result=build_result(task, mode=mode),
        error_message=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use a saved AgentDocs configuration for setup, pickup, completion, and processing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser(
        "setup", help="Save AgentDocs connection settings"
    )
    setup_parser.add_argument("--base-url", required=True)
    setup_parser.add_argument("--api-key", required=True)
    setup_parser.add_argument("--agent-name", required=True)
    setup_parser.add_argument("--timeout", type=float, default=10.0)
    setup_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    show_config_parser = subparsers.add_parser(
        "show-config", help="Show whether saved AgentDocs config exists"
    )
    show_config_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    get_task_parser = subparsers.add_parser("get-task", help="Fetch one task")
    get_task_parser.add_argument("--task-id", type=int, required=True)
    get_task_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    pickup_parser = subparsers.add_parser("pickup", help="Pick up one pending task")
    pickup_parser.add_argument("--agent-name", default=None)
    pickup_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    complete_parser = subparsers.add_parser(
        "complete", help="Complete one processing task"
    )
    complete_parser.add_argument("--task-id", type=int, required=True)
    complete_parser.add_argument("--result", default=None)
    complete_parser.add_argument("--error-message", default=None)
    complete_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    diff_parser = subparsers.add_parser("diff", help="Fetch a finished task diff")
    diff_parser.add_argument("--task-id", type=int, required=True)
    diff_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    recovery_preview_parser = subparsers.add_parser(
        "recovery-preview", help="Preview stale-task recovery options"
    )
    recovery_preview_parser.add_argument("--task-id", type=int, required=True)
    recovery_preview_parser.add_argument(
        "--config-path", default=str(DEFAULT_CONFIG_PATH)
    )

    relocate_parser = subparsers.add_parser("relocate", help="Relocate one stale task")
    relocate_parser.add_argument("--task-id", type=int, required=True)
    relocate_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    recover_parser = subparsers.add_parser("recover", help="Recover one stale task")
    recover_parser.add_argument("--task-id", type=int, required=True)
    recover_parser.add_argument(
        "--mode",
        choices=["relocate", "requeue_from_current"],
        required=True,
    )
    recover_parser.add_argument("--actor", default=None)
    recover_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    process_parser = subparsers.add_parser(
        "process", help="Pick up and complete one task"
    )
    process_parser.add_argument(
        "--mode",
        choices=["append", "uppercase", "fail"],
        default="append",
    )
    process_parser.add_argument("--agent-name", default=None)
    process_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    continuous_parser = subparsers.add_parser(
        "continuous", help="Run a continuous worker loop"
    )
    continuous_parser.add_argument(
        "--mode",
        choices=["append", "uppercase", "fail"],
        default="append",
    )
    continuous_parser.add_argument("--poll-interval", type=float, default=2.0)
    continuous_parser.add_argument("--agent-name", default=None)
    continuous_parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))

    args = parser.parse_args()

    try:
        if args.command == "setup":
            result = setup_runtime(
                base_url=args.base_url,
                api_key=args.api_key,
                agent_name=args.agent_name,
                timeout=args.timeout,
                config_path=args.config_path,
            )
        elif args.command == "show-config":
            result = {
                "config_exists": has_saved_config(args.config_path),
                "config_file": Path(args.config_path).name,
            }
        elif args.command == "get-task":
            result = get_one_task(task_id=args.task_id, config_path=args.config_path)
        elif args.command == "pickup":
            result = pickup_one_task(
                config_path=args.config_path,
                agent_name=args.agent_name,
            )
        elif args.command == "complete":
            result = complete_one_task(
                task_id=args.task_id,
                result=args.result,
                error_message=args.error_message,
                config_path=args.config_path,
            )
        elif args.command == "diff":
            result = get_task_diff(task_id=args.task_id, config_path=args.config_path)
        elif args.command == "recovery-preview":
            result = get_task_recovery_preview(
                task_id=args.task_id,
                config_path=args.config_path,
            )
        elif args.command == "relocate":
            result = relocate_one_task(
                task_id=args.task_id,
                config_path=args.config_path,
            )
        elif args.command == "recover":
            result = recover_one_task(
                task_id=args.task_id,
                mode=args.mode,
                actor=args.actor,
                config_path=args.config_path,
            )
        elif args.command == "process":
            result = process_one_task(
                mode=args.mode,
                config_path=args.config_path,
                agent_name=args.agent_name,
            )
        else:
            run_continuous(
                mode=args.mode,
                poll_interval=args.poll_interval,
                config_path=args.config_path,
                agent_name=args.agent_name,
            )
            return 0
    except AgentDocsClientError as exc:
        print(json.dumps(exc.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "client_error",
                        "message": str(exc),
                    },
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            build_cli_success(command=args.command, data=result),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
