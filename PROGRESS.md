# Merge Progress

## Phase 1: DB/schema unification — DONE
- [x] map Transcriptor schema — see gap-analysis.md §1
- [x] map LegatoFlow schema — see gap-analysis.md §2
- [x] gap analysis doc — gap-analysis.md (schema-mapper subagent, read-only; persisted by main session since the agent has no Write tool)
- [x] adapter/bridge decided — see gap-analysis.md §6. 3 new nullable columns on `jobs` (`provider`, `external_job_id`, `transcription_status`); transcript stored as a `.txt` file in the job dir (zero schema change); polling metadata deferred to Phase 2. No new tables, existing triggers/constraints untouched.
- [x] implement the migration (Alembic revision + models.py) — commit `2915bd4` in transcriptor. `models.py`: 3 new nullable Job columns. `database.py`: idempotent `_backfill_job_columns()` so existing on-disk DBs get upgraded too (create_all() alone doesn't alter existing tables). Alembic revision `89e25a4bf754` added for parity with the existing (unwired — not a declared dependency, app never invokes it) migration history; unexecuted/unverified since alembic isn't installed in this env, same caveat as the pre-existing revisions.
- [x] migrate transcriptor test suite, confirm green — 4 new tests with the migration itself (2 model, 2 database-backfill); found and fixed a real fixture break (below); full suite green 279→284.
- [x] migrate legatoflow test suite, confirm green — unaffected (schema change is Transcriptor-only, no cross-repo coupling yet — that's Phase 2). Re-ran to confirm: 4/4 still passed.
- [x] note any fixture breaks + fixes — one real break found: `api.get_jobs()` now returns the 3 new columns as dict keys, and `TranscriptorView`'s horizontal table mode displays every dict key not on its exclusion list. `show jobs`/`show clients`/`show rates`/`invoice` table output would have grown 3 new blank columns on every existing job — a real "no functional rewrites" violation from an otherwise-additive schema change. Fixed by adding the 3 columns to the same exclusion list `job_path`/`client`/`rate`/`client_email` already use — commit `2a7790d`. Swept tui.py for the same pattern (blind key iteration): all job-dict `__dict__` usages there feed fixed named-field reads (JobEditScreen etc.), not display loops, so nothing else needed changing.

## Phase 2: job pipeline wiring
...

## Phase X: Transcriptor raw-SQL hardening (from IMPROVEMENTS.md, approved but large) — DONE
- [x] decide: `-r/--raw` CLI flag accepted as-is (user-confirmed), restricting it is out of scope (functional change)
- [x] fix `base.py` unescaped `client_id`/`job_numbers` interpolation in `get_invoice_jobs`/`get_jobs_by_job_numbers` — commit `f8e7644`
- [x] confirm test suite green after change — 272→276 passed

## Phase X: Transcriptor tui.py silent-exception cleanup (from IMPROVEMENTS.md, approved but large) — DONE
- [x] audit all `except` sites in tui.py (34 total) — 9 were genuinely silent, rest already notify/surface or are deliberate fallback defaults
- [x] added module logger + `logger.debug(..., exc_info=True)` at each silent site — one sweep commit (mechanical, no control-flow change) — commit `da37c26`
- [x] confirm test suite green after change — 276 passed (no dedicated tui.py tests exist; verified by import + full-suite regression)

## New: Transcriptor tui.py mv_extract_job_file path-traversal gap (found during exception audit) — DONE
- [x] `AddJobScreen.mv_extract_job_file` in tui.py is a separate, un-deduplicated copy of `Transcriptor.mv_extract_job_file` (base.py) and had the unguarded `zf.extractall(job_dir)` the base.py fix (36d6ab8) didn't reach
- [x] applied the same zip-member path-traversal guard — commit `b83515a`
- [x] confirm test suite green after change — 276→279 passed; new tests/test_tui.py confirmed the gap was real against pre-fix code

## Log
- 2026-09-17: phase1 started, schema mapping in progress
- 2026-09-17: improvement-scout run on both repos, IMPROVEMENTS.md created
- 2026-09-17: all IMPROVEMENTS.md items approved; small items implemented inline (see IMPROVEMENTS.md for commit hashes); 2 large Transcriptor items deferred to Phase X above; scripts/old-scripts bundle kept per user decision
- 2026-09-17: fixed LegatoFlow requires-python/notebooklm-py conflict (commit a895b44) — uv now resolves/syncs, pytest runs for real (4/4 passed), all prior LegatoFlow fixes re-verified against a working env instead of py_compile-only
- 2026-09-17: Phase X raw-SQL hardening done (commit f8e7644) — user confirmed -r/--raw stays as-is (accepted risk, single-user local CLI); fixed base.py's own unescaped client_id/job_numbers interpolation instead.
- 2026-09-17: Phase X tui.py silent-exception cleanup done (commit da37c26) — 9 sites fixed with debug logging, mechanical/behavior-preserving. Found a new gap during the audit (tui.py's own mv_extract_job_file copy still has the zip path-traversal issue, not covered by the earlier base.py fix) — logged in IMPROVEMENTS.md.
- 2026-09-18: fixed tui.py's AddJobScreen.mv_extract_job_file path-traversal gap (commit b83515a), new tests/test_tui.py confirms the gap was real (evil.txt extracted outside target dir on pre-fix code). Full suite 276→279 passed. All IMPROVEMENTS.md items now done or explicitly declined — none left pending.
- 2026-09-18: ran schema-mapper subagent on both repos, wrote gap-analysis.md. Key findings: Transcriptor's jobs.status is a DB-trigger-coupled binary (Pending/Done) tied to date_submitted; LegatoFlow has no DB, just a 50-entry-capped flat JSON job list with raw provider status strings (not normalized except for NotebookLM) and no client/billing concepts at all. NotebookLM's "transcript" is actually an LLM chat answer about the audio, not real ASR — flagged as possibly a product-level concern, not just schema. 7 items flagged as requiring genuinely new columns (provider, external job id, fine-grained status, transcript storage, NotebookLM-specific fields, separate upload-path, polling metadata) — no bridge/schema decision made yet, that's the next step.
- 2026-09-18: reviewed gap-analysis.md, found 2 gaps (job_number/date_due missing from §4's bridge plan; 50-job-cap operational risk not called out) — both added, user confirmed.
- 2026-09-18: bridge/adapter decision made (user-confirmed, gap-analysis.md §6): 3 new nullable columns on jobs (provider, external_job_id, transcription_status), transcript as a file in the job dir (no schema change), polling metadata deferred to Phase 2. No new tables, existing Pending/Done triggers untouched. Migration itself not yet implemented — that's next.
- 2026-09-18: implemented the migration (commit 2915bd4): models.py gets the 3 columns; database.py gets an idempotent backfill step since create_all() doesn't alter existing tables (matters for real on-disk transcriptor.db files predating this change); Alembic revision 89e25a4bf754 added for documentation parity with the existing but unwired alembic setup. TDD followed: 4 new tests written first (confirmed failing), then implementation, confirmed passing. Full suite 279→283 green.
- 2026-09-18: closed out Phase 1. Found the one real fixture break from the schema change: new columns leaked into show jobs/clients/rates/invoice CLI table output as blank columns (view.py's horizontal mode displays all dict keys not on an exclusion list). Fixed with a TDD test-first pass (confirmed failing, then fixed) — commit 2a7790d, full suite 283→284. Swept tui.py for the same blind-key-iteration pattern; nothing else affected (all its __dict__ usages feed fixed named-field reads, not display loops). LegatoFlow suite re-confirmed green (4/4), unaffected since it has no coupling to Transcriptor's DB yet. Phase 1 complete — Phase 2 (job pipeline wiring) is next.
