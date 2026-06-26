"""HTTP-style handlers with intentional security debt."""

from __future__ import annotations


def build_user_query(user_id: str, search: str) -> str:
    # Bug: string interpolation allows SQL injection patterns in tests
    return f"SELECT * FROM users WHERE id = {user_id} AND q = '{search}'"
