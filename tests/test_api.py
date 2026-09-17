"""API integration tests."""

from __future__ import annotations


def test_create_and_get_task(client):
    res = client.post(
        "/api/tasks",
        json={
            "task_name": "send_email",
            "description": "Send welcome email",
            "priority": "HIGH",
            "payload": {"type": "SEND_NOTIFICATION", "email": "user@example.com"},
            "scheduled_at": None,
            "max_retries": 3,
        },
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["id"] >= 1
    assert body["status"] == "PENDING"
    assert body["priority"] == "HIGH"

    get_res = client.get(f"/api/tasks/{body['id']}")
    assert get_res.status_code == 200
    assert get_res.get_json()["task_name"] == "send_email"


def test_invalid_create_returns_error(client):
    res = client.post("/api/tasks", json={"priority": "HIGH"})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_list_filter_and_pagination(client):
    for i, priority in enumerate(["LOW", "HIGH", "HIGH", "CRITICAL"]):
        client.post(
            "/api/tasks",
            json={
                "task_name": f"t{i}",
                "priority": priority,
                "payload": {"type": "CALCULATE", "operation": "sum", "numbers": [i]},
            },
        )

    high = client.get("/api/tasks?priority=HIGH")
    assert high.status_code == 200
    assert high.get_json()["total"] == 2

    page = client.get("/api/tasks?page=1&limit=2")
    data = page.get_json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["total"] == 4


def test_cancel_retry_executions(client):
    created = client.post(
        "/api/tasks",
        json={
            "task_name": "cancellable",
            "priority": "MEDIUM",
            "payload": {"type": "DELAY", "seconds": 1},
        },
    ).get_json()
    task_id = created["id"]

    cancel = client.post(f"/api/tasks/{task_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.get_json()["status"] == "CANCELLED"

    from app.extensions import db
    from app.models.task import Task, TaskStatus

    with client.application.app_context():
        task = db.session.get(Task, task_id)
        task.status = TaskStatus.FAILED
        db.session.commit()

    retry = client.post(f"/api/tasks/{task_id}/retry")
    assert retry.status_code == 200
    assert retry.get_json()["status"] == "PENDING"

    history = client.get(f"/api/tasks/{task_id}/executions")
    assert history.status_code == 200
    assert "executions" in history.get_json()


def test_workers_and_stats(client, sample_worker):
    workers = client.get("/api/workers")
    assert workers.status_code == 200
    assert workers.get_json()["items"]

    one = client.get(f"/api/workers/{sample_worker.id}")
    assert one.status_code == 200
    assert one.get_json()["worker_name"] == "Test-Worker-1"

    missing = client.get("/api/workers/99999")
    assert missing.status_code == 404

    stats = client.get("/api/system/stats")
    assert stats.status_code == 200
    body = stats.get_json()
    assert "total_tasks" in body
    assert "active_workers" in body


def test_dashboard_and_health(client):
    dash = client.get("/")
    assert dash.status_code == 200
    assert b"Distributed Task Scheduler" in dash.data

    health = client.get("/api/system/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"


def test_not_found_task(client):
    res = client.get("/api/tasks/99999")
    assert res.status_code == 404
    assert res.get_json()["status"] == 404


def test_swagger_docs(client):
    res = client.get("/api/docs/")
    assert res.status_code == 200
