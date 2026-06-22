# Code Review Skill

Use this skill for reviewing code changes, pull requests, diffs, refactors, and implementation plans.

Review in this order:
1. Correctness, edge cases, data loss, race conditions, and failure modes.
2. Security-sensitive behavior: trust boundaries, input validation, auth checks, secrets, and unsafe shell or network calls.
3. Tests: missing coverage, brittle assertions, fixture gaps, and unverified behavior.
4. Maintainability: unnecessary abstraction, duplicated logic, naming, ownership boundaries, and reuse of existing helpers.
5. Performance: avoidable repeated work, N+1 queries, memory growth, blocking I/O, and slow paths.

Output findings first, ordered by severity. Use file and line references when available. Keep summaries short and separate from findings. Do not nitpick formatting that automated tools should handle.

Severity:
- Blocking: likely bug, security risk, data loss, broken build, or missing required behavior.
- Important: meaningful maintainability, test, performance, or reliability risk.
- Suggestion: optional improvement that should not block.
