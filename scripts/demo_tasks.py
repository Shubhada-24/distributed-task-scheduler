"""Demo helper: create prioritized tasks via the running API.

Usage (with the server already running on localhost:5000):

    python scripts/demo_tasks.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print(f"Demo against {BASE}")
    tasks = [
        ("Task A", "LOW", {"type": "DELAY", "seconds": 1}),
        ("Task B", "HIGH", {"type": "CALCULATE", "operation": "sum", "numbers": [1, 2, 3]}),
        ("Task C", "CRITICAL", {"type": "CALCULATE", "operation": "product", "numbers": [2, 3, 4]}),
        ("Task D", "MEDIUM", {"type": "DATA_PROCESSING", "operation": "count", "items": [1, 2, 3]}),
        ("Task E", "HIGH", {"type": "SEND_NOTIFICATION", "email": "demo@example.com", "message": "Hi"}),
        ("Task Fail", "MEDIUM", {"type": "FAIL", "reason": "Demo automatic retry"}),
    ]

    created = []
    for name, priority, payload in tasks:
        max_retries = 2 if payload["type"] == "FAIL" else 1
        task = post(
            "/api/tasks",
            {
                "task_name": name,
                "description": f"Demo {name}",
                "priority": priority,
                "payload": payload,
                "max_retries": max_retries,
            },
        )
        created.append(task)
        print(f"Created #{task['id']} {name} priority={priority} status={task['status']}")

    print("\nWaiting for workers to process...")
    time.sleep(8)

    print("\nFinal task states:")
    listing = get("/api/tasks?limit=50")
    for item in listing["items"]:
        if item["id"] in {t["id"] for t in created}:
            print(
                f"  #{item['id']} {item['task_name']:12} "
                f"{item['priority']:8} {item['status']:10} worker={item['worker_id']}"
            )

    print("\nSystem stats:")
    print(json.dumps(get("/api/system/stats"), indent=2))

    print("\nWorkers:")
    for w in get("/api/workers")["items"]:
        print(
            f"  {w['worker_name']}: {w['status']} "
            f"completed={w['tasks_completed']} failed={w['tasks_failed']}"
        )


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {BASE}: {exc}", file=sys.stderr)
        sys.exit(1)
