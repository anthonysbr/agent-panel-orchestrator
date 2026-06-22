# Release checklist

## One-time GitHub setup

1. Create environment **`release`** at  
   `https://github.com/anthonysbr/agent-panel-orchestrator/settings/environments`
2. Add secrets:
   - `PYPI_TOKEN` — PyPI API token with upload scope
   - `NPM_TOKEN` — npm automation token for `agent-panel-orchestrator`

The workflow in [`.github/workflows/release.yml`](../.github/workflows/release.yml) runs on tags `v*`.

## Publish a version

```bash
./scripts/check_version_sync.sh
git checkout main && git pull
git tag v0.3.0
git push origin v0.3.0
```

Jobs: build artifacts → GitHub Release → PyPI → npm (npm publish is idempotent if the version already exists).

## Homebrew tap

After the tag exists:

```bash
VERSION=0.3.0
curl -L "https://github.com/anthonysbr/agent-panel-orchestrator/archive/refs/tags/v${VERSION}.tar.gz" | shasum -a 256
```

Update [`packaging/homebrew/agent-panel-orchestrator.rb`](homebrew/agent-panel-orchestrator.rb) with `url`, tag, and `sha256`, then push to the tap repo:

```bash
brew tap anthonysbr/agent-panel
brew install agent-panel-orchestrator
```

See [`packaging/homebrew/README.md`](homebrew/README.md).
