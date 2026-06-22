from __future__ import annotations

import difflib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .paths import PROJECT_ROOT


BUILTIN_SKILLS_DIR = PROJECT_ROOT / "skills"
PROJECT_PANEL_DIR = ".panel"
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class Skill:
    skill_id: str
    name: str
    version: str
    description: str
    triggers: List[str]
    path: Path
    source: str

    @property
    def instructions_path(self) -> Path:
        return self.path / "instructions.md"

    def read_instructions(self) -> str:
        return self.instructions_path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class EvalResult:
    skill_id: str
    cases: int
    passed: int
    score: float
    failures: List[str]


def validate_skill_id(skill_id: str) -> None:
    if not SKILL_ID_RE.match(skill_id):
        raise ValueError("skill id must use lowercase letters, digits, and hyphens")


class SkillRegistry:
    def __init__(self, project_root: Optional[Path] = None, builtin_root: Path = BUILTIN_SKILLS_DIR) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.builtin_root = builtin_root

    @property
    def project_skills_root(self) -> Path:
        return self.project_root / PROJECT_PANEL_DIR / "skills"

    @property
    def proposals_root(self) -> Path:
        return self.project_root / PROJECT_PANEL_DIR / "skill_proposals"

    def list_skills(self) -> List[Skill]:
        skills = self._load_from_root(self.builtin_root, "built-in")
        skills.update(self._load_from_root(self.project_skills_root, "project"))
        return [skills[key] for key in sorted(skills)]

    def get_skill(self, skill_id: str) -> Skill:
        validate_skill_id(skill_id)
        for skill in self.list_skills():
            if skill.skill_id == skill_id:
                return skill
        raise ValueError(f"unknown skill {skill_id!r}; run `panel skills list`")

    def resolve(self, spec: str, task: str) -> List[Skill]:
        clean = (spec or "auto").strip()
        if clean == "none":
            return []
        if clean == "auto":
            return self.auto_select(task)

        skills: List[Skill] = []
        seen = set()
        for item in clean.split(","):
            skill_id = item.strip()
            if not skill_id:
                continue
            skill = self.get_skill(skill_id)
            if skill.skill_id not in seen:
                skills.append(skill)
                seen.add(skill.skill_id)
        if not skills:
            raise ValueError("skills spec did not name any skills")
        return skills

    def auto_select(self, task: str) -> List[Skill]:
        haystack = task.lower()
        scored = []
        for skill in self.list_skills():
            score = 0
            for trigger in skill.triggers:
                needle = trigger.lower()
                if needle and needle in haystack:
                    score += max(1, len(needle.split()))
            if score:
                scored.append((score, skill.name, skill))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored[:3]]

    def create_project_skill(self, skill_id: str, target: Path) -> Path:
        validate_skill_id(skill_id)
        root = target.resolve() / PROJECT_PANEL_DIR / "skills" / skill_id
        if root.exists():
            raise FileExistsError(f"skill already exists: {root}")
        (root / "evals").mkdir(parents=True)
        title = skill_id.replace("-", " ").title()
        metadata = {
            "id": skill_id,
            "name": title,
            "version": "0.1.0",
            "description": f"Project skill for {title}.",
            "triggers": [skill_id.replace("-", " ")],
        }
        (root / "skill.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        (root / "instructions.md").write_text(f"# {title}\n\n", encoding="utf-8")
        (root / "evals" / "basic.jsonl").write_text(
            json.dumps(
                {
                    "id": f"{skill_id}-basic",
                    "task": f"Use the {title} skill.",
                    "must_include": [skill_id.split("-")[0]],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return root

    def _load_from_root(self, root: Path, source: str) -> Dict[str, Skill]:
        if not root.exists():
            return {}
        loaded: Dict[str, Skill] = {}
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            meta_path = child / "skill.json"
            instructions_path = child / "instructions.md"
            if not meta_path.exists() or not instructions_path.exists():
                continue
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping):
                raise ValueError(f"skill metadata must be an object: {meta_path}")
            skill_id = str(raw["id"])
            validate_skill_id(skill_id)
            triggers = raw.get("triggers", [])
            if not isinstance(triggers, list) or not all(isinstance(item, str) for item in triggers):
                raise ValueError(f"skill triggers must be a list of strings: {meta_path}")
            loaded[skill_id] = Skill(
                skill_id=skill_id,
                name=str(raw.get("name", skill_id)),
                version=str(raw.get("version", "0.0.0")),
                description=str(raw.get("description", "")),
                triggers=list(triggers),
                path=child,
                source=source,
            )
        return loaded


def render_skill_context(skills: Sequence[Skill]) -> str:
    if not skills:
        return ""
    blocks = []
    for skill in skills:
        blocks.append(
            "\n".join(
                [
                    f"## {skill.name} ({skill.skill_id})",
                    skill.read_instructions().strip(),
                ]
            )
        )
    return "\n\n".join(blocks).strip()


def evaluate_skill(skill: Skill, instructions: Optional[str] = None) -> EvalResult:
    text = (instructions if instructions is not None else skill.read_instructions()).lower()
    cases = list(_iter_eval_cases(skill.path / "evals"))
    failures: List[str] = []
    passed = 0
    for case in cases:
        case_id = str(case.get("id", "unnamed"))
        required = case.get("must_include", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            failures.append(f"{case_id}: invalid must_include")
            continue
        missing = [item for item in required if item.lower() not in text]
        if missing:
            failures.append(f"{case_id}: missing {', '.join(missing)}")
            continue
        passed += 1
    score = (passed / len(cases)) if cases else 0.0
    return EvalResult(skill_id=skill.skill_id, cases=len(cases), passed=passed, score=score, failures=failures)


def improve_skill(
    registry: SkillRegistry,
    skill_id: str,
    runs_dir: Path,
    dry_run: bool,
) -> Path:
    skill = registry.get_skill(skill_id)
    current = skill.read_instructions()
    lessons = _extract_lessons(runs_dir)
    proposed = _apply_lessons(current, lessons)
    current_eval = evaluate_skill(skill, current)
    proposed_eval = evaluate_skill(skill, proposed)
    changed = proposed != current
    if not changed:
        status = "untested"
        reason = "No new run lessons were found."
    elif proposed_eval.cases == 0:
        status = "untested"
        reason = "No eval cases are available for this skill."
    elif proposed_eval.score >= current_eval.score:
        status = "validated"
        reason = "Proposal passed the validation gate."
    else:
        status = "regressed"
        reason = "Proposal lowered the validation score."

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    proposal_dir = registry.proposals_root / skill.skill_id / timestamp
    counter = 1
    while proposal_dir.exists():
        counter += 1
        proposal_dir = registry.proposals_root / skill.skill_id / f"{timestamp}-{counter}"
    diff = "\n".join(
        difflib.unified_diff(
            current.splitlines(),
            proposed.splitlines(),
            fromfile="current",
            tofile="proposed",
            lineterm="",
        )
    )
    metadata = {
        "id": f"{skill.skill_id}/{proposal_dir.name}",
        "skill_id": skill.skill_id,
        "status": status,
        "reason": reason,
        "dry_run": dry_run,
        "created_at": timestamp,
        "runs_dir": str(runs_dir),
        "run_sources": [str(path) for path in _iter_run_dirs(runs_dir)],
        "current_score": current_eval.score,
        "candidate_score": proposed_eval.score,
        "cases": proposed_eval.cases,
        "failures": proposed_eval.failures,
    }
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (proposal_dir / "current.md").write_text(current, encoding="utf-8")
    (proposal_dir / "proposed.md").write_text(proposed, encoding="utf-8")
    (proposal_dir / "diff.md").write_text(diff + ("\n" if diff else ""), encoding="utf-8")
    return proposal_dir


def adopt_proposal(registry: SkillRegistry, proposal_id: str) -> Path:
    proposal_dir = _resolve_proposal(registry, proposal_id)
    metadata = _read_proposal_metadata(proposal_dir)
    if metadata.get("status") != "validated":
        raise ValueError("only validated proposals can be adopted")
    skill_id = str(metadata["skill_id"])
    skill = registry.get_skill(skill_id)
    target = registry.project_skills_root / skill_id
    target.mkdir(parents=True, exist_ok=True)
    source_meta = skill.path / "skill.json"
    target_meta = target / "skill.json"
    if not target_meta.exists():
        shutil.copyfile(source_meta, target_meta)
    proposed = (proposal_dir / "proposed.md").read_text(encoding="utf-8")
    (target / "instructions.md").write_text(proposed, encoding="utf-8")
    (target / "evals").mkdir(exist_ok=True)
    if not any((target / "evals").iterdir()):
        source_evals = skill.path / "evals"
        if source_evals.exists():
            for item in source_evals.iterdir():
                if item.is_file():
                    shutil.copyfile(item, target / "evals" / item.name)
    metadata["adopted_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (proposal_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return target


def reject_proposal(registry: SkillRegistry, proposal_id: str) -> Path:
    proposal_dir = _resolve_proposal(registry, proposal_id)
    metadata = _read_proposal_metadata(proposal_dir)
    metadata["status"] = "rejected"
    metadata["rejected_at"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (proposal_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return proposal_dir


def _iter_eval_cases(evals_dir: Path) -> Iterable[Mapping[str, object]]:
    if not evals_dir.exists():
        return []
    cases: List[Mapping[str, object]] = []
    for path in sorted(evals_dir.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, Mapping):
                raise ValueError(f"eval case must be an object: {path}:{line_number}")
            cases.append(raw)
    return cases


def _iter_run_dirs(runs_dir: Path) -> List[Path]:
    if not runs_dir.exists():
        return []
    return [path for path in sorted(runs_dir.iterdir()) if path.is_dir()]


def _extract_lessons(runs_dir: Path) -> List[str]:
    lessons: List[str] = []
    ignored = {
        "No new repeated failure pattern was detected.",
        "Run the same task without `--dry-run` when provider evidence is needed.",
    }
    for run_dir in _iter_run_dirs(runs_dir):
        learning = run_dir / "learning.md"
        if not learning.exists():
            continue
        lines = learning.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "## Guardrail Recommendation" and index + 1 < len(lines):
                lesson = lines[index + 1].strip().lstrip("- ").strip()
                if lesson and lesson not in ignored and lesson not in lessons:
                    lessons.append(lesson)
    return lessons


def _apply_lessons(current: str, lessons: Sequence[str]) -> str:
    if not lessons:
        return current
    body = current.rstrip()
    existing = body.lower()
    new_lines = [lesson for lesson in lessons if lesson.lower() not in existing]
    if not new_lines:
        return current
    learned = "\n".join(f"- {line}" for line in new_lines)
    return body + "\n\n## Run-Learned Guidance\n\n" + learned + "\n"


def _resolve_proposal(registry: SkillRegistry, proposal_id: str) -> Path:
    raw_path = Path(proposal_id)
    if raw_path.exists():
        return raw_path.resolve()
    candidate = registry.proposals_root / proposal_id
    if candidate.exists():
        return candidate
    matches = list(registry.proposals_root.glob(f"*/{proposal_id}"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous proposal id {proposal_id!r}; use skill/timestamp")
    raise FileNotFoundError(f"proposal not found: {proposal_id}")


def _read_proposal_metadata(proposal_dir: Path) -> Dict[str, object]:
    metadata_path = proposal_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"proposal metadata not found: {metadata_path}")
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"proposal metadata must be an object: {metadata_path}")
    return raw
