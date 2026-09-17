const REFRESH_MS = 5000;

function payloadForType(type) {
  switch (type) {
    case "DELAY":
      return { type: "DELAY", seconds: 2 };
    case "DATA_PROCESSING":
      return { type: "DATA_PROCESSING", operation: "count", items: [1, 2, 3, 3, 4] };
    case "SEND_NOTIFICATION":
      return {
        type: "SEND_NOTIFICATION",
        email: "user@example.com",
        message: "Welcome from the dashboard",
      };
    case "FAIL":
      return { type: "FAIL", reason: "Dashboard forced failure" };
    case "CALCULATE":
    default:
      return { type: "CALCULATE", operation: "sum", numbers: [10, 20, 30] };
  }
}

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function canCancel(status) {
  return ["PENDING", "SCHEDULED", "RETRYING"].includes(status);
}

function canRetry(status) {
  return status === "FAILED";
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

async function refreshStats() {
  const stats = await fetchJSON("/api/system/stats");
  document.getElementById("stat-total").textContent = stats.total_tasks;
  document.getElementById("stat-pending").textContent = stats.pending_tasks;
  document.getElementById("stat-running").textContent = stats.running_tasks;
  document.getElementById("stat-completed").textContent = stats.completed_tasks;
  document.getElementById("stat-failed").textContent = stats.failed_tasks;
  document.getElementById("stat-workers").textContent = stats.active_workers;
}

async function refreshTasks() {
  const data = await fetchJSON("/api/tasks?limit=50");
  const body = document.getElementById("tasks-body");
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="8" class="muted">No tasks yet</td></tr>';
    return;
  }
  body.innerHTML = data.items
    .map((task) => {
      const actions = [];
      if (canCancel(task.status)) {
        actions.push(
          `<button class="btn danger" data-action="cancel" data-id="${task.id}">Cancel</button>`
        );
      }
      if (canRetry(task.status)) {
        actions.push(
          `<button class="btn retry" data-action="retry" data-id="${task.id}">Retry</button>`
        );
      }
      return `
        <tr>
          <td>${task.id}</td>
          <td>${escapeHtml(task.task_name)}</td>
          <td>${task.priority}</td>
          <td><span class="status ${task.status}">${task.status}</span></td>
          <td>${formatDate(task.created_at)}</td>
          <td>${formatDate(task.scheduled_at)}</td>
          <td>${task.worker_id ?? "—"}</td>
          <td class="actions">${actions.join("") || "—"}</td>
        </tr>`;
    })
    .join("");
}

async function refreshWorkers() {
  const data = await fetchJSON("/api/workers");
  const body = document.getElementById("workers-body");
  if (!data.items.length) {
    body.innerHTML = '<tr><td colspan="6" class="muted">No workers registered</td></tr>';
    return;
  }
  body.innerHTML = data.items
    .map(
      (w) => `
      <tr>
        <td>${w.id}</td>
        <td>${escapeHtml(w.worker_name)}</td>
        <td><span class="status ${w.status}">${w.status}</span></td>
        <td>${w.tasks_completed}</td>
        <td>${w.tasks_failed}</td>
        <td>${formatDate(w.last_heartbeat)}</td>
      </tr>`
    )
    .join("");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function refreshAll() {
  try {
    await Promise.all([refreshStats(), refreshTasks(), refreshWorkers()]);
  } catch (err) {
    console.error(err);
  }
}

document.getElementById("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const message = document.getElementById("form-message");
  const fd = new FormData(form);
  const body = {
    task_name: fd.get("task_name"),
    description: fd.get("description") || null,
    priority: fd.get("priority"),
    max_retries: Number(fd.get("max_retries")),
    payload: payloadForType(fd.get("type")),
    scheduled_at: null,
  };
  try {
    const task = await fetchJSON("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    message.hidden = false;
    message.classList.remove("error");
    message.textContent = `Created task #${task.id} (${task.status})`;
    form.reset();
    form.priority.value = "MEDIUM";
    form.max_retries.value = "3";
    await refreshAll();
  } catch (err) {
    message.hidden = false;
    message.classList.add("error");
    message.textContent = err.message;
  }
});

document.getElementById("tasks-body").addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;
  const id = btn.dataset.id;
  const action = btn.dataset.action;
  try {
    await fetchJSON(`/api/tasks/${id}/${action}`, { method: "POST" });
    await refreshAll();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById("manual-refresh").addEventListener("click", refreshAll);

refreshAll();
setInterval(refreshAll, REFRESH_MS);
