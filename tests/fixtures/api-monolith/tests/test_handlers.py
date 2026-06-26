import unittest

from app.handlers import build_user_query


class HandlerTests(unittest.TestCase):
    def test_build_user_query(self) -> None:
        query = build_user_query("42", "alice")
        self.assertIn("42", query)
        self.assertIn("alice", query)


if __name__ == "__main__":
    unittest.main()
