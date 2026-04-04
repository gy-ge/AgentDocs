import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(env_file: Path) -> None:
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class SmokeConfig:
    base_url: str
    api_key: str


STAGE_ORDER = ("basic", "tasks", "rollback")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an AgentDocs online smoke test")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to the env file that contains AGENTDOCS_SMOKE_BASE_URL and AGENTDOCS_SMOKE_API_KEY",
    )
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=STAGE_ORDER,
        default=["rollback"],
        help="Smoke test stages to run. Later stages imply earlier prerequisites.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "human"),
        default="json",
        help="Output format. Use human for a concise operator-friendly summary.",
    )
    return parser


def load_config(env_file: str) -> SmokeConfig:
    load_env_file(
        (PROJECT_ROOT / env_file).resolve()
        if not Path(env_file).is_absolute()
        else Path(env_file)
    )

    base_url = os.environ.get("AGENTDOCS_SMOKE_BASE_URL", "").strip().rstrip("/")
    api_key = os.environ.get(
        "AGENTDOCS_SMOKE_API_KEY", os.environ.get("API_KEY", "")
    ).strip()

    missing = []
    if not base_url:
        missing.append("AGENTDOCS_SMOKE_BASE_URL")
    if not api_key:
        missing.append("AGENTDOCS_SMOKE_API_KEY or API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required smoke test settings: {', '.join(missing)}"
        )

    return SmokeConfig(base_url=base_url, api_key=api_key)


class LiveSmokeClient:
    def __init__(self, config: SmokeConfig) -> None:
        self.base_url = config.base_url
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AgentDocsLiveSmoke/1.0",
        }

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=self.headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} failed with {exc.code}: {error_body}"
            ) from exc

        parsed = json.loads(text) if text else None
        if isinstance(parsed, dict) and "ok" in parsed and "data" in parsed:
            if parsed["ok"] is not True:
                raise RuntimeError(f"{method} {path} returned not ok: {parsed}")
            return parsed["data"]
        return parsed


def normalize_checks(requested_checks: list[str]) -> set[str]:
    enabled: set[str] = set()
    highest_index = max(STAGE_ORDER.index(check) for check in requested_checks)
    for check in STAGE_ORDER[: highest_index + 1]:
        enabled.add(check)
    return enabled


def parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assert_utc_timestamp(value: str | None, label: str) -> None:
    parsed = parse_utc_timestamp(value)
    if (
        parsed is None
        or parsed.tzinfo is None
        or parsed.utcoffset() != timezone.utc.utcoffset(parsed)
    ):
        raise AssertionError(f"{label} is not UTC-aware: {value!r}")


def create_task(
    client: LiveSmokeClient,
    *,
    doc_id: int,
    raw_markdown: str,
    doc_revision: int,
    source_text: str,
    action: str,
    instruction: str,
) -> dict[str, Any]:
    start_offset = raw_markdown.index(source_text)
    end_offset = start_offset + len(source_text)
    task = client.request(
        f"/api/docs/{doc_id}/tasks",
        method="POST",
        payload={
            "action": action,
            "instruction": instruction,
            "source_text": source_text,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "doc_revision": doc_revision,
        },
    )
    assert_utc_timestamp(task.get("created_at"), f"task {task.get('id')} created_at")
    return task


def pickup_and_complete(
    client: LiveSmokeClient, *, result: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    picked = client.request(
        "/api/tasks/next", method="POST", payload={"agent_name": "live-smoke-agent"}
    )
    if picked is None:
        raise AssertionError("pickup returned no task")
    completed = client.request(
        f"/api/tasks/{picked['id']}/complete",
        method="POST",
        payload={"result": result, "error_message": None},
    )
    if completed["status"] != "done":
        raise AssertionError(
            f"task {picked['id']} did not complete successfully: {completed}"
        )
    assert_utc_timestamp(
        completed.get("completed_at"), f"task {picked['id']} completed_at"
    )
    return picked, completed


def run_smoke_test(
    config: SmokeConfig, *, requested_checks: list[str]
) -> dict[str, Any]:
    client = LiveSmokeClient(config)
    enabled_checks = normalize_checks(requested_checks)
    prefix = f"live-smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    created_doc_id: int | None = None
    raw_markdown = (
        "# Live Smoke Verification\n\nAlpha beta gamma.\n\nDelta epsilon zeta.\n"
    )
    results: list[dict[str, Any]] = []
    document: dict[str, Any] | None = None
    after_accept: dict[str, Any] | None = None

    try:
        if "basic" in enabled_checks:
            documents = client.request("/api/docs")
            results.append({"step": "list_docs", "count": len(documents)})

            created = client.request(
                "/api/docs",
                method="POST",
                payload={
                    "title": f"{prefix}-doc",
                    "raw_markdown": raw_markdown,
                    "actor": "live-smoke",
                },
            )
            created_doc_id = int(created["id"])
            results.append(
                {
                    "step": "create_doc",
                    "doc_id": created_doc_id,
                    "revision": created["revision"],
                }
            )

            document = client.request(f"/api/docs/{created_doc_id}")
            assert_utc_timestamp(document.get("updated_at"), "document.updated_at")
            results.append({"step": "get_doc", "revision": document["revision"]})

        if "tasks" in enabled_checks:
            if created_doc_id is None or document is None:
                raise AssertionError(
                    "task checks require the basic checks to create a document"
                )

            task_accept = create_task(
                client,
                doc_id=created_doc_id,
                raw_markdown=document["raw_markdown"],
                doc_revision=document["revision"],
                source_text="Alpha beta gamma.",
                action="rewrite",
                instruction="accept flow",
            )
            picked_accept, _ = pickup_and_complete(
                client,
                result=f"{task_accept['source_text']} [live-smoke-accept]",
            )
            if picked_accept["id"] != task_accept["id"]:
                raise AssertionError(
                    f"pickup returned unexpected task for accept flow: {picked_accept}"
                )
            accepted = client.request(
                f"/api/tasks/{task_accept['id']}/accept",
                method="POST",
                payload={
                    "expected_revision": document["revision"],
                    "actor": "live-smoke",
                    "note": "accept from smoke test",
                },
            )
            if accepted["status"] != "accepted":
                raise AssertionError(f"accept flow failed: {accepted}")
            results.append(
                {
                    "step": "accept_task",
                    "task_id": task_accept["id"],
                    "status": accepted["status"],
                }
            )

            after_accept = client.request(f"/api/docs/{created_doc_id}")
            if after_accept["revision"] <= document["revision"]:
                raise AssertionError("document revision did not advance after accept")
            results.append(
                {"step": "doc_after_accept", "revision": after_accept["revision"]}
            )

            task_reject = create_task(
                client,
                doc_id=created_doc_id,
                raw_markdown=after_accept["raw_markdown"],
                doc_revision=after_accept["revision"],
                source_text="Delta epsilon zeta.",
                action="rewrite",
                instruction="reject flow",
            )
            picked_reject, _ = pickup_and_complete(
                client,
                result=f"{task_reject['source_text']} [live-smoke-reject]",
            )
            if picked_reject["id"] != task_reject["id"]:
                raise AssertionError(
                    f"pickup returned unexpected task for reject flow: {picked_reject}"
                )
            rejected = client.request(
                f"/api/tasks/{task_reject['id']}/reject", method="POST"
            )
            if rejected["status"] != "rejected":
                raise AssertionError(f"reject flow failed: {rejected}")
            results.append(
                {
                    "step": "reject_task",
                    "task_id": task_reject["id"],
                    "status": rejected["status"],
                }
            )

            task_cancel = create_task(
                client,
                doc_id=created_doc_id,
                raw_markdown=after_accept["raw_markdown"],
                doc_revision=after_accept["revision"],
                source_text="Live Smoke Verification",
                action="translate",
                instruction="cancel flow",
            )
            cancelled = client.request(
                f"/api/tasks/{task_cancel['id']}/cancel", method="POST"
            )
            if cancelled["status"] != "cancelled":
                raise AssertionError(f"cancel flow failed: {cancelled}")
            results.append(
                {
                    "step": "cancel_task",
                    "task_id": task_cancel["id"],
                    "status": cancelled["status"],
                }
            )

            tasks = client.request(f"/api/tasks?doc_id={created_doc_id}")
            results.append(
                {
                    "step": "list_tasks",
                    "count": len(tasks),
                    "statuses": [task["status"] for task in tasks],
                }
            )

            versions = client.request(f"/api/docs/{created_doc_id}/versions")
            for version in versions:
                assert_utc_timestamp(
                    version.get("created_at"), f"version {version.get('id')} created_at"
                )
            results.append(
                {
                    "step": "list_versions",
                    "count": len(versions),
                    "version_ids": [version["id"] for version in versions],
                }
            )

        if "rollback" in enabled_checks:
            if created_doc_id is None or after_accept is None:
                raise AssertionError(
                    "rollback checks require the task checks to prepare a version history"
                )

            versions = client.request(f"/api/docs/{created_doc_id}/versions")
            rollback_target = next(
                (version for version in versions if version["revision"] == 1), None
            )
            if rollback_target is None:
                raise AssertionError(
                    f"could not find revision 1 rollback target: {versions}"
                )
            rolled_back = client.request(
                f"/api/docs/{created_doc_id}/versions/{rollback_target['id']}/rollback",
                method="POST",
                payload={
                    "expected_revision": after_accept["revision"],
                    "actor": "live-smoke",
                    "note": "rollback from smoke test",
                },
            )
            if rolled_back["revision"] <= after_accept["revision"]:
                raise AssertionError(
                    f"rollback did not create a new revision: {rolled_back}"
                )
            final_document = client.request(f"/api/docs/{created_doc_id}")
            if final_document["raw_markdown"] != raw_markdown:
                raise AssertionError(
                    "final document content did not match the original markdown after rollback"
                )
            results.append({"step": "rollback", "revision": rolled_back["revision"]})

        return {
            "ok": True,
            "base_url": config.base_url,
            "doc_id": created_doc_id,
            "checks": [check for check in STAGE_ORDER if check in enabled_checks],
            "results": results,
        }
    finally:
        if created_doc_id is not None:
            client.request(f"/api/docs/{created_doc_id}", method="DELETE")


def format_human_summary(result: dict[str, Any]) -> str:
    lines = [
        "AgentDocs Live Smoke Test",
        f"Target: {result['base_url']}",
        f"Checks: {', '.join(result.get('checks', [])) or 'none'}",
        f"Temporary doc id: {result.get('doc_id')}",
        "Steps:",
    ]
    for item in result.get("results", []):
        details = ", ".join(
            f"{key}={value}" for key, value in item.items() if key != "step"
        )
        if details:
            lines.append(f"- {item['step']}: {details}")
        else:
            lines.append(f"- {item['step']}")
    lines.append("Status: OK")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.env_file)
        result = run_smoke_test(config, requested_checks=args.checks)
    except Exception as exc:
        if args.output == "human":
            print("AgentDocs Live Smoke Test")
            print("Status: FAILED")
            print(f"Error: {exc}")
        else:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    if args.output == "human":
        print(format_human_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
