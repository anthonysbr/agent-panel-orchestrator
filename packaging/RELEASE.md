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

Jobs: build artifacts → GitHub Release → PyPI (optional) → npm (optional).

### npm (manual if CI token cannot publish)

If your npm account requires publish OTP, CI may fail with 403 even when `NPM_TOKEN` is set. Publish locally, then re-run the failed **publish-npm** job (or push the tag again):

```bash
cd npm
node scripts/prepack.js
npm publish --access public --otp=YOUR_6_DIGIT_CODE
npm view agent-panel-orchestrator version
```

CI skips publish when that version already exists on npm. The **publish-npm** job uses `continue-on-error` so a token/2FA mismatch does not fail the whole release workflow.

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
