#!/usr/bin/env python3
from pathlib import Path
import sys

text = Path("app/handlers.py").read_text(encoding="utf-8")
if "f\"SELECT * FROM users WHERE id = {user_id}" in text:
    print("raw SQL interpolation detected")
    sys.exit(1)
print("ok")
