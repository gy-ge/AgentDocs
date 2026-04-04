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
    base_url: str, path: str, *, method: str = "GET", payload: dict | None = None
) -> dict:
    body = None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(
        f"{base_url}{path}", data=body, headers=headers, method=method
    )
    try:
        with request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        payload_text = exc.read().decode("utf-8")
        raise AssertionError(payload_text or exc.reason) from exc

    assert data["ok"] is True
    return data["data"]


def _wait_for_task_status(
    base_url: str, doc_id: int, expected_status: str, timeout: float = 12.0
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = _api_request(base_url, f"/api/tasks?doc_id={doc_id}")
        if tasks and tasks[0]["status"] == expected_status:
            return tasks[0]
        time.sleep(0.2)
    raise AssertionError(
        f"Task for document {doc_id} did not reach status {expected_status}"
    )


def _wait_for_task_count_with_status(
    base_url: str,
    doc_id: int,
    expected_status: str,
    expected_count: int,
    timeout: float = 20.0,
) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        tasks = _api_request(base_url, f"/api/tasks?doc_id={doc_id}")
        if len(tasks) >= expected_count and all(
            task["status"] == expected_status for task in tasks[:expected_count]
        ):
            return tasks
        time.sleep(0.2)
    raise AssertionError(
        f"Document {doc_id} did not reach {expected_count} tasks with status {expected_status}"
    )


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


def _show_selection_toolbar(page, needle: str) -> None:
    _select_textarea_range(page, needle)
    page.locator("#doc-body").evaluate(
        """
                (el) => {
                    const rect = el.getBoundingClientRect();
                    el.dispatchEvent(new MouseEvent('mouseup', {
                        bubbles: true,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + 20,
                    }));
                }
                """
    )
    page.locator("#selection-toolbar").wait_for(state="visible", timeout=5000)


def _save_api_key(page) -> None:
    page.locator("#api-key").fill(API_KEY)
    page.get_by_role("button", name="Save and Continue").click()
    page.locator("#key-modal").wait_for(state="hidden", timeout=5000)


def _create_doc_from_selector(page, title: str) -> None:
    page.locator("#doc-selector").select_option("__create_new__")
    page.locator("#create-doc-modal").wait_for(state="visible", timeout=5000)
    page.locator("#create-doc-title").fill(title)
    page.locator("#submit-create-doc").click()
    page.locator("#create-doc-modal").wait_for(state="hidden", timeout=5000)
    page.get_by_text("Loaded document #", exact=False).wait_for(timeout=5000)


def test_create_doc_modal_cancel_and_confirm(ui_stack):
    base_url = ui_stack["base_url"]
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Existing Doc",
            "raw_markdown": "# Existing Doc\n",
            "actor": "browser",
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)

        page.locator("#doc-selector").select_option("__create_new__")
        page.locator("#create-doc-modal").wait_for(state="visible", timeout=5000)
        page.locator("#cancel-create-doc").click()
        page.locator("#create-doc-modal").wait_for(state="hidden", timeout=5000)
        assert page.locator("#doc-selector").input_value() == str(doc["id"])

        _create_doc_from_selector(page, "Created In Modal")
        assert page.locator("#doc-title").input_value() == "Created In Modal"
        assert page.locator("#doc-selector").input_value() != str(doc["id"])

        browser.close()


@pytest.fixture
def ui_stack(tmp_path):
    db_path = tmp_path / "ui-e2e.db"
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["SQLITE_PATH"] = str(db_path)
    env["API_KEY"] = API_KEY
    env["APP_NAME"] = "AgentDocs UI E2E"

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
        _create_doc_from_selector(page, "Playwright Marker Flow")

        page.locator("#doc-body").fill(
            "# Playwright Marker Flow\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta."
        )
        page.wait_for_function(
            "() => document.querySelector('#doc-save-pill')?.textContent === 'Saved'",
            timeout=6000,
        )
        assert page.locator("#doc-save-meta").text_content().startswith("Last saved at")

        _select_textarea_range(page, "Alpha beta gamma.")
        page.locator("#task-instruction").fill("Polish this section for UI testing")
        page.locator("#create-task").click()

        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#task-comment-list .task-comment-status')).some((el) => el.textContent?.trim() === 'Completed')",
            timeout=12000,
        )
        page.locator("#task-comment-list [data-comment-task-id]").first.wait_for(
            timeout=5000
        )
        page.locator("#review-mode-review").click()
        page.locator("#review-surface [data-review-task-id]").first.wait_for(
            timeout=5000
        )
        assert page.locator("#task-comment-list [data-comment-task-id]").count() == 1
        assert page.locator("#review-surface [data-review-task-id]").count() >= 1
        page.locator("#task-comment-list [data-comment-task-id]").first.click()
        page.locator("#task-comment-list [data-comment-open]").first.wait_for(
            timeout=5000
        )
        page.locator("#task-comment-list [data-comment-open]").first.click()
        selected_task_value = page.locator("#task-list").input_value()
        assert selected_task_value != ""
        selected_text = page.locator("#doc-body").evaluate(
            "el => el.value.slice(el.selectionStart, el.selectionEnd)"
        )
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
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)

        page.locator("#doc-title").fill("Conflict Recovery Local Draft")
        page.wait_for_function(
            "() => document.querySelector('#doc-save-pill')?.textContent === 'Unsaved'",
            timeout=5000,
        )

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

        page.get_by_text(
            "Document changed on the server. Save your draft after reviewing the latest version."
        ).wait_for(timeout=6000)
        page.get_by_role("button", name="Reload Latest").click()
        page.locator("#doc-title").wait_for(timeout=5000)
        assert page.locator("#doc-title").input_value() == "Conflict Recovery Remote"
        assert page.locator("#doc-save-pill").text_content() == "Saved"
        assert page.locator("#doc-conflict-actions").text_content().strip() == ""

        browser.close()


def test_task_actions_stay_usable_on_narrow_viewport(ui_stack):
    base_url = ui_stack["base_url"]
    raw_markdown = "# Narrow Marker Flow\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta.\n"
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Narrow Marker Flow",
            "raw_markdown": raw_markdown,
            "actor": "browser",
        },
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
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)
        page.locator("#task-comment-list [data-comment-task-id]").first.wait_for(
            timeout=5000
        )
        page.locator("#task-comment-list [data-comment-task-id]").first.click()
        select_text_button = page.locator(
            "#task-comment-list [data-comment-open]"
        ).first
        assert select_text_button.is_visible()
        select_text_button.click()
        selected_text = page.locator("#doc-body").evaluate(
            "el => el.value.slice(el.selectionStart, el.selectionEnd)"
        )
        assert selected_text == "Alpha beta gamma."

        browser.close()


def test_review_comments_show_latest_task_first(ui_stack):
    """Comment rail sorts cards by document offset (ascending), so the card
    nearest to the top of the document appears first regardless of creation
    order."""
    base_url = ui_stack["base_url"]
    raw_markdown = "# Comment Order\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta.\n"
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Comment Order",
            "raw_markdown": raw_markdown,
            "actor": "browser",
        },
    )

    alpha_start = raw_markdown.index("Alpha beta gamma.")
    alpha_end = alpha_start + len("Alpha beta gamma.")
    delta_start = raw_markdown.index("Delta epsilon zeta.")
    delta_end = delta_start + len("Delta epsilon zeta.")

    first_task = _api_request(
        base_url,
        f"/api/docs/{doc['id']}/tasks",
        method="POST",
        payload={
            "action": "rewrite",
            "instruction": "first task",
            "source_text": "Alpha beta gamma.",
            "start_offset": alpha_start,
            "end_offset": alpha_end,
            "doc_revision": 1,
        },
    )
    _api_request(
        base_url,
        f"/api/docs/{doc['id']}/tasks",
        method="POST",
        payload={
            "action": "rewrite",
            "instruction": "second task",
            "source_text": "Delta epsilon zeta.",
            "start_offset": delta_start,
            "end_offset": delta_end,
            "doc_revision": 1,
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.locator("#task-comment-list [data-comment-task-id]").nth(1).wait_for(
            timeout=5000
        )
        first_card = page.locator("#task-comment-list [data-comment-task-id]").first
        assert first_card.get_attribute("data-comment-task-id") == str(first_task["id"])
        assert "Alpha beta gamma." in first_card.text_content()

        browser.close()


def test_task_completion_pushes_without_manual_refresh_and_sse_live(ui_stack):
    base_url = ui_stack["base_url"]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        _create_doc_from_selector(page, "SSE Push Verification")

        # Verify SSE is active and UI reports live stream mode.
        page.wait_for_function(
            """
            () => {
              const pill = document.querySelector('#workspace-sync-pill');
              return !!pill && (pill.textContent || '').includes('Live');
            }
            """,
            timeout=8000,
        )

        page.locator("#doc-body").fill(
            "# SSE Push Verification\n\n## Section A\nAlpha beta gamma.\n\n## Section B\nDelta epsilon zeta."
        )
        page.wait_for_function(
            "() => document.querySelector('#doc-save-pill')?.textContent === 'Saved'",
            timeout=6000,
        )

        _select_textarea_range(page, "Alpha beta gamma.")
        page.locator("#task-instruction").fill("SSE completion push check")
        page.locator("#create-task").click()

        # No manual refresh click here: completion must arrive via SSE/poll path.
        page.wait_for_function(
            """
            () => {
              const statuses = Array.from(document.querySelectorAll('#task-comment-list .task-comment-status'));
              return statuses.some((el) => (el.textContent || '').trim() === 'Completed');
            }
            """,
            timeout=12000,
        )

        browser.close()


def test_laptop_viewport_layout_stays_scrollable_and_compact(ui_stack):
    base_url = ui_stack["base_url"]
    sections: list[str] = []
    ranges: list[tuple[int, int, str]] = []
    cursor = 0
    for index in range(1, 15):
        line = f"- item {index:02d} for comment rail overflow\n"
        sections.append(line)
        start = cursor
        end = start + len(line.rstrip("\n"))
        ranges.append((start, end, line.rstrip("\n")))
        cursor += len(line)

    filler = "\n".join(
        f"Paragraph {index:02d} keeps the review surface tall for overflow checks."
        for index in range(1, 20)
    )
    raw_markdown = (
        "# Compact Layout\n\n## Items\n"
        + "".join(sections)
        + "\n\n## Filler\n"
        + filler
    )
    offset_base = len("# Compact Layout\n\n## Items\n")
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Compact Layout",
            "raw_markdown": raw_markdown,
            "actor": "browser",
        },
    )

    for start, end, source_text in ranges:
        _api_request(
            base_url,
            f"/api/docs/{doc['id']}/tasks",
            method="POST",
            payload={
                "action": "rewrite",
                "instruction": f"layout regression {source_text}",
                "source_text": source_text,
                "start_offset": offset_base + start,
                "end_offset": offset_base + end,
                "doc_revision": 1,
            },
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)
        page.locator("#task-comment-list [data-comment-task-id]").nth(10).wait_for(
            timeout=5000
        )
        page.locator("#review-mode-review").click()
        page.locator("#review-surface .review-surface-content").wait_for(timeout=5000)

        metrics = page.evaluate(
            """
                        () => {
                            const workspace = document.querySelector('.workspace');
                            const editorColumn = document.querySelector('.editor-column');
                            const sidebar = document.querySelector('.sidebar');
                            const editorPanelShell = document.querySelector('.editor-panel');
                            const panelBody = document.querySelector('.comment-rail .task-panel .panel-body.stack');
                            const taskList = document.getElementById('task-comment-list');
                            const composer = document.getElementById('composer-drawer');
                            const toolbar = document.querySelector('.editor-toolbar');
                            const editorPanel = document.querySelector('.editor-panel .panel-body.stack');
                            const reviewPanel = document.querySelector('.review-surface-panel');
                            const reviewContent = document.querySelector('#review-surface .review-surface-content');
                            const docSelector = document.getElementById('doc-selector');
                            const docTitle = document.getElementById('doc-title');
                            const actions = document.querySelector('.editor-toolbar-actions');
                            const exportDoc = document.getElementById('export-doc');
                                const savePill = document.getElementById('doc-save-pill');
                                const revisionPill = document.getElementById('doc-revision-pill');
                                const reviewPill = document.getElementById('review-surface-pill');

                            const read = (el) => {
                                if (!el) {
                                    return null;
                                }
                                const rect = el.getBoundingClientRect();
                                const style = getComputedStyle(el);
                                return {
                                    top: rect.top,
                                    bottom: rect.bottom,
                                    height: rect.height,
                                    clientHeight: el.clientHeight,
                                    scrollHeight: el.scrollHeight,
                                    overflowY: style.overflowY,
                                };
                            };

                            const top = (el) => el ? el.getBoundingClientRect().top : null;

                            return {
                                workspace: read(workspace),
                                editorColumn: read(editorColumn),
                                sidebar: read(sidebar),
                                editorPanelShell: read(editorPanelShell),
                                panelBody: read(panelBody),
                                taskList: read(taskList),
                                composer: read(composer),
                                toolbar: read(toolbar),
                                editorPanel: read(editorPanel),
                                reviewPanel: read(reviewPanel),
                                reviewContent: read(reviewContent),
                                controlTops: {
                                    docSelector: top(docSelector),
                                    docTitle: top(docTitle),
                                    actions: top(actions),
                                    exportDoc: top(exportDoc),
                                    savePill: top(savePill),
                                    revisionPill: top(revisionPill),
                                    reviewPill: top(reviewPill),
                                },
                            };
                        }
                        """
        )

        assert metrics["workspace"] is not None
        assert metrics["editorColumn"] is not None
        assert metrics["sidebar"] is not None
        assert metrics["editorPanelShell"] is not None
        assert metrics["panelBody"] is not None
        assert metrics["taskList"] is not None
        assert metrics["composer"] is not None
        assert metrics["toolbar"] is not None
        assert metrics["editorPanel"] is not None
        assert metrics["reviewPanel"] is not None
        assert metrics["reviewContent"] is not None
        assert metrics["workspace"]["height"] <= metrics["sidebar"]["height"] + 4
        assert metrics["editorColumn"]["height"] <= metrics["sidebar"]["height"] + 4
        assert metrics["editorPanelShell"]["height"] <= metrics["sidebar"]["height"] + 4
        assert metrics["editorPanel"]["height"] <= metrics["sidebar"]["height"] + 4
        assert metrics["panelBody"]["bottom"] <= metrics["sidebar"]["bottom"] + 2
        assert metrics["taskList"]["scrollHeight"] > metrics["taskList"]["clientHeight"]
        assert metrics["taskList"]["overflowY"] in {"auto", "scroll"}
        assert metrics["composer"]["height"] < 280
        assert metrics["toolbar"]["height"] <= 80
        assert metrics["reviewPanel"]["bottom"] <= metrics["editorPanel"]["bottom"] + 2
        assert (
            metrics["reviewContent"]["scrollHeight"]
            > metrics["reviewContent"]["clientHeight"]
        )
        tops = metrics["controlTops"]
        assert tops["docSelector"] is not None
        assert tops["docTitle"] is not None
        assert tops["actions"] is not None
        assert tops["exportDoc"] is not None
        assert tops["savePill"] is not None
        assert tops["revisionPill"] is not None
        assert tops["reviewPill"] is not None
        assert abs(tops["docSelector"] - tops["docTitle"]) <= 2
        assert abs(tops["actions"] - tops["exportDoc"]) <= 2
        assert abs(tops["savePill"] - tops["docTitle"]) <= 10
        assert abs(tops["revisionPill"] - tops["docTitle"]) <= 10
        assert abs(tops["reviewPill"] - tops["docTitle"]) <= 10

        browser.close()


def test_doc_title_input_uses_available_toolbar_width(ui_stack):
    base_url = ui_stack["base_url"]
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Width Check Document",
            "raw_markdown": "# Width Check Document\n",
            "actor": "browser",
        },
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)

        metrics = page.evaluate(
            """
                        () => {
                            const switcher = document.querySelector('.doc-switcher');
                            const selector = document.getElementById('doc-selector');
                            const title = document.getElementById('doc-title');
                            const actions = document.querySelector('.editor-toolbar-actions');
                            const toolbar = document.querySelector('.editor-toolbar');
                            if (!switcher || !selector || !title || !toolbar || !actions) {
                                throw new Error('Missing toolbar controls');
                            }
                            const switcherRect = switcher.getBoundingClientRect();
                            const selectorRect = selector.getBoundingClientRect();
                            const titleRect = title.getBoundingClientRect();
                            const actionsRect = actions.getBoundingClientRect();
                            const toolbarRect = toolbar.getBoundingClientRect();
                            return {
                                switcherRight: switcherRect.right,
                                titleRight: titleRect.right,
                                actionsLeft: actionsRect.left,
                                selectorWidth: selectorRect.width,
                                titleWidth: titleRect.width,
                                toolbarWidth: toolbarRect.width,
                                switcherWidth: switcherRect.width,
                            };
                        }
                        """
        )

        assert metrics["switcherWidth"] > metrics["toolbarWidth"] * 0.35
        assert metrics["titleWidth"] > metrics["selectorWidth"]
        assert abs(metrics["actionsLeft"] - metrics["switcherRight"]) <= 10
        assert abs(metrics["switcherRight"] - metrics["titleRight"]) <= 2
        assert page.locator("#save-doc").count() == 0

        browser.close()


def test_review_mode_keeps_left_scroll_and_syncs_comment_rail(ui_stack):
    base_url = ui_stack["base_url"]
    item_lines = [
        f"- review sync item {index:02d} keeps the rail busy and the surface tall"
        for index in range(1, 15)
    ]
    filler = "\n".join(
        f"Paragraph {index:02d} extends the review panel for scroll-sync regression coverage."
        for index in range(1, 18)
    )
    raw_markdown = (
        "# Review Scroll Sync\n\n## Items\n"
        + "\n".join(item_lines)
        + "\n\n## Notes\n"
        + filler
    )
    doc = _api_request(
        base_url,
        "/api/docs",
        method="POST",
        payload={
            "title": "Review Scroll Sync",
            "raw_markdown": raw_markdown,
            "actor": "browser",
        },
    )

    for line in item_lines:
        start = raw_markdown.index(line)
        end = start + len(line)
        _api_request(
            base_url,
            f"/api/docs/{doc['id']}/tasks",
            method="POST",
            payload={
                "action": "rewrite",
                "instruction": f"review sync {line}",
                "source_text": line,
                "start_offset": start,
                "end_offset": end,
                "doc_revision": 1,
            },
        )

    _wait_for_task_count_with_status(
        base_url, doc["id"], "done", len(item_lines), timeout=25.0
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        page.locator("#doc-selector").select_option(str(doc["id"]))
        page.get_by_text(f"Loaded document #{doc['id']}.").wait_for(timeout=5000)
        page.locator("#task-comment-list [data-comment-task-id]").nth(12).wait_for(
            timeout=5000
        )
        page.locator("#review-mode-review").click()
        page.locator("#review-surface .review-surface-content").wait_for(timeout=5000)

        page.evaluate(
            """
            () => {
              const reviewContent = document.querySelector('#review-surface .review-surface-content');
              const taskList = document.getElementById('task-comment-list');
              if (!reviewContent || !taskList) {
                throw new Error('Missing review content or task list');
              }
              reviewContent.scrollTop = Math.max(0, reviewContent.scrollHeight * 0.58);
              taskList.scrollTop = 0;
            }
            """
        )

        target_marker = page.locator("#review-surface [data-review-task-id]").nth(11)
        target_marker.scroll_into_view_if_needed()
        target_task_id = target_marker.get_attribute("data-review-task-id")
        assert target_task_id is not None

        scroll_before = page.evaluate(
            """
            () => {
              const reviewContent = document.querySelector('#review-surface .review-surface-content');
              return reviewContent ? reviewContent.scrollTop : 0;
            }
            """
        )

        target_marker.click()
        page.wait_for_function(
            """
            (taskId) => {
              const activeCard = document.querySelector('#task-comment-list .task-comment-card.is-active');
              return !!activeCard && activeCard.getAttribute('data-comment-task-id') === taskId;
            }
            """,
            arg=target_task_id,
            timeout=5000,
        )

        metrics = page.evaluate(
            """
            () => {
              const reviewContent = document.querySelector('#review-surface .review-surface-content');
              const taskList = document.getElementById('task-comment-list');
              const activeCard = document.querySelector('#task-comment-list .task-comment-card.is-active');
              if (!reviewContent || !taskList || !activeCard) {
                throw new Error('Missing review sync elements');
              }
              const listRect = taskList.getBoundingClientRect();
              const cardRect = activeCard.getBoundingClientRect();
              return {
                reviewScrollTop: reviewContent.scrollTop,
                taskListScrollTop: taskList.scrollTop,
                activeCardTop: cardRect.top,
                activeCardBottom: cardRect.bottom,
                taskListTop: listRect.top,
                taskListBottom: listRect.bottom,
              };
            }
            """
        )

        assert metrics["reviewScrollTop"] > 120
        assert abs(metrics["reviewScrollTop"] - scroll_before) < 180
        assert metrics["taskListScrollTop"] > 0
        assert metrics["activeCardTop"] >= metrics["taskListTop"] - 1
        assert metrics["activeCardTop"] <= metrics["taskListTop"] + 56
        assert metrics["activeCardBottom"] > metrics["taskListTop"] + 80

        browser.close()


def test_selection_toolbar_template_updates_instruction(ui_stack):
    base_url = ui_stack["base_url"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")

        _save_api_key(page)
        _create_doc_from_selector(page, "Selection Toolbar Template Sync")
        page.locator("#doc-body").fill(
            "# Selection Toolbar Template Sync\n\nAlpha beta gamma for selection toolbar."
        )
        page.wait_for_function(
            "() => document.querySelector('#doc-save-pill')?.textContent === 'Saved'",
            timeout=6000,
        )

        _show_selection_toolbar(page, "Alpha beta gamma")
        page.locator("#selection-toolbar-template").select_option(
            "builtin:instruction-example"
        )

        expected_instruction = "Example: Define goals, style, constraints, and length"
        page.wait_for_function(
            """
            (snippet) => {
              const toolbarInstruction = document.getElementById('selection-toolbar-instruction');
              const taskInstruction = document.getElementById('task-instruction');
              return !!toolbarInstruction && !!taskInstruction
                && (toolbarInstruction.value || '').includes(snippet)
                && (taskInstruction.value || '').includes(snippet);
            }
            """,
            arg=expected_instruction,
            timeout=5000,
        )

        assert (
            expected_instruction
            in page.locator("#selection-toolbar-instruction").input_value()
        )
        assert expected_instruction in page.locator("#task-instruction").input_value()

        browser.close()
