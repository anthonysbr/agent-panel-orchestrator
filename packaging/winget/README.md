# winget

Install on Windows:

1. `npm install -g agent-panel-orchestrator`
2. `pipx install agent-panel-orchestrator`
3. `irm https://raw.githubusercontent.com/anthonysbr/agent-panel-orchestrator/main/packaging/windows/install.ps1 | iex`

To submit to [winget-pkgs](https://github.com/microsoft/winget-pkgs): attach the release zip from `scripts/release.sh`, update `InstallerSha256` in `Entkreis.AgentPanelOrchestrator.yaml`, open a PR.
