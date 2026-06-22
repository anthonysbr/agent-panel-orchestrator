# Agent Panel Orchestrator

[![npm version](https://img.shields.io/npm/v/agent-panel-orchestrator.svg)](https://www.npmjs.com/package/agent-panel-orchestrator)

CLI for running independent panelists on local agent CLIs, then synthesizing their answers through a judge pass.

Install via npm, pipx, Homebrew, or git clone. Same `panel` command; needs Python 3.10+.

Runtime adapters in provider prompts keep Codex, Claude Code, Cursor, and Gemini on their own identity and tools. Skill references live under `third_party/`.

## Commands

```bash
./panel doctor
./panel detect
./panel detect --json
./panel prompt --agent codex --task "test"
./panel run --dry-run --skills auto --panel codex:2 --judge codex -- "test"
./panel run --yes --skills auto --panel auto --judge auto -- "your hard question"
./panel run --audit-loop --dry-run --builder codex --panel codex:2 --judge claude --max-rounds 3 -- "fix race in worker pool"
./panel runs list
./panel runs show 20260616T120000Z
./panel skills list
./panel skills diff design/20260615T120000Z
./panel export-rules --target /path/to/project
```

Live runs ask for confirmation unless you pass `--yes`. Use `--max-panelists`, `--retries`, `--audit-loop`, `--max-rounds`, and `--json` where you need control or scripting.

Set `PANEL_PROVIDER_EMPTY_RETRIES=1` (default) to transparently retry provider turns that return empty output.

## Related tools

| Tool | Use for |
|------|---------|
| [evolve-loop](https://github.com/mickeyyaya/evolve-loop) | Overnight autonomous Build→Audit→Ship cycles with deterministic gates (Claude Code, Codex CLI, Gemini CLI) |
| [UltraCode-Shim](https://github.com/OnlyTerp/UltraCode-Shim) | Optional: run Claude Code panelists through other models via a local proxy (`panel` does not manage this) |

- **Hard decisions / multi-model review** → `panel run`
- **Implement until merge-safe** → evolve-loop, or `panel run --audit-loop` in this repo
- **Claude Code + cheaper worker models** → configure UltraCode-Shim separately

See [`packaging/RELEASE.md`](packaging/RELEASE.md) for tagging and PyPI/npm publish.

## Install

| Method | Command | Best for |
|--------|---------|----------|
| npm | `npm install -g agent-panel-orchestrator` | Web/mobile projects, monorepos, teams on Node.js |
| pipx | `pipx install agent-panel-orchestrator` | Python-first workflows on macOS, Linux, or Windows |
| Homebrew | `brew tap anthonysbr/agent-panel` then `brew install agent-panel-orchestrator` (tap pending) | macOS and Linux terminal setups |
| Windows zip | Download from [GitHub Releases](https://github.com/anthonysbr/agent-panel-orchestrator/releases) or run `packaging/windows/install.ps1` | Windows without a preferred package manager |
| Git clone | `./install.sh` | Contributors and active development of this repo |

Requirements: Python 3.10+ and at least one provider CLI (`codex`, `claude`, `agent`, or `gemini`).

### Git clone (development)

```bash
./install.sh --dry-run
./install.sh
```

By default this symlinks `~/.local/bin/panel` to this repo's `panel` script.

### npm (JS ecosystem)

```bash
npm install -g agent-panel-orchestrator
panel doctor
```

Project-local install:

```bash
npm install -D agent-panel-orchestrator
npx panel run --skills auto --panel auto --judge auto -- "your task"
```

### pipx / pip

```bash
pipx install agent-panel-orchestrator
panel doctor
```

### Homebrew

```bash
# brew tap anthonysbr/agent-panel  # coming soon
# brew install agent-panel-orchestrator
pipx install agent-panel-orchestrator
```

See [`packaging/homebrew/README.md`](packaging/homebrew/README.md).

### Windows

```powershell
npm install -g agent-panel-orchestrator
# or
pipx install agent-panel-orchestrator
# or
irm https://raw.githubusercontent.com/anthonysbr/agent-panel-orchestrator/main/packaging/windows/install.ps1 | iex
```

Winget manifest: [`packaging/winget/`](packaging/winget/).

## Audit loop

`--audit-loop` runs **builder → deterministic gates → audit panel → judge** until gates pass, the judge emits `<promise>CLEAN</promise>`, or `--max-rounds` is reached.

```bash
cp .panel/gates.yaml.example .panel/gates.yaml
panel run --audit-loop --dry-run --builder auto --panel auto --judge auto -- "implement feature X"
panel run --yes --audit-loop --max-rounds 5 -- "fix flaky tests and race conditions"
```

Each round writes under `runs/<timestamp>/rounds/NN/` (`builder.*`, `gates.json`, audit prompts, judge output). Default gates run `compileall` and `unittest` when `.panel/gates.yaml` is missing.

## Quick example

Dry-run (no provider calls):

```bash
panel run --dry-run --panel codex:2 --judge codex -- "review this API design"
panel runs list
```

Typical output tree:

```text
runs/20260616T120000Z/
  run_plan.json
  task_graph.json
  task.md
  panelists/
  verification.md
  decision.md
  learning.md
```

## Providers

Provider subprocess adapters live in `config/agents.json`.

- `codex`: runs `codex exec` in a scratch directory and captures the final answer with `-o`.
- `claude`: runs `claude -p --output-format text --no-session-persistence`.
- `cursor`: runs `agent -p --output-format text`.

`panel detect` checks Codex, Claude Code, Cursor, and Gemini as first-class providers.

## Skills

Built-in skills live in `skills/`:

- `design`
- `code-review`
- `security`
- `research`
- `audit-loop`

Use `--skills auto` to select skills from the task text, `--skills none` to disable them, or pass an explicit list:

```bash
panel run --skills design,security --panel auto --judge auto -- "review this app"
```

Project-specific skills go in `.panel/skills/` and override built-in skills with the same id.

```bash
panel skills create brand --target /path/to/project
```

Improvements are staged under `.panel/skill_proposals/` and only land after validation:

```bash
panel skills eval design
panel skills eval --all
panel skills improve design --from-runs runs --dry-run
panel skills diff design/20260615T120000Z
panel skills adopt design/20260615T120000Z
panel skills reject design/20260615T120000Z
```

## Run Artifacts

Each run writes to `runs/<timestamp>/` in the current working directory:

- `run_plan.json`
- `task_graph.json`
- `task.md`
- `panelists/*.prompt.md`
- `panelists/*.output.md` for live runs
- `logs/*.log`
- `judge.prompt.md`
- `final.md`
- `verification.md`
- `decision.md`
- `learning.md`

`runs/` is gitignored local output.

## Tests

```bash
python3 -m compileall panel_core tests
python3 -m unittest discover tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome; bugs → issue with the command you ran.

Email: [hallo@entkreis.de](mailto:hallo@entkreis.de) (Anthony Batista).
