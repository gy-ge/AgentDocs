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
    assert "AgentDocs" in response.text
    assert "连接设置" in response.text
    assert "文档工作台" in response.text
    assert "已有文档" in response.text
    assert "新建文档" in response.text
    assert "任务动作" in response.text
    assert "任务处理" in response.text
    assert "创建任务" in response.text
    assert "导出 Markdown" in response.text
    assert "删除文档" in response.text
    assert "清理失效" in response.text
    assert "批量接受可合并结果" in response.text
    assert "批量接受范围" in response.text
    assert "自动刷新：前台 15s" in response.text
    assert "快捷模板" in response.text
    assert "最近说明" in response.text
    assert "管理模板" in response.text
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
        "block": {
            "heading": "Background",
            "level": 2,
            "position": 1,
            "start_offset": raw_markdown.index("## Background"),
            "end_offset": raw_markdown.index("## Next"),
        },
        "block_markdown": "## Background\nAlpha beta gamma\n",
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
    assert task_data["context"]["block"]["heading"] == "Section"
    assert task_data["context"]["block_markdown"] == "## Section\nHallo world\n"


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
        "block": {
            "heading": "Section",
            "level": 2,
            "position": 1,
            "start_offset": raw_markdown.index("## Section"),
            "end_offset": len(raw_markdown),
        },
        "block_markdown": "## Section\nHello world\n",
        "context_before": "# Title\n## Section\nHello ",
        "context_after": "\n",
    }


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