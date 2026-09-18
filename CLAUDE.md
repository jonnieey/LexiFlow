# Merge project: Transcriptor + LegatoFlow → unified-app

## Hard constraints
- NO functional rewrites. Port + wire, don't reimagine.
- Reuse existing DB schema/file. Do not create new tables unless bridging two schemas requires it — flag before doing so.
- Reuse existing directory structure/conventions from Transcriptor for job storage.
- Every change = one git commit, one concern (schema / wiring / cleanup — not mixed).
- TDD: write failing test → confirm fail → implement → confirm pass → commit. No implementation before a test exists, no exceptions.
- Responses: terse. Skip preamble/summary fluff. Bullet over prose.

## Source repos (reference only, read-only mentally)
- Transcriptor: ~/.IT/python/projects/transcriptor — job CRUD, dir/file mgmt, status
- LegatoFlow: ~/.IT/python/projects/legatoflow — transcription via external services

## Progress tracking
See PROGRESS.md. Update it after every commit, not before.

## Improvements
Suggestions only, never auto-implemented. Logged in IMPROVEMENTS.md.
Each item: ask before implementing. If approved and small → do inline as its own commit (not mixed with merge commits). If approved and large → new PROGRESS.md task, own phase if needed.
If declined → mark "declined" in IMPROVEMENTS.md, don't re-raise.
