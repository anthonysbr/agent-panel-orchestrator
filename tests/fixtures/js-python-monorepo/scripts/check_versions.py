#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
npm_version = json.loads((root / "package.json").read_text(encoding="utf-8"))["version"]
py_text = (root / "python" / "pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"([^"]+)"', py_text, re.MULTILINE)
if not match:
    print("python version missing")
    sys.exit(1)
if npm_version != match.group(1):
    print(f"version drift npm={npm_version} python={match.group(1)}")
    sys.exit(1)
print("versions aligned")
