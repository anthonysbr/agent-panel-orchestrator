#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const pythonRoot = path.resolve(__dirname, "..", "python");
const userArgs = process.argv.slice(2);

if (!fs.existsSync(path.join(pythonRoot, "panel_core", "cli.py"))) {
  console.error("panel: error: bundled Python package is missing. Reinstall agent-panel-orchestrator.");
  process.exit(1);
}

const candidates =
  process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"];

function buildArgs(exe) {
  if (process.platform === "win32" && exe === "py") {
    return ["-3", "-m", "panel_core.cli", ...userArgs];
  }
  return ["-m", "panel_core.cli", ...userArgs];
}

for (const exe of candidates) {
  const result = spawnSync(exe, buildArgs(exe), {
    stdio: "inherit",
    env: {
      ...process.env,
      PYTHONPATH: pythonRoot,
    },
  });

  if (result.error) {
    if (result.error.code === "ENOENT") {
      continue;
    }
    console.error(`panel: error: ${result.error.message}`);
    process.exit(1);
  }

  process.exit(result.status ?? 1);
}

console.error("panel: error: Python 3.10+ is required. Install from https://www.python.org/downloads/ or run: pipx install agent-panel-orchestrator");
process.exit(1);
