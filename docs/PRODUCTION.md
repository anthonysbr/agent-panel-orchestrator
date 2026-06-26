# Production readiness checklist (v0.4.0)

Use this checklist before tagging a production release.

## CI tier 1+2 (required)

- [ ] `python3 -m unittest discover tests -v` passes
- [ ] `./scripts/verify_fixtures.sh` passes
- [ ] `panel skills eval --all` passes
- [ ] npm smoke (Linux + Windows) passes
- [ ] `./scripts/check_version_sync.sh` passes

## Live QA tier 3 (required before v0.4.0)

Run manually or via `.github/workflows/live-qa.yml`:

```bash
cd tests/fixtures/worker-pool-bug
panel run --yes --audit-loop --ci --workspace project \
  --builder auto --panel auto --judge auto \
  --max-rounds 3 -- "fix the worker pool counting bug"
echo $?  # expect 0
```

- [ ] At least one fixture reaches `stopped_reason: clean` with a real provider
- [ ] `panel run --workspace project --yes --panel auto --judge auto -- "review this codebase"` produces artifacts on `api-monolith`
- [ ] `panel doctor` reports available providers and gates hint

## Release ops

- [ ] `NPM_TOKEN` set in GitHub `release` environment
- [ ] Tag triggers GitHub release + npm publish (idempotent skip OK)
- [ ] PyPI job skipped unless `ENABLE_PYPI=true` repo variable
- [ ] Homebrew formula version matches tag

## Exit codes (`panel run --ci`)

| Code | Meaning |
|------|---------|
| 0 | Success, clean audit-loop, or dry-run |
| 1 | Audit-loop ended at max-rounds without CLEAN |
| 2 | Hard failure (missing provider, config error) |
| 130 | User cancelled confirmation prompt |
