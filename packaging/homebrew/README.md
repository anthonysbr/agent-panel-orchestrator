# Homebrew tap

```bash
brew tap entkreis/agent-panel https://github.com/anthonysbr/homebrew-agent-panel
brew install agent-panel-orchestrator
```

Local test:

```bash
brew install --build-from-source ./packaging/homebrew/agent-panel-orchestrator.rb
```

Before a release, update `url`, tag, and `sha256` in `agent-panel-orchestrator.rb`.
