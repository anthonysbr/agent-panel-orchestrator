# Audit Loop

Do not stop at the first plausible fix or review pass.

## Builder

Implement the requested change, run relevant checks, and leave the tree verifiable. If tests exist for the touched area, run them.

## Auditor

Search changed and related code for bugs, race conditions, missing error handling, weak tests, and regressions. Cite paths and severity. Keep looking until you can defend a clean bill of health with evidence.

## Stop condition

Only declare the work clean when deterministic gates pass and no material issue remains. In audit-loop judge runs, emit `<promise>CLEAN</promise>` only when that is genuinely true.
