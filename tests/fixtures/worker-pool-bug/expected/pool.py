"""Worker pool with counting bug fixed."""

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
        return total, processed
