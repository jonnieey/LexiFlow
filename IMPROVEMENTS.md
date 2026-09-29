# Improvements

Suggestions only. Not auto-implemented. Ask before implementing each item.
Status: pending | approved | declined | done

## Transcriptor

### Security
- [x] **done (partial, by design)** — SQL injection via app-built raw SQL. Decision (user-confirmed): the `-r/--raw` CLI flag itself (`api.py`'s `raw_sql_stmt` params, fed from unfiltered `args.raw` across `cli.py`) is an intentional, documented free-form-SQL escape hatch in a single-user local CLI tool — accepted as-is, restricting it would be a functional change and out of scope for this merge project. Fixed the genuine bug instead: `base.py:get_invoice_jobs`/`get_jobs_by_job_numbers` interpolated app-computed `client_id`/`job_numbers` into SQL with no validation/escaping. `client_id` now validated as `int` before interpolation (fails closed); `job_numbers` get single-quotes doubled per SQL string-literal escaping. Commit `f8e7644`. Confirmed against pre-fix code that an unescaped job number raised `sqlite3.OperationalError`; new tests fail on old code, pass on new. Full suite green (272→276 passed).
- [x] **done** — Unfiltered archive extraction. `backup.py` restore now uses `tarfile.extractall(..., filter="data")`; `base.py:mv_extract_job_file` validates zip members stay within the target dir before extracting. Commit `36d6ab8`. Tests added (`test_backup.py`, `test_base.py`), full suite green (268→272 passed).

### Bugs
- [x] **done** — `base.py` duplicate `load_cutoffs(year=year)` call removed. Commit `9678fa2`.
- [x] **done** — `tui.py:1396` bare `except:` narrowed to `except Exception:`. Commit `8889e09`.
- [x] **done** — `api.py` `update()`/`delete()` now `logger.error()` instead of `print()`; `update_clients/update_rates/update_jobs/delete_clients/delete_jobs` guard against a `False` statement before calling `session.execute()`. Commit `ac99b7e`. 4 new tests, full suite green (272 passed).
- [x] **done** — Widespread `except Exception: pass` in `tui.py`. Audited every `except` in the file (34 sites); 9 were genuinely silent (bare `pass`, no notify/logging): client-name lookup fallback, dashboard/jobs-table post-create refresh (x2), invoicing pane initial visibility, invoice-table cursor/focus/scroll (x2), markdown-preview focus/scroll (x3), cutoff date auto-fill. Added a module logger and `logger.debug(..., exc_info=True)` at each — no control-flow change, same fallback behavior, now traceable. Left alone: handlers that already `notify()`/surface the error, and deliberate value-coercion fallbacks (sort-key parsing, conversion-rate default) which aren't bugs. Commit `da37c26`. Full suite green (276 passed) — no dedicated tui.py test file exists, so this is a mechanical, behavior-preserving change verified by import + full-suite regression, not new unit tests.

### New finding (not on the original approved list)
- [x] **done** — `tui.py`'s `AddJobScreen.mv_extract_job_file` (a second, un-deduplicated copy of the method already fixed on `Transcriptor.mv_extract_job_file` in `base.py`, commit `36d6ab8`) had the same unguarded `zf.extractall(job_dir)` — same zip path-traversal gap, not covered by the earlier fix since it's a separate method on a separate class. Applied the same member-path validation. Commit `b83515a`. New `tests/test_tui.py` (3 tests) confirms the gap was real — reverted the fix and reran: a malicious zip with a `../evil.txt` member extracted outside the target dir on pre-fix code. Full suite green (276→279 passed).

### Stale artifacts
- [x] **done** — Empty `.null-ls_*.py` scratch files removed (were untracked, no commit needed).
- [x] **declined (keep)** — `scripts/old-scripts/` bundle is untracked (never committed) — deleting is irreversible with no git history to recover from, and it includes a binary `part1.mp3` fixture. User chose to keep for now; revisit if it causes confusion during the merge port.

## LegatoFlow

### Security
- [x] **done** — `cli.py` `config set` now masks secrets via shared `_mask_secret()` helper (same logic `config show` used). Commit `0fae4fe`. Tests added in new `tests/test_cli_config.py` (not executed here — see note below).
- [x] **done** — `services/notebook_lm.py` prompt dump moved from `print()` to `logger.debug()` (off by default), so case PII no longer prints unconditionally. Commit `3bf9efa`.

### Stale/broken files (blocked bare `pytest`)
- [x] **done** — Root-caused via `pyproject.toml: [tool.pytest.ini_options] testpaths = ["tests"]`, so a bare `pytest` run no longer auto-collects broken files under `src/`. Commit `1d0b450`.
- [x] **done** — `test_extractor.py`, `test_additional.py`, `pbs_form.py`, `notebook.py` moved (not deleted — all were untracked/uncommitted, so `rm` would be unrecoverable) from `src/legatoflow/` into a new top-level `experiments/` dir, out of the installable package. Fixes the "wrong copy gets ported" risk and the accidental-import landmine without destroying anything.
- [x] **done** — `notebook.py` (now in `experiments/`) top-level `asyncio.run(main())` guarded with `if __name__ == "__main__":`.

### Fragile patterns
- [x] **done** — `extractor.py` `OpenAI(...)` client now has `timeout=60.0, max_retries=2`. Commit `eea493c`.
- [x] **done** — `config.py`/`storage.py` load/save failures now `logger.warning`/`logger.error` instead of silently swallowing. Commit `204c375`.

### New finding (not on the original approved list)
- [x] **done** — `pyproject.toml` had `requires-python = ">=3.8"` but `notebooklm-py>=0.1.2` requires Python `>=3.10`, with no compatible version below that — `uv` could not resolve the project at all. Bumped `requires-python` to `>=3.10`, dropped the now-inconsistent 3.8/3.9 classifiers, updated the README, committed the resulting `uv.lock`. Commit `a895b44`.

### Verification note (superseded)
With the `requires-python` fix above, `uv sync` now installs cleanly and `uv run --with pytest pytest -q` passes (4/4, including the earlier `testpaths`/`_mask_secret` fixes). All LegatoFlow fixes in this file are now confirmed against a real environment, not just `py_compile`.

## Config / PDF (found during Phase 5)
- [ ] **pending** — `utils/invoice_utils.py:htmlstr_to_pdf_async` hardcodes `PDFRenderer(backend="playwright")`, ignoring the configured `pdf_backend` (and failing if Playwright isn't installed). Only Playwright implements true async; option: use the default backend and fall back to `asyncio.to_thread(render)` for sync backends.
- [ ] **pending** — legacy `~/.config/legatoflow/config` still holds plaintext API keys after migration (left untouched by design). Suggest user deletes it (or its key entries) once env vars are exported.
