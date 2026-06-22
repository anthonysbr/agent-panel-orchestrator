$ErrorActionPreference = "Stop"

function Test-Command($Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "Agent Panel Orchestrator installer for Windows"
Write-Host ""

if (Test-Command pipx) {
  Write-Host "Installing with pipx..."
  pipx install agent-panel-orchestrator --force
  Write-Host "Done. Run: panel detect"
  exit 0
}

if (Test-Command python) {
  Write-Host "Installing with pip..."
  python -m pip install --user --upgrade agent-panel-orchestrator
  Write-Host "Done. Ensure Python Scripts is on PATH, then run: panel detect"
  exit 0
}

if (Test-Command node) {
  Write-Host "Installing with npm..."
  npm install -g agent-panel-orchestrator
  Write-Host "Done. Run: panel detect"
  exit 0
}

Write-Error @"
No supported installer found.

Install one of:
  - Python 3.10+ (https://www.python.org/downloads/) then rerun this script
  - Node.js 18+ (https://nodejs.org/) for npm install -g agent-panel-orchestrator
  - pipx (https://pipx.pypa.io/) for pipx install agent-panel-orchestrator
"@
