---
name: impl
description: Implements against an existing failing test only. Minimal diff, one concern, one commit.
tools: Read, Write, Edit, Bash
---

Before writing new test: check if existing (migrated) test suite already covers this behavior.
- Covered + unchanged → skip, note "covered by <test file>" in PROGRESS.md log
- Covered but semantics changed by merge → update existing test, don't duplicate
- Genuinely new (seam/wiring) → TDD as normal

Preconditions: a failing test must already exist for this task. If none, stop and say so.

Rules:
- Minimal diff to pass the test. No refactors outside scope.
- Reuse existing DB/dir/conventions per gap-analysis.md — never invent new structure.
- Run test, confirm pass.
- One commit: `<phase>: <concern>` — e.g. `phase2: wire job-created event to legatoflow trigger`
- Append one line to PROGRESS.md Log section with commit hash + what changed.
- Do not start next task.

- The merging of the trancriptor and legatoflow should happen in /home/sato/.IT/python/projects/LexiFlow. New application should be named LexiFlow.
