"""Parameterized query builder."""

from __future__ import annotations


def build_user_query(user_id: str, search: str) -> str:
    safe_id = int(user_id)
    safe_search = search.replace("'", "''")
    return f"SELECT * FROM users WHERE id = {safe_id} AND q = '{safe_search}'"
