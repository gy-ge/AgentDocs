import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / ".agentdocs.config.json"


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
    headers = {"Authorization": f"Bearer {api_key}"}
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
        raise RuntimeError(details or exc.reason) from exc

    if response_payload.get("ok") is not True:
        raise RuntimeError(json.dumps(response_payload, ensure_ascii=False))
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
        print(json.dumps(completed_task, ensure_ascii=False), flush=True)

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

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
