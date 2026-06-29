#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== unit tests =="
python3 -m unittest discover tests -v

echo "== fixture gate checks =="
python3 -m unittest tests.integration.test_fixture_audit_loop.FixtureGateTests -v

echo "== fixture audit-loop integration =="
python3 -m unittest tests.integration.test_fixture_audit_loop.WorkerPoolAuditLoopIntegrationTests -v

echo "== integration user journeys =="
python3 -m unittest tests.integration.test_user_journeys -v

echo "== fixture dry-run smoke =="
FIXTURES_DIR="$ROOT/tests/fixtures"
RUNS_DIR="$(mktemp -d)"
trap 'rm -rf "$RUNS_DIR"' EXIT

for fixture in worker-pool-bug api-monolith js-python-monorepo; do
  echo "-- $fixture --"
  (
    cd "$FIXTURES_DIR/$fixture"
    python3 "$ROOT/panel" run --audit-loop --dry-run --yes \
      --runs-dir "$RUNS_DIR/$fixture" \
      --builder codex --panel codex --judge codex \
      --max-rounds 1 -- "fix the known issue in this fixture"
  )
done

echo "All fixture verification passed."
