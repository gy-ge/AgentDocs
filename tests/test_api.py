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
    assert "删除文档" in response.text
    assert "清理失效" in response.text


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