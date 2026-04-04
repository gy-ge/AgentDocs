import importlib.util
from pathlib import Path

from app.services.simulated_agent import build_simulated_result, process_next_task

from tests.test_api import create_document, create_task


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "simulate_agent.py"


def _load_simulate_agent_module():
    spec = importlib.util.spec_from_file_location("simulate_agent_script", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load simulate_agent module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientTaskApiAdapter:
    def __init__(self, client, auth_headers):
        self.client = client
        self.auth_headers = auth_headers

    def pickup_next_task(self, agent_name: str):
        response = self.client.post(
            "/api/tasks/next",
            headers=self.auth_headers,
            json={"agent_name": agent_name},
        )
        assert response.status_code == 200
        return response.json()["data"]

    def complete_task(
        self, task_id: int, *, result: str | None, error_message: str | None
    ):
        response = self.client.post(
            f"/api/tasks/{task_id}/complete",
            headers=self.auth_headers,
            json={"result": result, "error_message": error_message},
        )
        assert response.status_code == 200
        return response.json()["data"]


def test_build_simulated_result_preserves_trailing_newline():
    result = build_simulated_result(
        {
            "source_text": "Hello\n",
            "instruction": "rewrite text",
        }
    )

    assert result == "Hello [simulated-agent: rewrite text]\n"


def test_simulated_agent_processes_pending_task(client, auth_headers):
    raw_markdown = "# Title\n## Section\nHello world\n"
    document = create_document(client, auth_headers, raw_markdown)
    task, _, _ = create_task(
        client, auth_headers, document["id"], raw_markdown, "Hello"
    )

    api_client = ClientTaskApiAdapter(client, auth_headers)
    completed_task = process_next_task(
        api_client,
        agent_name="simulated-agent",
        mode="append",
    )

    assert completed_task is not None
    assert completed_task["status"] == "done"
    assert completed_task["agent_name"] == "simulated-agent"
    assert completed_task["result"] == "Hello [simulated-agent: rewrite text]"

    diff_response = client.get(
        f"/api/tasks/{task['id']}/diff",
        headers=auth_headers,
    )
    assert diff_response.status_code == 200
    assert diff_response.json()["data"]["can_accept"] is True


def test_simulated_agent_can_fail_task(client, auth_headers):
    raw_markdown = "# Title\n\nHello world\n"
    document = create_document(client, auth_headers, raw_markdown)
    create_task(client, auth_headers, document["id"], raw_markdown, "Hello")

    api_client = ClientTaskApiAdapter(client, auth_headers)
    completed_task = process_next_task(
        api_client,
        agent_name="simulated-agent",
        mode="fail",
    )

    assert completed_task is not None
    assert completed_task["status"] == "failed"
    assert completed_task["error_message"] == "simulated agent failure"


def test_simulated_agent_returns_none_when_queue_is_empty(client, auth_headers):
    api_client = ClientTaskApiAdapter(client, auth_headers)

    completed_task = process_next_task(
        api_client,
        agent_name="simulated-agent",
        mode="append",
    )

    assert completed_task is None


def test_simulate_agent_http_client_sends_gateway_safe_headers(monkeypatch):
    module = _load_simulate_agent_module()
    observed_headers: dict[str, str] = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok": true, "data": null}'

    def fake_urlopen(req, timeout=20):
        observed_headers.update(dict(req.header_items()))
        return DummyResponse()

    monkeypatch.setattr(module.request, "urlopen", fake_urlopen)

    client = module.HttpTaskApiClient("https://docs.example.com", "secret-key")
    result = client.pickup_next_task("simulated-agent")

    assert result is None
    assert observed_headers["Accept"] == "application/json"
    assert observed_headers["User-agent"] == "AgentDocsSimulatedAgent/1.0"
