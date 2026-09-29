# LexiFlow

> A terminal-based application for managing transcription jobs, clients, and professional invoices — unifying job CRUD/invoicing (ported from Transcriptor) with external transcription services (ported from LegatoFlow).

LexiFlow streamlines the workflow for freelance transcribers and small agencies. It provides a centralized system to track jobs, manage client-specific rates, monitor deadlines, submit/poll transcription jobs to external ASR providers, and generate professional PDF invoices — all from your terminal.

See `PROGRESS.md` for the merge status and `gap-analysis.md` for the schema/data-shape decisions behind this unification.

## Key Features

*   **Dual Interface:**
    *   **TUI (Textual User Interface):** A rich, interactive dashboard powered by [Textual](https://textual.textualize.io/). Features Vim-like navigation, sorting, and direct editing.
    *   **CLI (Command Line Interface):** A scriptable command line tool for quick entry, automation, and piping.
*   **Comprehensive Job Tracking:** Manage job numbers, due dates, audio duration, status (Pending/Done), and file locations.
*   **Client Management:** Maintain a database of clients with specific contact details.
*   **Flexible Rate System:** Define custom rates per client for different job types (Normal, Expedite, Interpreted).
*   **Automated Invoicing:**
    *   Generate PDF and CSV invoices.
    *   Support for multiple invoice themes.
    *   Annual summary generation.
*   **Workflow Automation:** Automatically organizes job files into a structured directory hierarchy based on client and date.
*   **Data Safety:** Built-in SQLite database with automatic backup capabilities.
*   **External Transcription (in progress):** Submit/poll/fetch jobs against Speechmatics, Rev.ai, and NotebookLM — wiring in progress, see `PROGRESS.md` Phase 2.

## Installation

This project uses `uv` for modern, fast Python package management.

### Prerequisites
*   Python 3.9+
*   `uv` (Recommended) or `pip`

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/jonnieey/lexiflow.git
    cd lexiflow
    ```

2.  **Install dependencies:**
    ```bash
    # Create virtual environment and install
    uv venv
    source .venv/bin/activate
    uv pip install -e .
    ```

### PDF Backends (Optional)

LexiFlow supports multiple PDF rendering engines. Install one or more backends as needed:

```bash
# Install with Playwright (recommended for Windows)
uv pip install -e '.[playwright]'
playwright install  # Install browser binaries

# Install with WeasyPrint (requires system libraries)
uv pip install -e '.[weasyprint]'

# Install with xhtml2pdf (pure Python, limited CSS)
uv pip install -e '.[xhtml2pdf]'

# Install all backends
uv pip install -e '.[all]'
```

The system will auto-detect available backends with priority: Playwright > WeasyPrint > xhtml2pdf.

To pick a backend explicitly, set `pdf_backend` in the config file (`auto`, `playwright`, `weasyprint`, or `xhtml2pdf`) — via `update config --pdf-backend <name>` in the CLI or the TUI Configuration screen. The `LEXIFLOW_PDF_BACKEND` environment variable overrides the config file.

## Usage

### 🖥️ TUI Mode (Interactive Dashboard)

Launch the visual interface:
```bash
lexiflow tui
```

**Navigation:**
*   **Tabs:** Dashboard, All Jobs, Cutoffs, Clients, Rates, Configuration.
*   **Vim Mode:** Press `v` to toggle. Use `h` / `l` to switch tabs.
*   **Actions:**
    *   `a`: Add New Job
    *   `e`: Edit Selected Job
    *   `r`: Refresh Table

**Dashboard:** Quickly view and manage pending jobs. Select multiple jobs to perform batch actions.

### ⌨️ CLI Mode (Command Line)

The CLI offers both an interactive shell and one-off command execution.

#### 1. Interactive Shell
Enter the dedicated shell environment:
```bash
lexiflow
```
Prompt: `(trans5) ` (unchanged from the ported Transcriptor shell — cosmetic, not yet renamed)

#### 2. One-off Commands
Run commands directly from your system shell. This is ideal for scripts or quick checks. Aliases defined in `.cmd2rc` are loaded silently.
```bash
lexiflow cli show version
lexiflow cli invoice -c 1 --print
```

#### Common Commands

| Command | Description | Example |
| :--- | :--- | :--- |
| `show` | List data (clients, jobs, rates) | `show clients` |
| `add` | Create new records | `add job -f /path/to/audio.mp3` |
| `update` | Modify existing records | `update job -j 12345 -v status=Done` |
| `delete` | Remove records | `delete job -w id=5` |
| `invoice` | Generate invoices | `invoice -c 1 -w "date_submitted > '2023-01-01'"` |
| `backup` | Backup database | `backup` |

Use `help <command>` for detailed syntax (e.g., `help add`).

## Configuration

All settings live in **one** YAML file:

*   **Config File:** `~/.config/lexiflow/config.yaml` (Linux; platform config dir elsewhere)
*   **Data / Profile:** `~/.local/share/transcriptor/` (unchanged — existing jobs, DB and backups keep working)

On first run, the old `~/.config/transcriptor/config.yaml` and LegatoFlow `~/.config/legatoflow/config` are merged into it automatically. The old files are left in place and can be deleted once you've checked the new one.

**Example `config.yaml`:**
```yaml
base_dir: /home/user/.local/share/transcriptor
date_format: "%Y-%m-%d"
invoice_theme: default
pdf_backend: auto          # auto | playwright | weasyprint | xhtml2pdf
ai_model: gpt-4o-mini
base_url: null             # OpenAI-compatible endpoint, e.g. https://api.deepseek.com
ai_api_key_env: null       # env var holding the AI key; null = OPENAI_API_KEY
notebooklm_notebook_id: null
notebooklm_prompt_file: null
file_manager: ""
terminal: ""
```

Edit it through the TUI Configuration screen, `update config ...`, or `config set <key> <value>`. In the CLI, `config set <TAB>` lists every key with its current value, and `config set <key> <TAB>` suggests values (backends, themes, currencies, key env var names, paths). Unknown keys and invalid values (e.g. `conversion_rate abc`) are rejected without touching the file.

### API keys (environment variables only)

API keys are **never** read from or stored in the config file. Export them in your shell profile:

```sh
export OPENAI_API_KEY=...        # or whichever var ai_api_key_env names
export SPEECHMATIX_API_KEY=...
export REVAI_API_KEY=...
```

**Using a non-OpenAI provider (e.g. DeepSeek):** keep `OPENAI_API_KEY` for OpenAI and point LexiFlow at the right variable, so the endpoint and key always match:

```sh
config set base_url https://api.deepseek.com
config set ai_model deepseek-v4-flash
config set ai_api_key_env DEEPSEEK_API_KEY
```

If the named variable isn't set, extraction fails with `<NAME> is not set` rather than falling back to another key.

`config show` lists which variables are in use (masked). `config set <anything>_API_KEY ...` is refused. A `.env` file is still loaded for development, but variables already set in your shell take precedence.

## Windows Installation

For Windows users, see [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) for detailed instructions.

**Recommended PDF backend for Windows:** Playwright
```powershell
# Install with Playwright backend
pip install lexiflow[playwright]
playwright install
```

## Database & Structure

Data is stored in an **SQLite** database (`transcriptor.db`) located in your `base_dir` — filename kept as-is to reuse the existing database file.

**Directory Structure:**
```text
base_dir/
├── clients/
│   └── ClientName/
│       ├── 2023/
│       │   └── Month/
│       │       └── Date_JobNumber_Due/  <-- Job Files Here
│       ├── invoices/
│       └── templates/
├── cutoffs/
├── backups/
└── transcriptor.db
```

## Development

### Setup
Install development dependencies:
```bash
uv pip install -e '.[dev]'
```

### Testing
Run the test suite using `pytest`:
```bash
pytest
```

## License

MIT License. See `LICENSE` for details.

---
