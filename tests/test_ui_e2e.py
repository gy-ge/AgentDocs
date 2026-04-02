import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, request

import pytest
from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON_EXE = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
API_KEY = "ui-e2e-key"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_http_ok(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with request.urlopen(url) as response:
                if 200 <= response.status < 500:
                    return
        except Exception:
            time.sleep(0.2)
            continue
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}")


def _terminate_process(process: subprocess.Popen[bytes] | subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _api_request(base_url: str, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    body = None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    try:
        with request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        payload_text = exc.read().decode("utf-8")
        raise AssertionError(payload_text or exc.reason) from exc

    assert data["ok"] is True
    return data["data"]


def _wait_for_task_status(base_url: str, doc_id: int, expected_status: str, timeout: float = 12.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = _api_request(base_url, f"/api/tasks?doc_id={doc_id}")
        if tasks and tasks[0]["status"] == expected_status:
            return tasks[0]
        time.sleep(0.2)
    raise AssertionError(f"Task for document {doc_id} did not reach status {expected_status}")


def _select_textarea_range(page, needle: str) -> None:
    page.locator("#doc-body").evaluate(
        """
        (el, target) => {
          const start = el.value.indexOf(target);
          if (start === -1) {
            throw new Error(`Missing selection target: ${target}`);
          }
          const end = start + target.length;
          el.focus();
          el.setSelectionRange(start, end);
          el.dispatchEvent(new Event('select', { bubbles: true }));
        }
        """,
        needle,
    )


def _save_api_key(page) -> None:
    page.locator("#api-key").fill(API_KEY)
    page.get_by_role("button", name="Save and Continue").click()
    page.get_by_text("API Key saved to browser.").wait_for(timeout=5000)


@pytest.fixture
def ui_stack(tmp_path):
    db_path = tmp_path / "ui-e2e.db"
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["API_KEY"] = API_KEY
    env["APP_NAME"] = "AgentDocs UI E2E"
    env["APP_ENV"] = "test"

    subprocess.run(
        [str(PYTHON_EXE), "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    server_process = subprocess.Popen(
        [str(PYTHON_EXE), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_http_ok(f"{base_url}/")

    agent_process = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "scripts/simulate_agent.py",
            "--base-url",
            base_url,
            "--api-key",
            API_KEY,
            "--continuous",
            "--poll-interval",
            "0.2",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        yield {"base_url": base_url}
    finally:
        _terminate_process(agent_process)
        _terminate_process(server_process)


def test_task_selection_action_flow_and_autosave(ui_stack):
    base_url = ui_stack["base_url"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#new-title").fill("Playwright Marker Flow")
        page.get_by_role("button", name="Create", exact=True).click()
        page.get_by_text("Loaded document #", exact=False).wait_for(timeout=5000)

        page.locator("#doc-body").fill(
            "# Playwright Marker Flow\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta."
        )
        page.get_by_text("All changes saved").wait_for(timeout=6000)
        assert page.locator("#doc-save-meta").text_content().startswith("Last saved at")

        _select_textarea_range(page, "Alpha beta gamma.")
        page.locator("#task-instruction").fill("Polish this section for UI testing")
        page.get_by_role("button", name="Create Task").click()

        page.locator("#task-summary").get_by_text("Ready to accept", exact=True).wait_for(timeout=12000)
        page.locator("#task-actions").get_by_role("button", name="Select Text", exact=True).wait_for(timeout=5000)
        page.locator("#task-actions").get_by_role("button", name="Select Text", exact=True).click()
        selected_task_value = page.locator("#task-list").input_value()
        assert selected_task_value != ""
        selected_text = page.locator("#doc-body").evaluate("el => el.value.slice(el.selectionStart, el.selectionEnd)")
        assert selected_text == "Alpha beta gamma."

        browser.close()


def test_conflict_reload_latest_recovers_document(ui_stack):
    base_url = ui_stack["base_url"]
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Conflict Recovery Flow",
            "raw_markdown": "# Conflict Recovery Flow\n\nOriginal body.\n",
            "actor": "browser",
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}, revision 1.").wait_for(timeout=5000)

        page.locator("#doc-title").fill("Conflict Recovery Local Draft")
        page.get_by_text("Unsaved changes").wait_for(timeout=5000)

        _api_request(
            base_url,
            f"/api/docs/{doc['id']}",
            method="PUT",
            payload={
                "title": "Conflict Recovery Remote",
                "raw_markdown": "# Conflict Recovery Flow\n\nOriginal body.\n\nRemote update.\n",
                "expected_revision": 1,
                "actor": "browser",
                "note": "remote update for conflict ui e2e",
            },
        )

        page.get_by_text("Document changed on the server. Save your draft after reviewing the latest version.").wait_for(timeout=6000)
        page.get_by_role("button", name="Reload Latest").click()
        page.locator("#doc-title").wait_for(timeout=5000)
        assert page.locator("#doc-title").input_value() == "Conflict Recovery Remote"
        assert page.locator("#doc-save-pill").text_content() == "All changes saved"
        assert page.locator("#doc-conflict-actions").text_content().strip() == ""

        browser.close()


def test_task_actions_stay_usable_on_narrow_viewport(ui_stack):
    base_url = ui_stack["base_url"]
    raw_markdown = "# Narrow Marker Flow\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta.\n"
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={"title": "Narrow Marker Flow", "raw_markdown": raw_markdown, "actor": "browser"},
    )
    start = raw_markdown.index("Alpha beta gamma.")
    end = start + len("Alpha beta gamma.")
    _api_request(
        base_url,
        f"/api/docs/{doc['id']}/tasks",
        method="POST",
        payload={
            "action": "rewrite",
            "instruction": "compact mobile marker test",
            "source_text": "Alpha beta gamma.",
            "start_offset": start,
            "end_offset": end,
            "doc_revision": 1,
        },
    )
    _wait_for_task_status(base_url, doc["id"], "done")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}, revision 1.").wait_for(timeout=5000)
        page.locator("#task-summary").get_by_text("Ready to accept", exact=True).wait_for(timeout=5000)
        select_text_button = page.locator("#task-actions").get_by_role("button", name="Select Text", exact=True)
        assert select_text_button.is_visible()
        select_text_button.click()
        selected_text = page.locator("#doc-body").evaluate("el => el.value.slice(el.selectionStart, el.selectionEnd)")
        assert selected_text == "Alpha beta gamma."

        browser.close()