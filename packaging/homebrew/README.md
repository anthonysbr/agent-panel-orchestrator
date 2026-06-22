# Homebrew tap

```bash
brew tap anthonysbr/agent-panel https://github.com/anthonysbr/homebrew-agent-panel
brew install agent-panel-orchestrator
```

Copy `packaging/homebrew/agent-panel-orchestrator.rb` into the tap repo as `Formula/agent-panel-orchestrator.rb`.

Local test:

```bash
brew install --build-from-source ./packaging/homebrew/agent-panel-orchestrator.rb
```

Before a release, update `url`, tag, and `sha256` in `agent-panel-orchestrator.rb`. See [`../RELEASE.md`](../RELEASE.md).
