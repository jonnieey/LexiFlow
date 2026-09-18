# Gap Analysis: Transcriptor + LegatoFlow

Produced by schema-mapper subagent (read-only). Terse, tables over prose.
No resolution decisions here — those happen in planning (PROGRESS.md Phase 1 next steps).

## 1. Transcriptor — DB schema

SQLite via SQLAlchemy, `src/transcriptor/models.py`. `PRAGMA foreign_keys=ON` set in `database.py`.

### `clients`
| field | type | constraints |
|---|---|---|
| id | int | PK |
| name | str(255) | NOT NULL, UNIQUE |
| email | str(255) | NOT NULL |
| (rel) rate | 1:1 Rate | cascade delete-orphan |
| (rel) jobs | 1:N Job | cascade delete-orphan |

### `rates`
| field | type | constraints |
|---|---|---|
| id | int | PK |
| normal | float | NOT NULL |
| expedite | float | NOT NULL |
| interpreted | float | NOT NULL |
| client_id | int | FK clients.id, ON DELETE CASCADE |

`job_type` string (`normal`/`expedite`/`interpreted`, validated lowercase) maps 1:1 to a rate column name — this is the pricing tier, not a transcription-provider field.

### `jobs`
| field | type | constraints |
|---|---|---|
| id | int | PK |
| client_id | int | FK clients.id, ON DELETE CASCADE |
| date_received | str | NOT NULL |
| job_number | str | NOT NULL |
| job_type | str | NOT NULL (normal/expedite/interpreted) |
| status | str | NOT NULL, default "Pending" |
| date_due | str | NOT NULL |
| total_quantity | float | NOT NULL (media duration) |
| quantity | float | NOT NULL (billable qty, may differ from total) |
| job_rate | float | NOT NULL |
| date_submitted | str | nullable |
| amount | float | NOT NULL (computed by trigger) |
| amount_paid | float | NOT NULL, default 0.0 |
| job_path | str | NOT NULL — path to the task **file** (not dir) |
| note | str | NOT NULL, default "" |

CheckConstraint: `date(date_submitted) >= date(date_received)`.

### Triggers (SQLite, all `AFTER ... ON jobs`)
- `update_amount_on_insert` / `update_amount_on_update` (of job_rate, quantity): recompute `amount = round_up_to_half(quantity * job_rate)`.
- `update_date_on_update` (of status): status→Pending clears date_submitted; status→Done sets date_submitted=today if empty.
- `update_status_on_update` (of date_submitted): date_submitted empty/NULL → status=Pending; else status=Done. (Bidirectional coupling with above trigger — status and date_submitted are two views of the same state.)
- `limit_amounts_paid_on_update` (of amount_paid): clamps amount_paid to ≤ amount.
- `update_client_job_rates_on_update` (of client_id) and `update_job_rate_on_update` (of job_type): re-derive job_rate from client's rates row.

### Job status enum
Effectively binary, DB-enforced via triggers, not a CHECK/enum type: `"Pending"` | `"Done"`. TUI hardcodes `statuses = ["Pending", "Done"]` (tui.py:908). No `In Progress`/`Failed`/`Cancelled` states exist in Transcriptor.

### Directory / file naming convention
Base: `config.base_dir` (default `platformdirs.user_data_dir("transcriptor")`).
```
{base_dir}/clients/{slugified_client_name}/{YYYY}/{MonthName}/{DD_Ddd}_{job_number}_DUE_{DD_Ddd}/
```
(`sc()` = slug/case util for client name folder.) Example actual path seen in repo:
`/home/sato/.local/share/transcriptor/clients/Natalie_Puelles/2026/April/07_Tue_950140_DUE_11_Sat/`

Within that job dir: task files named `{job_number} Due {MM.DD}{template_suffix}` (dedup via `next_non_existent_file`, appends `_1`, `_2`...). `job_path` DB field stores the **task file path**, not the directory — directory is `Path(job_path).parent`. Renaming a job's dir (on client/date change) is handled by `_sync_job_files`, which moves the whole old dir's contents to a newly computed dir and rewrites `job_path`.
Also: `clients/{client}/templates/`, `clients/{client}/invoices/` (+ `csv/`), `{base_dir}/cutoffs/`.

---

## 2. LegatoFlow — job record & storage

No DB. `JobManager` (`src/legatoflow/storage.py`) — flat JSON list at `~/.local/share/legatoflow/jobs.json`, max 50 entries (LRU-ish trim by `added_at`), config separately at `~/.config/legatoflow/config` (`ConfigManager`/`Settings` dataclass, env + file backed).

### Job record fields (union across services, all optional except id/provider)
| field | type | origin | notes |
|---|---|---|---|
| id | str | provider's native job/source id | **required** by `add_job` |
| provider | str | `"speechmatics"` \| `"revai"` \| `"notebooklm"` | **required** by `add_job` |
| status | str | provider-native string, NOT normalized | see below — differs per provider |
| created_at | provider datetime/str | from provider API | field name differs from Transcriptor's `date_received` |
| file_path | str | local input file path | analogous to Transcriptor's `job_path`, but points at **source media**, not output |
| upload_timestamp | ISO str | `datetime.now().isoformat()` set at submit time | app-side field, no provider equivalent |
| added_at | ISO str | set by `JobManager.add_job` if missing | used for sort/prune, distinct from upload_timestamp |

No `client_id`, `job_number`, `job_type`, `quantity`, `amount`, `note`, `date_due` — none of the billing/job-management concepts exist in LegatoFlow at all.

### External service call points (`src/legatoflow/services/*.py`)
| provider | submit | poll status | fetch transcript | list |
|---|---|---|---|---|
| speechmatics.py | `AsyncClient.submit_job()` | `AsyncClient.get_job_info()` | `AsyncClient.get_transcript(format_type=JSON)` → `.transcript_text` | `job_manager.list_jobs(provider=...)` |
| revai.py | `RevAiAPIClient.submit_job_local_file()` (sync, wrapped in `asyncio.to_thread`) | `sync_client.get_job_details()` | `sync_client.get_transcript_text()` | same |
| notebook_lm.py | `NotebookLMClient.sources.add_file()` | `client.sources.get()` → maps `SourceStatus` enum to string | `client.chat.ask(question=prompt, source_ids=[job_id])` → `.answer` | same |

All three call `job_manager.add_job()` on submit and `job_manager.update_job(job_id, {"status": ...})` on status poll — this is the only "persistence layer" LegatoFlow has.

### Output format ("transcript") per provider — NOT uniform
- **Speechmatics / Rev.ai**: real ASR — ordered transcript text (speaker-diarized), i.e. genuine transcription output.
- **NotebookLM**: NOT ASR. `get_transcript()` uploads the audio as a "source" then sends a fixed prompt (`NOTEBOOKLM_PROMPT_FILE`) via `chat.ask(...)`, optionally injected with case metadata (witness name, attorneys, etc. from `extractor.py`), and returns the **chat answer text** — an LLM's response about/derived from the audio, not a direct transcript. Any consumer treating "transcript" as literal ASR output will be wrong for this provider.

### Status values (NOT enum, raw provider strings, except NotebookLM which is mapped)
- Speechmatics: `job.status` passed through raw (library-defined, e.g. `running`, `done`, `rejected` — not normalized by LegatoFlow).
- Rev.ai: `job_details.status` passed through raw (e.g. `in_progress`, `transcribed`, `failed`).
- NotebookLM: explicitly mapped: `PROCESSING`/`PREPARING` → `"in_progress"`, `READY` → `"transcribed"`, `ERROR` → `"failed"`.
- `base.py` docstring implies canonical vocabulary `'transcribed' | 'failed' | 'in_progress'` but only NotebookLM actually conforms; Speechmatics/Rev.ai leak provider-native strings.

---

## 3. Overlaps / Conflicts

| concept | Transcriptor | LegatoFlow | conflict |
|---|---|---|---|
| job identity | `id` (int, autoincrement PK) | `id` (str, provider-assigned, e.g. UUID/opaque token) | type mismatch (int vs str) + semantic mismatch (surrogate PK vs external provider id) |
| job state | `status`: `"Pending"` \| `"Done"` only, DB-trigger-coupled to `date_submitted` | `status`: free-form provider string (`in_progress`, `transcribed`, `failed`, `running`, `done`, `rejected`, etc., inconsistent per provider) | Transcriptor is binary/coarse (billing lifecycle); LegatoFlow is fine-grained/technical (ASR pipeline state). No shared vocabulary. |
| file/dir location | `job_path`: path to **task file**, dir derivable via `.parent`, dir path is a structured convention (client/year/month/daynum_DUE) | `file_path`: path to **source input media** dropped wherever the CLI was pointed (no directory convention, no client/date structure) | different semantics: Transcriptor's is an organized *output/working* location, LegatoFlow's is just wherever the raw upload came from. Field name collision risk (`job_path` vs `file_path`) but values not interchangeable. |
| creation timestamp | `date_received` (str, user-entered, date only, app date_format) | `created_at` (provider-supplied, often full datetime) + `upload_timestamp` (app ISO datetime) + `added_at` (JobManager ISO datetime, may equal upload_timestamp) | Transcriptor has 1 date-only field; LegatoFlow has 3 different timestamp fields, none aligned to `date_received`'s semantics (received-from-client vs uploaded-to-service). |
| completion date | `date_submitted` (str, date, trigger-set to today when status→Done) | none — no explicit "done" timestamp field; must be inferred from polling `status` transitions | No equivalent in LegatoFlow; would need derivation logic, not a stored field. |
| owning entity | `client_id` → `clients` table (name, email, rates) | none — no client concept at all | Total gap. |
| job "type"/pricing tier | `job_type`: normal/expedite/interpreted — billing rate tier | none | Total gap — LegatoFlow has no billing concept. |
| provider/service | none (Transcriptor doesn't know about ASR providers) | `provider`: speechmatics/revai/notebooklm | Total gap in Transcriptor. |
| transcript output | none (Transcriptor manages job metadata + invoicing, not transcript content) | returned as a string from `get_transcript()`, never persisted anywhere (not even in jobs.json) | Total gap — LegatoFlow doesn't persist transcript text at all currently; it's ephemeral return value. |
| quantity/duration | `total_quantity` (media duration, from `get_media_duration`) computed at Transcriptor job creation | not tracked | Overlaps conceptually with duration metadata a provider could return, but LegatoFlow never captures it. |
| "note" field | `note` str, free text | none | Total gap. |

---

## 4. Minimal bridge (rename/alias, no new tables unless flagged in §5)

- Map LegatoFlow's `provider` + service call results into the existing `jobs.note` or a repurposed unused-capacity field for provider bookkeeping — **but** `note` is free text; using it for structured provider/status data is a hack, flag if this is the chosen path (see §5, likely needs real columns).
- Alias LegatoFlow's `file_path` → read/write through to `Job.job_path` (values differ semantically — source-file vs task-file — bridge layer must resolve which one wins, i.e. decide job_path continues to mean "the file in the Transcriptor-managed dir" and LegatoFlow's raw upload path is transient/pre-import only).
- Alias LegatoFlow's `created_at`/`upload_timestamp` → `Job.date_received` at bridge time (format conversion needed: full datetime → app's `date_format` date string).
- Status: bridge must translate LegatoFlow's provider-status vocabulary into Transcriptor's Pending/Done trigger-driven binary — e.g. `in_progress`/`running`/`preparing` → keep `Pending`; `transcribed`/`done`/`ready` → set `date_submitted` (trigger flips `status` to `Done` automatically); `failed`/`rejected`/`error` → **no existing Transcriptor state for this** (flagged below).
- Directory convention: reuse Transcriptor's `create_job_dir()` as-is for any merged job; LegatoFlow's flat/arbitrary file_path should be treated as a one-time input to be moved into the Transcriptor dir structure (mirrors existing `mv_extract_job_file` flow), not as a parallel storage location.
- `job_type`/rate tier and `client_id` continue to be required on every Job row exactly as Transcriptor already needs them — LegatoFlow-originated jobs must be assigned a client and job_type at creation time (via existing CLI prompts in `input_handler.py`), no schema change needed for this.
- Same treatment applies to `job_number` and `date_due` — both NOT NULL on `jobs` with no LegatoFlow equivalent (see §2's gap list). Assign at creation time via existing CLI prompts, same as client_id/job_type; no schema change needed.

### Operational risk (not a schema conflict, but relevant to which bridge option gets picked)
`JobManager` caps at `max_jobs=50`, trimming oldest by `added_at` (`storage.py`). If the bridge design reuses LegatoFlow's flat-JSON store as-is for provider/status tracking rather than folding that tracking into Transcriptor's `jobs` table (via the columns flagged in §5), a busy shop could silently lose the ability to poll/fetch older in-flight jobs once they age out of the cap — no error, just quietly untrackable.

## 5. Requires genuinely NEW table/column — FLAG ONLY, no resolution decided here

- **Provider identity** — no column in `jobs` for which ASR provider (speechmatics/revai/notebooklm) handled the job. Needed if Transcriptor is to track/poll/retry against the right service.
- **External/provider job ID** — `jobs.id` is an internal autoincrement int; LegatoFlow's provider job id (str) has no home. Needed to poll status / re-fetch transcript later.
- **Fine-grained ASR status** — Transcriptor's Pending/Done binary has no slot for `in_progress` (mid-flight) or `failed`/`rejected` (terminal error) states that LegatoFlow providers report. Current triggers only understand 2 states.
- **Transcript storage** — LegatoFlow never persists transcript text anywhere (returned in-memory only); if transcripts are to be retained, no existing column/table holds arbitrary-length text output.
- **NotebookLM-specific fields** — prompt used, chat answer vs true transcript distinction, source_id vs job_id, metadata-injection record — none of this has any existing home; also worth flagging that NotebookLM output isn't literal ASR (see §2) which may itself be a product-level flag, not just a schema one.
- **Upload/media source path separate from managed job_path** — if the pre-import raw upload location must be retained distinctly from the organized `job_path`, no column currently captures it (today `job_path` serves double duty as "the" file location).
- **Provider polling metadata** — e.g. last-polled-at, retry count, error message — no equivalent in Transcriptor schema; LegatoFlow doesn't track this either but future retry logic likely will need it.

## 6. Decision (user-confirmed, Phase 1)

- **Provider/external-job tracking**: 3 new nullable columns on `jobs` — `provider`, `external_job_id`, `transcription_status`. Single source of truth once a job exists in Transcriptor's DB; leaves the existing `status`/`date_submitted` (Pending/Done) columns and their triggers completely untouched — `transcription_status` is orthogonal, not a replacement. Covers §5's "Provider identity", "External/provider job ID", and "Fine-grained ASR status" items.
- **NotebookLM identity**: its `source_id` fills the `external_job_id` slot like any other provider's job id — no separate column. The "not real ASR" caveat (§2) stays a documented behavior difference, not a schema field.
- **Transcript storage**: a `.txt` file in the job's existing Transcriptor-managed directory, same convention as task files/invoices — zero schema change. Covers §5's "Transcript storage" item. Also resolves "Upload/media source path" (§5): the file lands in the same directory the transcript does, no separate column needed.
- **Provider polling metadata** (last-polled-at, retry count, error message): deferred to Phase 2 (job pipeline wiring) — operational/runtime state that should be shaped by how the actual polling loop works, not decided ahead of that design.
- **NotebookLM-specific audit fields** (prompt used, metadata-injection record): not added. Out of scope for a minimal bridge; the chat-answer-as-transcript behavior is a documented caveat, not a tracked field. Can be revisited if a real need surfaces.

Net: **3 new nullable columns**, no new tables, no changes to existing triggers/constraints. Matches the "minimal bridge, prefer renaming/aliasing over new tables" instruction — this is the smallest schema change that covers every item flagged in §5 except deliberately-deferred/declined ones.
