"""Quick smoke checks against a running server."""
import json
import urllib.request

BASE = "http://127.0.0.1:5000"


def get(path: str):
    with urllib.request.urlopen(BASE + path) as resp:
        return resp.status, resp.read()


def post(path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


for path in ["/", "/api/docs/", "/api/system/stats", "/api/tasks?limit=5"]:
    status, _ = get(path)
    print(f"GET {path} -> {status}")

status, task = post(
    "/api/tasks",
    {
        "task_name": "to_cancel",
        "priority": "LOW",
        "payload": {"type": "DELAY", "seconds": 25},
        "max_retries": 0,
    },
)
print("created", task["id"], task["status"])
status, cancelled = post(f"/api/tasks/{task['id']}/cancel")
print("cancel ->", cancelled["status"])

status, body = get(f"/api/tasks/2/executions")
print("executions ->", status, json.loads(body.decode())["executions"][:1])
print("smoke OK")
