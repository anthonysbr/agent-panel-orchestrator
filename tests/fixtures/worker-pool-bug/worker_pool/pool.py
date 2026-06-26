"""Worker pool with a counting bug."""

from __future__ import annotations

from typing import Iterable, Tuple


class WorkerPool:
    def __init__(self, workers: int = 2) -> None:
        self.workers = workers

    def process(self, items: Iterable[int]) -> Tuple[int, int]:
        total = 0
        processed = 0
        for item in items:
            total += item
            processed += 1
        # Bug: returns processed+1 instead of processed when items non-empty
        return total, processed + (1 if processed else 0)
