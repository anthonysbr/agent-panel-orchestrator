import unittest

from worker_pool.pool import WorkerPool


class WorkerPoolTests(unittest.TestCase):
    def test_process_count(self) -> None:
        pool = WorkerPool()
        total, count = pool.process([1, 2, 3])
        self.assertEqual(total, 6)
        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
