import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / "skills" / "agentdocs-integration"
SKILL_FILE = SKILL_DIR / "SKILL.md"
SCRIPT_FILE = SKILL_DIR / "scripts" / "agentdocs_skill_client.py"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
API_KEY = "skill-test-key"


def _load_skill_module():
    spec = importlib.util.spec_from_file_location("agentdocs_skill_client", SCRIPT_FILE)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load skill client module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_http_ok(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception:
            time.sleep(0.2)
            continue
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}")


def _terminate_process(
    process: subprocess.Popen[bytes] | subprocess.Popen[str] | None,
) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _api_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
) -> dict | list | None:
    body = None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = request.Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(http_request, timeout=5) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        payload_text = exc.read().decode("utf-8")
        raise AssertionError(payload_text or exc.reason) from exc

    assert response_payload["ok"] is True
    return response_payload["data"]


@pytest.fixture
def skill_stack(tmp_path):
    db_path = tmp_path / "skill.db"
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["API_KEY"] = API_KEY
    env["APP_NAME"] = "AgentDocs Skill Test"

    subprocess.run(
        [str(PYTHON_EXE), "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    server_process = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_http_ok(f"{base_url}/")

    try:
        yield {"base_url": base_url}
    finally:
        _terminate_process(server_process)


def _create_document_and_task(
    base_url: str, *, title: str, raw_markdown: str, needle: str
) -> int:
    document = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": title,
            "raw_markdown": raw_markdown,
            "actor": "skill-test",
        },
    )
    start_offset = raw_markdown.index(needle)
    end_offset = start_offset + len(needle)
    task = _api_request(
        base_url,
        f"/api/docs/{document['id']}/tasks",
        method="POST",
        payload={
            "action": "rewrite",
            "instruction": "make it tighter",
            "source_text": needle,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "doc_revision": 1,
        },
    )
    return int(task["id"])


def test_skill_markdown_contains_required_frontmatter_and_assets():
    content = SKILL_FILE.read_text(encoding="utf-8")

    assert content.startswith("---\n")
    assert "name: agentdocs-integration" in content
    assert "description:" in content
    assert "Check whether `.agentdocs.config.json` already exists" in content
    assert "python ./scripts/agentdocs_skill_client.py setup" in content
    assert "python ./scripts/agentdocs_skill_client.py process" in content
    assert "python ./scripts/agentdocs_skill_client.py continuous" in content
    assert "./scripts/agentdocs_skill_client.py" in content
    assert "./references/workflow.md" in content


def test_skill_client_can_save_and_load_runtime_config(tmp_path):
    module = _load_skill_module()
    config_path = tmp_path / "agentdocs-config.json"

    saved = module.setup_runtime(
        base_url="https://docs.example.com/",
        api_key="secret-key",
        agent_name="prod-agent",
        timeout=12.5,
        config_path=config_path,
    )

    loaded = module.load_config(config_path)
    resolved = module.resolve_config(config_path=config_path)

    assert saved["base_url"] == "https://docs.example.com"
    assert saved["agent_name"] == "prod-agent"
    assert saved["api_key_saved"] is True
    assert saved["config_path"] == "agentdocs-config.json"
    assert module.has_saved_config(config_path) is True
    assert loaded["api_key"] == "secret-key"
    assert resolved["agent_name"] == "prod-agent"
    assert resolved["timeout"] == 12.5


def test_skill_client_reports_missing_config(tmp_path):
    module = _load_skill_module()
    config_path = tmp_path / "missing.json"

    assert module.has_saved_config(config_path) is False

    with pytest.raises(FileNotFoundError):
        module.load_config(config_path)


def test_skill_client_continuous_loop_uses_process_one_task(monkeypatch):
    module = _load_skill_module()
    observed_calls: list[tuple[str, float]] = []
    responses = iter(
        [
            None,
            {"id": 1, "status": "done", "result": "ok"},
            KeyboardInterrupt(),
        ]
    )

    def fake_process_one_task(**kwargs):
        observed_calls.append((str(kwargs["mode"]), float(kwargs.get("timeout", 10.0))))
        next_item = next(responses)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item

    monkeypatch.setattr(module, "process_one_task", fake_process_one_task)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    with pytest.raises(KeyboardInterrupt):
        module.run_continuous(mode="append", poll_interval=0.01)

    assert observed_calls[0][0] == "append"
    assert len(observed_calls) == 3


def test_skill_client_processes_one_task_against_live_http_stack(skill_stack):
    module = _load_skill_module()
    config_path = Path(skill_stack["base_url"].replace("http://", "").replace(":", "_"))
    config_path = PROJECT_ROOT / ".pytest_cache" / f"{config_path}.json"
    module.setup_runtime(
        base_url=skill_stack["base_url"],
        api_key=API_KEY,
        agent_name="skill-smoke-agent",
        config_path=config_path,
    )
    task_id = _create_document_and_task(
        skill_stack["base_url"],
        title="Skill Success",
        raw_markdown="# Skill Success\n\nHello world\n",
        needle="Hello",
    )

    completed_task = module.process_one_task(
        mode="append",
        config_path=config_path,
    )

    assert completed_task is not None
    assert completed_task["id"] == task_id
    assert completed_task["status"] == "done"
    assert completed_task["agent_name"] == "skill-smoke-agent"
    assert completed_task["result"] == "Hello [agentdocs-skill: make it tighter]"

    diff_data = _api_request(skill_stack["base_url"], f"/api/tasks/{task_id}/diff")
    assert diff_data["can_accept"] is True


def test_skill_client_can_report_failure_against_live_http_stack(skill_stack):
    module = _load_skill_module()
    config_path = Path(skill_stack["base_url"].replace("http://", "").replace(":", "_"))
    config_path = PROJECT_ROOT / ".pytest_cache" / f"{config_path}.json"
    module.setup_runtime(
        base_url=skill_stack["base_url"],
        api_key=API_KEY,
        agent_name="skill-fail-agent",
        config_path=config_path,
    )
    task_id = _create_document_and_task(
        skill_stack["base_url"],
        title="Skill Failure",
        raw_markdown="# Skill Failure\n\nHello world\n",
        needle="Hello",
    )

    completed_task = module.process_one_task(
        mode="fail",
        config_path=config_path,
    )

    assert completed_task is not None
    assert completed_task["id"] == task_id
    assert completed_task["status"] == "failed"
    assert completed_task["error_message"] == "agentdocs skill client simulated failure"


def test_skill_client_requires_exactly_one_completion_field():
    module = _load_skill_module()

    with pytest.raises(ValueError):
        module.build_complete_payload(result=None, error_message=None)

    with pytest.raises(ValueError):
        module.build_complete_payload(result="ok", error_message="bad")
