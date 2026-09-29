# Installation Instructions for Windows

For Windows users who are not comfortable with command-line tools or installing Python manually, the recommended approach is to download the standalone executable.

## Installing the Standalone Executable (Releases)

1.  **Download**: Go to the Releases page (e.g., on GitHub) and download `transcriptor.exe`.
2.  **Run**: Double-click `transcriptor.exe` to launch the application.
3.  **Requirements**:
    *   **PDF Backend**: For PDF invoice generation, you need a PDF rendering backend.

    **Recommended for Windows: Playwright**
    ```powershell
    pip install playwright
    playwright install
    ```

    *   **GTK3 Runtime (Alternative)**: If using WeasyPrint backend, install GTK3 runtime libraries.
        *   Download and install the latest "GTK3 Runtime Environment" from [GTK-for-Windows-Runtime-Environment-Installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases).
        *   Restart your computer after installing GTK3.

## Building from Source (For Developers)

If you want to build the executable yourself:

1.  **Install Python**: Ensure Python 3.9+ is installed.
2.  **Install Build Tools**:
    ```powershell
    pip install pyinstaller uv
    ```
3.  **Build**:
    Run the provided PowerShell script (will prompt for PDF backend selection):
    ```powershell
    .\scripts\build_windows_exe.ps1
    ```
    Or run PyInstaller manually (specify backend via environment variable):
    ```powershell
    # Set preferred backend before building
    $env:LEXIFLOW_PDF_BACKEND = "playwright"
    pyinstaller lexiflow.spec
    ```
    The executable will be generated in the `dist` folder.

## Alternative: Using `uv` (For Command Line Users)

If you are comfortable with the command line:

1.  **Install `uv`**:
    ```powershell
    irm https://astral.sh/uv/install.ps1 | iex
    ```
2.  **Install Transcriptor with PDF backend**:
    ```powershell
    # Install with Playwright (recommended for Windows)
    uv tool install ".\[playwright]" --force
    playwright install

    # Or with xhtml2pdf
    uv tool install ".\[xhtml2pdf]" --force

    # Or with WeasyPrint (requires GTK3 runtime)
    uv tool install ".\[weasyprint]" --force
    ```
3.  **Run**:
    ```powershell
    trans5
    ```

## API Keys

API keys are read from environment variables only (never from the config file). Set them once per user in PowerShell, then open a new terminal:

```powershell
setx OPENAI_API_KEY "..."
setx SPEECHMATIX_API_KEY "..."
setx REVAI_API_KEY "..."
```

The PDF backend can be chosen at runtime via `pdf_backend` in the config file (`update config --pdf-backend playwright`) or the TUI Configuration screen; `LEXIFLOW_PDF_BACKEND` still overrides it.
