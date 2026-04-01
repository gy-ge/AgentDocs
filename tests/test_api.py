def create_document(client, auth_headers, raw_markdown: str, title: str = "Doc"):
    response = client.post(
        "/api/docs",
        headers=auth_headers,
        json={
            "title": title,
            "raw_markdown": raw_markdown,
            "actor": "browser",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_task(client, auth_headers, doc_id: int, raw_markdown: str, needle: str):
    start_offset = raw_markdown.index(needle)
    end_offset = start_offset + len(needle)
    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "instruction": "rewrite text",
            "source_text": needle,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "doc_revision": 1,
        },
    )
    assert response.status_code == 200
    return response.json()["data"], start_offset, end_offset


def test_authentication_is_required(client):
    response = client.get("/api/docs")

    assert response.status_code == 401
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "unauthorized",
            "message": "invalid api key",
        },
    }


def test_root_page_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "�" not in response.text
    assert "AgentDocs" in response.text
    assert 'meta name="description"' in response.text
    assert 'rel="icon"' in response.text
    assert "连接设置" in response.text
    assert "文档工作台" in response.text
    assert "模板格式示例" in response.text
    assert "已有文档" in response.text
    assert "新建文档" in response.text
    assert "任务动作" in response.text
    assert "任务处理" in response.text
    assert "当前文档任务" in response.text
    assert "创建任务" in response.text
    assert "导出 Markdown" in response.text
    assert "删除文档" in response.text
    assert "清理失效" in response.text
    assert "批量接受可合并结果" in response.text
    assert "批量接受范围" in response.text
    assert "自动刷新：{mode} {sec}s" in response.text
    assert "前台" in response.text
    assert "快捷模板" in response.text
    assert "管理模板" in response.text
    assert "设为文档默认" in response.text
    assert "查看 unified diff" in response.text


def test_create_document_rejects_blank_title(client, auth_headers):
    response = client.post(
        "/api/docs",
        headers=auth_headers,
        json={
            "title": "   ",
            "raw_markdown": "# Title\n",
            "actor": "browser",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_update_document_rejects_blank_title(client, auth_headers):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n", title="Doc")

    response = client.put(
        f"/api/docs/{created['id']}",
        headers=auth_headers,
        json={
            "title": "   ",
            "raw_markdown": "# Title\n\nAlpha\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "blank title",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_pickup_next_task_rejects_blank_agent_name(client, auth_headers):
    response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_document_update_versions_and_rollback(client, auth_headers):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n")
    doc_id = created["id"]

    get_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["blocks"][0]["heading"] == "Title"

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Title v2",
            "raw_markdown": "# Title\n\nBeta\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["revision"] == 2

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    versions = versions_response.json()["data"]
    assert [item["revision"] for item in versions] == [2, 1]

    rollback_response = client.post(
        f"/api/docs/{doc_id}/versions/{versions[-1]['id']}/rollback",
        headers=auth_headers,
        json={
            "expected_revision": 2,
            "actor": "browser",
            "note": "rollback",
        },
    )
    assert rollback_response.status_code == 200
    rollback_data = rollback_response.json()["data"]
    assert rollback_data["revision"] == 3
    assert rollback_data["raw_markdown"] == "# Title\n\nAlpha\n"


def test_delete_document_removes_document_and_related_records(client, auth_headers):
    raw_markdown = "# Title\n\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    delete_response = client.delete(f"/api/docs/{doc_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == doc_id

    get_doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert get_doc_response.status_code == 404

    get_task_response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)
    assert get_task_response.status_code == 404


def test_rollback_to_current_snapshot_is_noop(client, auth_headers):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n")
    doc_id = created["id"]

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    version = versions_response.json()["data"][0]

    rollback_response = client.post(
        f"/api/docs/{doc_id}/versions/{version['id']}/rollback",
        headers=auth_headers,
        json={
            "expected_revision": 1,
            "actor": "browser",
            "note": "noop rollback",
        },
    )
    assert rollback_response.status_code == 200
    rollback_data = rollback_response.json()["data"]
    assert rollback_data["revision"] == 1

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert len(versions_response.json()["data"]) == 1


def test_document_noop_update_does_not_create_new_version(client, auth_headers):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n", title="Doc")
    doc_id = created["id"]

    noop_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n\nAlpha\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "noop edit",
        },
    )
    assert noop_response.status_code == 200
    noop_data = noop_response.json()["data"]
    assert noop_data["revision"] == 1
    assert noop_data["raw_markdown"] == "# Title\n\nAlpha\n"

    title_only_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc Renamed",
            "raw_markdown": "# Title\n\nAlpha\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "rename only",
        },
    )
    assert title_only_response.status_code == 200
    title_only_data = title_only_response.json()["data"]
    assert title_only_data["title"] == "Doc Renamed"
    assert title_only_data["revision"] == 1

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    versions = versions_response.json()["data"]
    assert len(versions) == 1
    assert versions[0]["revision"] == 1


def test_task_accept_updates_document_and_versions(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    next_response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    assert next_response.status_code == 200
    assert next_response.json()["data"]["status"] == "processing"

    complete_response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["status"] == "done"

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 1,
            "actor": "browser",
            "note": "accept task",
        },
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["data"]["status"] == "accepted"

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["raw_markdown"] == "# Title\n## Section\nHi world\n"
    assert doc_response.json()["data"]["revision"] == 2

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    assert [item["revision"] for item in versions_response.json()["data"]] == [2, 1]


def test_task_reject_and_cancel_do_not_change_document(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    pending_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")
    cancel_response = client.post(
        f"/api/tasks/{pending_task['id']}/cancel",
        headers=auth_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["data"]["status"] == "cancelled"

    second_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "world")
    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{second_task['id']}/complete",
        headers=auth_headers,
        json={"result": "planet", "error_message": None},
    )
    reject_response = client.post(
        f"/api/tasks/{second_task['id']}/reject",
        headers=auth_headers,
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["status"] == "rejected"

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.json()["data"]["raw_markdown"] == raw_markdown
    assert doc_response.json()["data"]["revision"] == 1


def test_accept_ready_tasks_accepts_multiple_safe_done_tasks(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    hello_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")
    world_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "world")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{hello_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    client.post(
        f"/api/tasks/{world_task['id']}/complete",
        headers=auth_headers,
        json={"result": "planet", "error_message": None},
    )

    response = client.post(
        f"/api/docs/{doc_id}/tasks/accept-ready",
        headers=auth_headers,
        json={"actor": "browser", "note": "bulk accept"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "doc_id": doc_id,
        "document_revision": 3,
        "accepted": 2,
        "skipped": 0,
        "accepted_task_ids": [world_task["id"], hello_task["id"]],
        "skipped_tasks": [],
    }

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["raw_markdown"] == "# Title\n## Section\nHi planet\n"
    assert doc_response.json()["data"]["revision"] == 3


def test_accept_ready_tasks_skips_stale_results_and_accepts_safe_ones(client, auth_headers):
    raw_markdown = "# Title\n## A\nHello\n## B\nWorld\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    stale_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")
    safe_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "World")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{stale_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    client.post(
        f"/api/tasks/{safe_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Planet", "error_message": None},
    )

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## A\nHallo\n## B\nWorld\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "make first task stale",
        },
    )
    assert update_response.status_code == 200

    response = client.post(
        f"/api/docs/{doc_id}/tasks/accept-ready",
        headers=auth_headers,
        json={"actor": "browser", "note": "bulk accept"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["accepted"] == 1
    assert data["skipped"] == 1
    assert data["accepted_task_ids"] == [safe_task["id"]]
    assert data["skipped_tasks"] == [{"task_id": stale_task["id"], "reason": "task_stale"}]
    assert data["document_revision"] == 3

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["raw_markdown"] == "# Title\n## A\nHallo\n## B\nPlanet\n"


def test_accept_ready_tasks_can_filter_by_action_and_range(client, auth_headers):
    raw_markdown = "# Title\n## First\nAlpha\n## Second\nBeta\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    alpha_start = raw_markdown.index("Alpha")
    beta_start = raw_markdown.index("Beta")
    alpha_task_response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "instruction": "rewrite alpha",
            "source_text": "Alpha",
            "start_offset": alpha_start,
            "end_offset": alpha_start + len("Alpha"),
            "doc_revision": 1,
        },
    )
    assert alpha_task_response.status_code == 200
    alpha_task = alpha_task_response.json()["data"]

    beta_task_response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "summarize",
            "instruction": "summarize beta",
            "source_text": "Beta",
            "start_offset": beta_start,
            "end_offset": beta_start + len("Beta"),
            "doc_revision": 1,
        },
    )
    assert beta_task_response.status_code == 200
    beta_task = beta_task_response.json()["data"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{alpha_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Gamma", "error_message": None},
    )
    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    client.post(
        f"/api/tasks/{beta_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Delta", "error_message": None},
    )

    response = client.post(
        f"/api/docs/{doc_id}/tasks/accept-ready",
        headers=auth_headers,
        json={
            "actor": "browser",
            "note": "filtered accept",
            "action": "rewrite",
            "start_offset": raw_markdown.index("## First"),
            "end_offset": raw_markdown.index("## Second"),
            "limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["accepted"] == 1
    assert data["skipped"] == 0
    assert data["accepted_task_ids"] == [alpha_task["id"]]

    alpha_response = client.get(f"/api/tasks/{alpha_task['id']}", headers=auth_headers)
    beta_response = client.get(f"/api/tasks/{beta_task['id']}", headers=auth_headers)
    assert alpha_response.status_code == 200
    assert beta_response.status_code == 200
    assert alpha_response.json()["data"]["status"] == "accepted"
    assert beta_response.json()["data"]["status"] == "done"

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["raw_markdown"] == "# Title\n## First\nGamma\n## Second\nBeta\n"


def test_relocate_done_task_finds_unique_match_in_same_block(client, auth_headers):
    raw_markdown = "# Title\n## Section\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Gamma", "error_message": None},
    )

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nBeta Alpha\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "shift target within same block",
        },
    )
    assert update_response.status_code == 200

    relocate_response = client.post(
        f"/api/tasks/{task['id']}/relocate",
        headers=auth_headers,
    )
    assert relocate_response.status_code == 200
    relocate_data = relocate_response.json()["data"]
    assert relocate_data["relocation_strategy"] == "same_block_position_match"
    assert relocate_data["task"]["doc_revision"] == 2
    assert relocate_data["task"]["is_stale"] is False

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    assert diff_response.json()["data"]["can_accept"] is True

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 2,
            "actor": "browser",
            "note": "accept after relocation",
        },
    )
    assert accept_response.status_code == 200

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["raw_markdown"] == "# Title\n## Section\nBeta Gamma\n"


def test_relocate_rejected_task_allows_retry_after_manual_edit(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nStart Hello\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "shift content",
        },
    )
    client.post(
        f"/api/docs/{doc_id}/tasks/cleanup-stale",
        headers=auth_headers,
    )

    relocate_response = client.post(
        f"/api/tasks/{task['id']}/relocate",
        headers=auth_headers,
    )
    assert relocate_response.status_code == 200
    assert relocate_response.json()["data"]["relocation_strategy"] == "same_block_position_match"
    assert relocate_response.json()["data"]["task"]["doc_revision"] == 2

    retry_response = client.post(
        f"/api/tasks/{task['id']}/retry",
        headers=auth_headers,
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["data"]["status"] == "pending"
    assert retry_response.json()["data"]["doc_revision"] == 2


def test_relocate_returns_conflict_when_source_is_ambiguous(client, auth_headers):
    raw_markdown = "# Title\n## Section\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## First\nAlpha\n## Second\nAlpha\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "duplicate source text",
        },
    )
    assert update_response.status_code == 200

    relocate_response = client.post(
        f"/api/tasks/{task['id']}/relocate",
        headers=auth_headers,
    )
    assert relocate_response.status_code == 409
    assert relocate_response.json()["error"]["code"] == "conflict"


def test_pickup_next_task_includes_context_window_and_block_metadata(client, auth_headers):
    raw_markdown = "# Title\n## Background\nAlpha beta gamma\n## Next\nMore\n"
    created = create_document(client, auth_headers, raw_markdown, title="Knowledge Base")
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "beta")

    response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == task["id"]
    assert data["status"] == "processing"
    assert data["is_stale"] is False
    assert data["recommended_action"] is None
    assert data["context"] == {
        "document_title": "Knowledge Base",
        "document_revision": 1,
        "current_selection_text": "beta",
        "block": {
            "heading": "Background",
            "level": 2,
            "position": 1,
            "start_offset": raw_markdown.index("## Background"),
            "end_offset": raw_markdown.index("## Next"),
        },
        "block_markdown": "## Background\nAlpha beta gamma\n",
        "heading_path": [
            {"heading": "Title", "level": 1, "position": 0},
            {"heading": "Background", "level": 2, "position": 1},
        ],
        "document_outline": [
            {"heading": "Title", "level": 1, "position": 0},
            {"heading": "Background", "level": 2, "position": 1},
            {"heading": "Next", "level": 2, "position": 2},
        ],
        "context_before": "# Title\n## Background\nAlpha ",
        "context_after": " gamma\n## Next\nMore\n",
    }


def test_pickup_next_task_reports_stale_state_and_current_context(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown, title="Doc")
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit before pickup",
        },
    )
    assert update_response.status_code == 200

    next_response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    assert next_response.status_code == 200

    task_data = next_response.json()["data"]
    assert task_data["id"] == task["id"]
    assert task_data["status"] == "processing"
    assert task_data["is_stale"] is True
    assert task_data["stale_reason"] == "source_changed"
    assert task_data["recommended_action"] == "cancel"
    assert task_data["context"]["document_revision"] == 2
    assert task_data["context"]["current_selection_text"] == "Hallo"
    assert task_data["context"]["block"]["heading"] == "Section"
    assert task_data["context"]["block_markdown"] == "## Section\nHallo world\n"
    assert task_data["context"]["heading_path"] == [
        {"heading": "Title", "level": 1, "position": 0},
        {"heading": "Section", "level": 2, "position": 1},
    ]


def test_get_task_includes_current_context_snapshot(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown, title="Doc")
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "world")

    response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["context"] == {
        "document_title": "Doc",
        "document_revision": 1,
        "current_selection_text": "world",
        "block": {
            "heading": "Section",
            "level": 2,
            "position": 1,
            "start_offset": raw_markdown.index("## Section"),
            "end_offset": len(raw_markdown),
        },
        "block_markdown": "## Section\nHello world\n",
        "heading_path": [
            {"heading": "Title", "level": 1, "position": 0},
            {"heading": "Section", "level": 2, "position": 1},
        ],
        "document_outline": [
            {"heading": "Title", "level": 1, "position": 0},
            {"heading": "Section", "level": 2, "position": 1},
        ],
        "context_before": "# Title\n## Section\nHello ",
        "context_after": "\n",
    }


def test_get_task_context_heading_path_tracks_nested_sections(client, auth_headers):
    raw_markdown = "# Root\n## Chapter\n### Detail\nAlpha beta\n## Tail\nDone\n"
    created = create_document(client, auth_headers, raw_markdown, title="Outline Doc")
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "beta")

    response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)

    assert response.status_code == 200
    context = response.json()["data"]["context"]
    assert context["heading_path"] == [
        {"heading": "Root", "level": 1, "position": 0},
        {"heading": "Chapter", "level": 2, "position": 1},
        {"heading": "Detail", "level": 3, "position": 2},
    ]
    assert context["document_outline"] == [
        {"heading": "Root", "level": 1, "position": 0},
        {"heading": "Chapter", "level": 2, "position": 1},
        {"heading": "Detail", "level": 3, "position": 2},
        {"heading": "Tail", "level": 2, "position": 3},
    ]


def test_document_task_defaults_can_be_saved_without_new_revision(client, auth_headers):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n", title="Doc")

    get_response = client.get(f"/api/docs/{created['id']}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["default_task_action"] == "rewrite"
    assert get_response.json()["data"]["default_task_instruction"] is None

    update_response = client.post(
        f"/api/docs/{created['id']}/task-defaults",
        headers=auth_headers,
        json={
            "actor": "browser",
            "default_task_action": "expand",
            "default_task_instruction": "补充背景与上下文",
        },
    )

    assert update_response.status_code == 200
    data = update_response.json()["data"]
    assert data["revision"] == 1
    assert data["default_task_action"] == "expand"
    assert data["default_task_instruction"] == "补充背景与上下文"

    get_response = client.get(f"/api/docs/{created['id']}", headers=auth_headers)
    assert get_response.status_code == 200
    persisted = get_response.json()["data"]
    assert persisted["default_task_action"] == "expand"
    assert persisted["default_task_instruction"] == "补充背景与上下文"


def test_task_templates_crud(client, auth_headers):
    list_response = client.get("/api/task-templates", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["data"] == []

    create_response = client.post(
        "/api/task-templates",
        headers=auth_headers,
        json={
            "name": "技术方案润色",
            "action": "rewrite",
            "instruction": "改成克制、正式、适合项目文档的表述。",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["name"] == "技术方案润色"

    update_response = client.put(
        f"/api/task-templates/{created['id']}",
        headers=auth_headers,
        json={
            "name": "技术方案精简润色",
            "action": "summarize",
            "instruction": "压缩成 3 句以内，保留关键事实。",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["name"] == "技术方案精简润色"
    assert updated["action"] == "summarize"

    list_response = client.get("/api/task-templates", headers=auth_headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["data"]] == [created["id"]]

    delete_response = client.delete(
        f"/api/task-templates/{created['id']}", headers=auth_headers
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["id"] == created["id"]

    list_response = client.get("/api/task-templates", headers=auth_headers)
    assert list_response.status_code == 200
    assert list_response.json()["data"] == []


def test_task_recovery_preview_prefers_relocation_when_possible(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown, title="Doc")
    task, _, _ = create_task(client, auth_headers, created["id"], raw_markdown, "Hello")

    update_response = client.put(
        f"/api/docs/{created['id']}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nStart Hello world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "insert prefix",
        },
    )
    assert update_response.status_code == 200

    preview_response = client.get(
        f"/api/tasks/{task['id']}/recovery-preview",
        headers=auth_headers,
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["is_stale"] is True
    assert preview["can_relocate"] is True
    assert preview["relocation_strategy"] == "same_block_position_match"
    assert preview["can_requeue_from_current"] is True
    assert preview["recommended_mode"] == "relocate"


def test_task_recover_requeue_from_current_creates_new_pending_task(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown, title="Doc")
    task, _, _ = create_task(client, auth_headers, created["id"], raw_markdown, "Hello")

    update_response = client.put(
        f"/api/docs/{created['id']}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit before recovery",
        },
    )
    assert update_response.status_code == 200

    recover_response = client.post(
        f"/api/tasks/{task['id']}/recover",
        headers=auth_headers,
        json={"mode": "requeue_from_current", "actor": "browser"},
    )
    assert recover_response.status_code == 200
    data = recover_response.json()["data"]
    assert data["mode"] == "requeue_from_current"
    assert data["closed_source_status"] == "cancelled"
    assert data["source_task"]["status"] == "cancelled"
    assert data["new_task"]["status"] == "pending"
    assert data["new_task"]["doc_revision"] == 2
    assert data["new_task"]["source_text"] == "Hallo"
    assert data["new_task"]["context"]["current_selection_text"] == "Hallo"

    list_response = client.get(
        f"/api/tasks?doc_id={created['id']}", headers=auth_headers
    )
    assert list_response.status_code == 200
    statuses = {item["id"]: item["status"] for item in list_response.json()["data"]}
    assert statuses[task["id"]] == "cancelled"
    assert data["new_task"]["id"] in statuses


def test_task_recover_with_relocate_mode_updates_offsets(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown, title="Doc")
    task, start_offset, end_offset = create_task(
        client, auth_headers, created["id"], raw_markdown, "Hello"
    )

    update_response = client.put(
        f"/api/docs/{created['id']}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nStart Hello world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "insert prefix",
        },
    )
    assert update_response.status_code == 200

    recover_response = client.post(
        f"/api/tasks/{task['id']}/recover",
        headers=auth_headers,
        json={"mode": "relocate", "actor": "browser"},
    )
    assert recover_response.status_code == 200
    data = recover_response.json()["data"]
    assert data["mode"] == "relocate"
    assert data["relocation_strategy"] == "same_block_position_match"
    assert data["new_task"] is None
    assert data["source_task"]["start_offset"] > start_offset
    assert data["source_task"]["end_offset"] > end_offset
    assert data["source_task"]["doc_revision"] == 2


def test_task_create_rejects_cross_block_range(client, auth_headers):
    raw_markdown = "## A\nAlpha\n## B\nBeta\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    start_offset = raw_markdown.index("Alpha")
    end_offset = raw_markdown.index("Beta") + len("Beta")

    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "instruction": "rewrite text",
            "source_text": raw_markdown[start_offset:end_offset],
            "start_offset": start_offset,
            "end_offset": end_offset,
            "doc_revision": 1,
            "actor": "browser",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_accept_detects_revision_conflict_after_manual_edit(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit",
        },
    )

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 2,
            "actor": "browser",
            "note": "accept task",
        },
    )
    assert accept_response.status_code == 409
    assert accept_response.json()["error"]["code"] == "conflict"


def test_complete_with_error_marks_task_failed(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    complete_response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": None, "error_message": "model timeout"},
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["data"]["status"] == "failed"

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 1,
            "actor": "browser",
            "note": "accept task",
        },
    )
    assert accept_response.status_code == 409
    assert accept_response.json()["error"]["code"] == "invalid_state"


def test_task_diff_and_retry_flow(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_data = diff_response.json()["data"]
    assert diff_data["can_accept"] is True
    assert "--- source" in diff_data["diff"]
    assert "+Hi" in diff_data["diff"]

    reject_response = client.post(
        f"/api/tasks/{task['id']}/reject",
        headers=auth_headers,
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["data"]["status"] == "rejected"

    retry_response = client.post(
        f"/api/tasks/{task['id']}/retry",
        headers=auth_headers,
    )
    assert retry_response.status_code == 200
    retry_data = retry_response.json()["data"]
    assert retry_data["status"] == "pending"
    assert retry_data["result"] is None
    assert retry_data["agent_name"] is None

    next_response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    assert next_response.status_code == 200
    assert next_response.json()["data"]["id"] == task["id"]
    assert next_response.json()["data"]["status"] == "processing"


def test_retry_rejects_stale_task_when_document_changed(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": None, "error_message": "timeout"},
    )
    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit",
        },
    )

    retry_response = client.post(
        f"/api/tasks/{task['id']}/retry",
        headers=auth_headers,
    )
    assert retry_response.status_code == 422
    assert retry_response.json()["error"]["code"] == "validation_error"


def test_deleted_source_text_blocks_accept_and_retry(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nworld\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "remove task source",
        },
    )

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 2,
            "actor": "browser",
            "note": "accept after delete",
        },
    )
    assert accept_response.status_code == 409
    assert accept_response.json()["error"]["code"] == "conflict"

    reject_response = client.post(
        f"/api/tasks/{task['id']}/reject",
        headers=auth_headers,
    )
    assert reject_response.status_code == 200

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    assert diff_response.json()["data"]["conflict_reason"] is None
    assert diff_response.json()["data"]["can_accept"] is False
    task_response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)
    assert task_response.status_code == 200
    assert task_response.json()["data"]["is_stale"] is False
    assert task_response.json()["data"]["stale_reason"] is None
    assert task_response.json()["data"]["recommended_action"] is None

    retry_response = client.post(
        f"/api/tasks/{task['id']}/retry",
        headers=auth_headers,
    )
    assert retry_response.status_code == 422
    assert retry_response.json()["error"]["code"] == "validation_error"


def test_retry_flow_still_conflicts_after_second_manual_edit(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.post(
        f"/api/tasks/{task['id']}/reject",
        headers=auth_headers,
    )
    retry_response = client.post(
        f"/api/tasks/{task['id']}/retry",
        headers=auth_headers,
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["data"]["doc_revision"] == 1

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hey", "error_message": None},
    )
    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit after retry",
        },
    )

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_data = diff_response.json()["data"]
    assert diff_data["conflict_reason"] == "source_changed"


def test_cleanup_stale_tasks_closes_outdated_pending_and_done_tasks(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    pending_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "world")
    done_task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{pending_task['id']}/cancel",
        headers=auth_headers,
    )
    client.post(
        f"/api/tasks/{pending_task['id']}/retry",
        headers=auth_headers,
    )

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-two"},
    )
    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-three"},
    )
    client.post(
        f"/api/tasks/{done_task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nChanged text\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "make tasks stale",
        },
    )

    cleanup_response = client.post(
        f"/api/docs/{doc_id}/tasks/cleanup-stale",
        headers=auth_headers,
    )
    assert cleanup_response.status_code == 200
    cleanup_data = cleanup_response.json()["data"]
    assert cleanup_data == {
        "doc_id": doc_id,
        "cancelled": 1,
        "rejected": 1,
        "unchanged": 0,
    }

    pending_response = client.get(f"/api/tasks/{pending_task['id']}", headers=auth_headers)
    assert pending_response.status_code == 200
    assert pending_response.json()["data"]["status"] == "cancelled"

    done_response = client.get(f"/api/tasks/{done_task['id']}", headers=auth_headers)
    assert done_response.status_code == 200
    assert done_response.json()["data"]["status"] == "rejected"


def test_accepted_task_is_not_marked_stale_after_later_document_edits(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 1,
            "actor": "browser",
            "note": "accept task",
        },
    )
    assert accept_response.status_code == 200

    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHi universe\n",
            "expected_revision": 2,
            "actor": "browser",
            "note": "edit after accept",
        },
    )

    task_response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)
    assert task_response.status_code == 200
    task_data = task_response.json()["data"]
    assert task_data["status"] == "accepted"
    assert task_data["is_stale"] is False
    assert task_data["stale_reason"] is None

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    assert diff_response.json()["data"]["can_accept"] is False


def test_rejected_task_is_not_marked_stale_after_later_document_edits(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )
    client.post(
        f"/api/tasks/{task['id']}/reject",
        headers=auth_headers,
    )

    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nHallo world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "edit after reject",
        },
    )

    task_response = client.get(f"/api/tasks/{task['id']}", headers=auth_headers)
    assert task_response.status_code == 200
    task_data = task_response.json()["data"]
    assert task_data["status"] == "rejected"
    assert task_data["is_stale"] is False
    assert task_data["stale_reason"] is None

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    assert diff_response.json()["data"]["can_accept"] is False


def test_accept_identical_result_does_not_create_new_revision(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hello", "error_message": None},
    )

    accept_response = client.post(
        f"/api/tasks/{task['id']}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 1,
            "actor": "browser",
            "note": "accept same result",
        },
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["data"]["status"] == "accepted"

    doc_response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert doc_response.status_code == 200
    assert doc_response.json()["data"]["revision"] == 1
    assert doc_response.json()["data"]["raw_markdown"] == raw_markdown

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    assert len(versions_response.json()["data"]) == 1


def test_rollback_keeps_old_done_task_blocked_when_source_no_longer_matches(
    client, auth_headers
):
    created = create_document(client, auth_headers, "# Title\n\nAlpha\n")
    doc_id = created["id"]

    update_response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n\nBeta\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "move to beta",
        },
    )
    assert update_response.status_code == 200

    task_response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "instruction": "rewrite beta",
            "source_text": "Beta",
            "start_offset": "# Title\n\n".__len__(),
            "end_offset": "# Title\n\nBeta".__len__(),
            "doc_revision": 2,
            "actor": "browser",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["data"]["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "agent-one"},
    )
    client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "Gamma", "error_message": None},
    )

    versions_response = client.get(f"/api/docs/{doc_id}/versions", headers=auth_headers)
    assert versions_response.status_code == 200
    version_id = versions_response.json()["data"][-1]["id"]

    rollback_response = client.post(
        f"/api/docs/{doc_id}/versions/{version_id}/rollback",
        headers=auth_headers,
        json={
            "expected_revision": 2,
            "actor": "browser",
            "note": "back to alpha",
        },
    )
    assert rollback_response.status_code == 200
    assert rollback_response.json()["data"]["raw_markdown"] == "# Title\n\nAlpha\n"

    diff_response = client.get(f"/api/tasks/{task_id}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_data = diff_response.json()["data"]
    assert diff_data["can_accept"] is False
    assert diff_data["current_text"] == "Alph"
    assert diff_data["source_text"] == "Beta"

    accept_response = client.post(
        f"/api/tasks/{task_id}/accept",
        headers=auth_headers,
        json={
            "expected_revision": 3,
            "actor": "browser",
            "note": "accept after rollback",
        },
    )
    assert accept_response.status_code == 409
    assert accept_response.json()["error"]["code"] == "conflict"


def test_diff_returns_recommended_action_for_stale_done_task(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post("/api/tasks/next", headers=auth_headers, json={"agent_name": "agent-one"})
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "Doc",
            "raw_markdown": "# Title\n## Section\nBye world\n",
            "expected_revision": 1,
            "actor": "browser",
            "note": "manual edit",
        },
    )

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_data = diff_response.json()["data"]
    assert diff_data["can_accept"] is False
    assert diff_data["recommended_action"] == "reject"
    assert diff_data["conflict_reason"] is not None


def test_diff_returns_no_recommended_action_for_clean_done_task(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    client.post("/api/tasks/next", headers=auth_headers, json={"agent_name": "agent-one"})
    client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "Hi", "error_message": None},
    )

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 200
    diff_data = diff_response.json()["data"]
    assert diff_data["can_accept"] is True
    assert diff_data["recommended_action"] is None
    assert diff_data["conflict_reason"] is None


def test_diff_rejects_task_without_result(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Hello")

    diff_response = client.get(f"/api/tasks/{task['id']}/diff", headers=auth_headers)
    assert diff_response.status_code == 409
    assert diff_response.json()["error"]["code"] == "invalid_state"


def test_batch_accept_returns_empty_result_when_no_tasks_match(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks/accept-ready",
        headers=auth_headers,
        json={"actor": "browser"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["accepted"] == 0
    assert data["skipped"] == 0
    assert data["accepted_task_ids"] == []
    assert data["skipped_tasks"] == []


def test_document_parse_blocks_with_no_headings(client, auth_headers):
    raw_markdown = "Just plain text without any headings.\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["blocks"]) == 1
    assert data["blocks"][0]["heading"] == ""
    assert data["blocks"][0]["level"] == 0
    assert data["blocks"][0]["start_offset"] == 0
    assert data["blocks"][0]["end_offset"] == len(raw_markdown)


def test_document_parse_blocks_with_empty_content(client, auth_headers):
    raw_markdown = ""
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.get(f"/api/docs/{doc_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["blocks"] == []


def test_create_task_rejects_blank_action(client, auth_headers):
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    needle = "Content"
    start_offset = raw_markdown.index(needle)
    end_offset = start_offset + len(needle)

    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "   ",
            "instruction": "rewrite text",
            "source_text": needle,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "doc_revision": 1,
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Edge-case and regression tests
# ---------------------------------------------------------------------------


def test_complete_task_with_empty_string_result(client, auth_headers):
    """An empty-string result should be accepted (it may represent a deletion)."""
    raw_markdown = "# Heading\nSome text\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Some text")
    task_id = task["id"]

    # Pickup the task
    pickup = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    assert pickup.status_code == 200

    # Complete with empty string result
    response = client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "", "error_message": None},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "done"
    assert data["result"] == ""


def test_complete_task_rejects_both_result_and_error(client, auth_headers):
    """Providing both result and error_message should be rejected."""
    raw_markdown = "# Heading\nSome text\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Some text")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )

    response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "rewritten", "error_message": "also error"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_complete_task_rejects_neither_result_nor_error(client, auth_headers):
    """Providing neither result nor error_message should be rejected."""
    raw_markdown = "# Heading\nSome text\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Some text")

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )

    response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": None, "error_message": None},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_task_create_rejects_revision_mismatch(client, auth_headers):
    """Creating a task with a stale doc_revision should fail."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "source_text": "Alpha",
            "start_offset": raw_markdown.index("Alpha"),
            "end_offset": raw_markdown.index("Alpha") + len("Alpha"),
            "doc_revision": 999,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_task_create_rejects_out_of_range_offsets(client, auth_headers):
    """Creating a task with offsets exceeding document length should fail."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "source_text": "Alpha",
            "start_offset": 0,
            "end_offset": 10000,
            "doc_revision": 1,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_task_create_rejects_source_text_mismatch(client, auth_headers):
    """Creating a task where source_text doesn't match the document at offsets should fail."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks",
        headers=auth_headers,
        json={
            "action": "rewrite",
            "source_text": "wrong text",
            "start_offset": raw_markdown.index("Alpha"),
            "end_offset": raw_markdown.index("Alpha") + len("Alpha"),
            "doc_revision": 1,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_accept_task_rejects_already_accepted_task(client, auth_headers):
    """An already-accepted task cannot be accepted again."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "Beta"},
    )
    client.post(
        f"/api/tasks/{task_id}/accept",
        headers=auth_headers,
        json={"expected_revision": 1, "actor": "browser"},
    )

    # Try to accept again
    response = client.post(
        f"/api/tasks/{task_id}/accept",
        headers=auth_headers,
        json={"expected_revision": 2, "actor": "browser"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_reject_task_rejects_non_done_task(client, auth_headers):
    """A pending or processing task cannot be rejected."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")

    response = client.post(
        f"/api/tasks/{task['id']}/reject",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_cancel_rejects_done_task(client, auth_headers):
    """A done task cannot be cancelled."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "Beta"},
    )

    response = client.post(
        f"/api/tasks/{task_id}/cancel",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_retry_rejects_done_task(client, auth_headers):
    """A done task cannot be retried (must be rejected or cancelled first)."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "Beta"},
    )

    response = client.post(
        f"/api/tasks/{task_id}/retry",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_recover_rejects_accepted_task(client, auth_headers):
    """An already-accepted task cannot be recovered."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    client.post(
        f"/api/tasks/{task_id}/complete",
        headers=auth_headers,
        json={"result": "Beta"},
    )
    client.post(
        f"/api/tasks/{task_id}/accept",
        headers=auth_headers,
        json={"expected_revision": 1, "actor": "browser"},
    )

    response = client.post(
        f"/api/tasks/{task_id}/recover",
        headers=auth_headers,
        json={"mode": "requeue_from_current", "actor": "browser"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_relocate_rejects_processing_task(client, auth_headers):
    """A processing task cannot be relocated."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )

    response = client.post(
        f"/api/tasks/{task_id}/relocate",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_get_nonexistent_document_returns_404(client, auth_headers):
    """Getting a document that doesn't exist returns 404."""
    response = client.get("/api/docs/99999", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_get_nonexistent_task_returns_404(client, auth_headers):
    """Getting a task that doesn't exist returns 404."""
    response = client.get("/api/tasks/99999", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_update_nonexistent_template_returns_404(client, auth_headers):
    """Updating a template that doesn't exist returns 404."""
    response = client.put(
        "/api/task-templates/99999",
        headers=auth_headers,
        json={"name": "Test", "action": "rewrite", "instruction": "test"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_nonexistent_template_returns_404(client, auth_headers):
    """Deleting a template that doesn't exist returns 404."""
    response = client.delete(
        "/api/task-templates/99999",
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_pickup_returns_null_when_no_pending_tasks(client, auth_headers):
    """POST /api/tasks/next returns null when there are no pending tasks."""
    response = client.post(
        "/api/tasks/next",
        headers=auth_headers,
        json={"agent_name": "test-agent"},
    )
    assert response.status_code == 200
    assert response.json()["data"] is None


def test_list_tasks_filters_by_status_and_doc_id(client, auth_headers):
    """Task list should support filtering by status and doc_id."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")

    # Filter by status
    response = client.get(
        f"/api/tasks?status=pending&doc_id={doc_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "pending"

    # Filter by different status returns empty
    response = client.get(
        f"/api/tasks?status=done&doc_id={doc_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 0


def test_template_create_rejects_blank_fields(client, auth_headers):
    """Template creation should reject blank name, action, or instruction."""
    response = client.post(
        "/api/task-templates",
        headers=auth_headers,
        json={"name": "   ", "action": "rewrite", "instruction": "test"},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/task-templates",
        headers=auth_headers,
        json={"name": "Test", "action": "   ", "instruction": "test"},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/task-templates",
        headers=auth_headers,
        json={"name": "Test", "action": "rewrite", "instruction": "   "},
    )
    assert response.status_code == 422


def test_recovery_preview_for_non_stale_task(client, auth_headers):
    """Recovery preview should report a non-stale task correctly."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")
    task_id = task["id"]

    response = client.get(
        f"/api/tasks/{task_id}/recovery-preview",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_stale"] is False
    assert data["can_relocate"] is False
    assert data["can_requeue_from_current"] is False
    assert data["recommended_mode"] is None


def test_recover_with_unsupported_mode_returns_422(client, auth_headers):
    """Recover with an unsupported mode should return validation error."""
    raw_markdown = "# Heading\nAlpha\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Alpha")

    response = client.post(
        f"/api/tasks/{task['id']}/recover",
        headers=auth_headers,
        json={"mode": "invalid_mode", "actor": "browser"},
    )
    assert response.status_code == 422


def test_versions_for_nonexistent_document_returns_404(client, auth_headers):
    """Listing versions for a nonexistent document returns 404."""
    response = client.get("/api/docs/99999/versions", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_rollback_to_nonexistent_version_returns_404(client, auth_headers):
    """Rolling back to a nonexistent version returns 404."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/versions/99999/rollback",
        headers=auth_headers,
        json={"expected_revision": 1, "actor": "browser"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_title_only_update_does_not_increment_revision(client, auth_headers):
    """Updating only the title (not content) should not create a new revision."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.put(
        f"/api/docs/{doc_id}",
        headers=auth_headers,
        json={
            "title": "New Title",
            "raw_markdown": raw_markdown,
            "expected_revision": 1,
            "actor": "browser",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == "New Title"
    assert data["revision"] == 1

    # Check only 1 version exists (the initial creation)
    versions = client.get(
        f"/api/docs/{doc_id}/versions",
        headers=auth_headers,
    )
    assert len(versions.json()["data"]) == 1


def test_batch_accept_validates_range_parameters(client, auth_headers):
    """Providing only start_offset without end_offset should be rejected."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks/accept-ready",
        headers=auth_headers,
        json={"actor": "browser", "start_offset": 0},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_cleanup_stale_on_document_without_tasks(client, auth_headers):
    """Cleanup stale on a document with no tasks should return all zeros."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]

    response = client.post(
        f"/api/docs/{doc_id}/tasks/cleanup-stale",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cancelled"] == 0
    assert data["rejected"] == 0
    assert data["unchanged"] == 0


def test_diff_for_pending_task_without_result_returns_409(client, auth_headers):
    """Getting diff for a task without a result (pending) should return 409."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Content")

    response = client.get(
        f"/api/tasks/{task['id']}/diff",
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_complete_task_rejects_non_processing_task(client, auth_headers):
    """Completing a pending (not processing) task should fail."""
    raw_markdown = "# Title\nContent\n"
    created = create_document(client, auth_headers, raw_markdown)
    doc_id = created["id"]
    task, _, _ = create_task(client, auth_headers, doc_id, raw_markdown, "Content")

    response = client.post(
        f"/api/tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"result": "New Content"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_ui_does_not_contain_undefined_function_references(client):
    """The UI page should not reference undefined functions like syncKeyState."""
    response = client.get("/")
    assert response.status_code == 200
    assert "syncKeyState" not in response.text


def test_ui_contains_visibilitychange_listener(client):
    """The UI page should register a visibilitychange event listener for auto-refresh."""
    response = client.get("/")
    assert response.status_code == 200
    assert "addEventListener('visibilitychange', updateAutoRefreshPill)" in response.text