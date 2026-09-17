"""Thread-safe priority queue for scheduled tasks.

Complexity (n = number of queued tasks):
    push:   O(log n)
    pop:    O(log n) amortized (lazy deletion of cancelled entries)
    peek:   O(1) amortized after skipping cancelled entries
    remove: O(1)  (marks entry invalid; cleaned on pop/peek)
    size:   O(1)
    is_empty: O(1)
"""

from __future__ import annotations

import heapq
import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(order=True)
class QueueEntry:
    """Heap entry. Higher priority first; for ties, older tasks first.

    heapq is a min-heap, so we negate priority and use created_at ascending.
    """

    sort_key: tuple
    task_id: int = field(compare=False)
    priority: int = field(compare=False)
    created_at: datetime = field(compare=False)
    scheduled_at: datetime | None = field(compare=False, default=None)
    payload: dict[str, Any] | None = field(compare=False, default=None)


class PriorityTaskQueue:
    """In-memory priority queue backed by ``heapq`` with lazy removal."""

    def __init__(self) -> None:
        self._heap: list[QueueEntry] = []
        self._entry_finder: dict[int, QueueEntry] = {}
        self._counter = itertools.count()
        self._lock = threading.RLock()
        self._valid_count = 0

    def push(
        self,
        task_id: int,
        priority: int,
        created_at: datetime,
        scheduled_at: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace a task. O(log n)."""
        with self._lock:
            if task_id in self._entry_finder:
                self.remove(task_id)
            # Negate priority so CRITICAL (4) sorts before LOW (1).
            # Sequence counter breaks remaining ties deterministically.
            sort_key = (-priority, created_at, next(self._counter))
            entry = QueueEntry(
                sort_key=sort_key,
                task_id=task_id,
                priority=priority,
                created_at=created_at,
                scheduled_at=scheduled_at,
                payload=payload,
            )
            self._entry_finder[task_id] = entry
            heapq.heappush(self._heap, entry)
            self._valid_count += 1

    def pop(self) -> QueueEntry | None:
        """Remove and return the highest-priority ready task. O(log n)."""
        with self._lock:
            while self._heap:
                entry = heapq.heappop(self._heap)
                current = self._entry_finder.get(entry.task_id)
                if current is entry:
                    del self._entry_finder[entry.task_id]
                    self._valid_count -= 1
                    return entry
            return None

    def peek(self) -> QueueEntry | None:
        """Return the next task without removing it. O(1) amortized."""
        with self._lock:
            self._prune_invalid()
            return self._heap[0] if self._heap else None

    def remove(self, task_id: int) -> bool:
        """Invalidate a queued task. O(1). Actual heap cleanup is lazy."""
        with self._lock:
            entry = self._entry_finder.pop(task_id, None)
            if entry is None:
                return False
            self._valid_count -= 1
            return True

    def contains(self, task_id: int) -> bool:
        with self._lock:
            return task_id in self._entry_finder

    def size(self) -> int:
        with self._lock:
            return self._valid_count

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        with self._lock:
            self._heap.clear()
            self._entry_finder.clear()
            self._valid_count = 0

    def _prune_invalid(self) -> None:
        while self._heap:
            entry = self._heap[0]
            if self._entry_finder.get(entry.task_id) is entry:
                return
            heapq.heappop(self._heap)
