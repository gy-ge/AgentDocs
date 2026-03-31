import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.simulated_agent import process_next_task


class HttpTaskApiClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def pickup_next_task(self, agent_name: str) -> dict | None:
        return self._post("/api/tasks/next", {"agent_name": agent_name})

    def complete_task(
        self,
        task_id: int,
        *,
        result: str | None,
        error_message: str | None,
    ) -> dict:
        return self._post(
            f"/api/tasks/{task_id}/complete",
            {"result": result, "error_message": error_message},
        )

    def _post(self, path: str, payload: dict) -> dict | None:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            payload_text = exc.read().decode("utf-8")
            raise RuntimeError(payload_text or exc.reason) from exc

        if not data.get("ok"):
            raise RuntimeError(json.dumps(data, ensure_ascii=False))
        return data.get("data")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a simulated AgentDocs worker")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="AgentDocs base url",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("API_KEY", "change-me"),
        help="shared API key",
    )
    parser.add_argument(
        "--agent-name",
        default="simulated-agent",
        help="name reported to the task API",
    )
    parser.add_argument(
        "--mode",
        choices=["append", "uppercase", "fail"],
        default="append",
        help="how the simulated agent completes tasks",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=1,
        help="maximum tasks to process before exiting",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="seconds to wait between polls in continuous mode",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="keep polling until interrupted",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    api_client = HttpTaskApiClient(args.base_url, args.api_key)
    processed = 0

    try:
        while True:
            completed_task = process_next_task(
                api_client,
                agent_name=args.agent_name,
                mode=args.mode,
            )
            if completed_task is None:
                print("No pending task.")
                if not args.continuous:
                    return 0
                time.sleep(args.poll_interval)
                continue

            processed += 1
            print(
                f"Processed task {completed_task['id']} with status {completed_task['status']}"
            )

            if not args.continuous and processed >= args.max_tasks:
                return 0
    except KeyboardInterrupt:
        print("Stopped by user.")
        return 0
    except RuntimeError as exc:
        print(f"Simulated agent failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())