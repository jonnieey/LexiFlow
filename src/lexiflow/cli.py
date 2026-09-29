# type: ignore
import asyncio
import json
import os
import sys
import threading
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import cmd2
from prompt_toolkit import prompt
from prompt_toolkit.styles import Style

from lexiflow.base import Transcriptor
from lexiflow.config import (
    DEFAULT_AI_API_KEY_ENV,
    SECRET_KEYS,
    ai_api_key_env_name,
    config_manager,
    configurable_keys,
)
from lexiflow.extractor import MetadataExtractor, fill_template
from lexiflow.input_handler import CLIInputHandler
from lexiflow.pdf import BACKEND_PRIORITY, PDFRenderer, not_installed_message
from lexiflow.utils.currency import CURRENCY_SYMBOLS
from lexiflow.services import get_service
from lexiflow.utils import (
    invoice_template_themes,
    list_candidate_files,
    open_in_file_manager,
    parse_conditions,
    parse_conditions_as_dict,
    positive_number_validator,
    process_metadata_to_vocabulary,
    yes_no_validator,
)
from lexiflow.utils.docx_utils import generate_cutoff_list_from_docx
from lexiflow.view import TranscriptorView

style = Style.from_dict(
    {
        "": "#FFA500 bg:#2A2B3C",
        "space": "bg:#2A2B3C",
        "prompt": "#8BE9FD bg:#2A2B3C",
    }
)

base_parser = cmd2.Cmd2ArgumentParser(description="Transcriptor CLI")
base_subparsers = base_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)

show_parser = base_subparsers.add_parser("show", help="show object")
show_subparsers = show_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)
show_config_parser = show_subparsers.add_parser("config", help="show config")
show_profile_parser = show_subparsers.add_parser(
    "profile", help="show profile"
)
show_clients_parser = show_subparsers.add_parser(
    "clients", help="show client"
)
show_rates_parser = show_subparsers.add_parser("rates", help="show rates")
show_jobs_parser = show_subparsers.add_parser("jobs", help="show jobs")
show_cutoffs_parser = show_subparsers.add_parser(
    "cutoffs", help="show cutoffs"
)
show_cutoffs_parser.add_argument("-y", "--year", help="Year for cutoffs")
show_version_parser = show_subparsers.add_parser(
    "version", help="show version"
)
show_pdf_backends_parser = show_subparsers.add_parser(
    "pdf_backends", help="show available PDF backends"
)

show_jobs_parser.add_argument(
    "-a", "--all", action="store_true", help="show all jobs"
)


def add_query_arguments(parser):
    parser.add_argument(
        "-w",
        "--where",
        action="append",
        help='Specify conditions in the format "field[operator]value", e.g., -w id<=1 -w amount>0',
    )
    parser.add_argument(
        "-r",
        "--raw",
        help="Raw sql query",
    )


add_query_arguments(show_clients_parser)
add_query_arguments(show_rates_parser)
add_query_arguments(show_jobs_parser)


add_parser = base_subparsers.add_parser("add", help="add object")
add_subparsers = add_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)
add_client_parser = add_subparsers.add_parser("client", help="add client")
add_client_parser.add_argument(
    "-n",
    "--name",
    type=str,
    help="client name",
)
add_client_parser.add_argument(
    "-e",
    "--email",
    type=str,
    help="client email",
)

add_job_parser = add_subparsers.add_parser("job", help="add job")

add_job_parser.add_argument(
    "-f",
    "--file",
    type=str,
    help="Job File Path",
)
add_job_parser.add_argument("-c", "--client_id", type=int, help="Client ID")
add_job_parser.add_argument("-j", "--job_number", help="Job Number")
add_job_parser.add_argument("-r", "--date_received", help="Date Received")
add_job_parser.add_argument("-d", "--date_due", help="Date Due")
add_job_parser.add_argument("-q", "--quantity", help="Quantity")
add_job_parser.add_argument("-w", "--work_on_file", help="Work On File")
add_job_parser.add_argument("-t", "--job_type", help="Job Type")
add_job_parser.add_argument("-T", "--job_template", help="Job Template")
add_job_parser.add_argument("-N", "--note", help="Job Note")


add_cutoffs_parser = add_subparsers.add_parser(
    "cutoffs", help="generate cutoffs file from docx"
)
add_cutoffs_parser.add_argument(
    "-f",
    "--file",
    type=str,
    help="Cutoffs docx File Path",
)
add_cutoffs_parser.add_argument("-d", "--date_fmt", help="Date Format")
add_cutoffs_parser.add_argument("-y", "--year", help="Year for cutoffs")


update_parser = base_subparsers.add_parser("update", help="update object")
update_subparsers = update_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)
update_config_parser = update_subparsers.add_parser(
    "config", help="update config"
)

update_config_parser.add_argument("-b", "--base-dir", help="base directory")
update_config_parser.add_argument("-d", "--date-format", help="date format")
update_config_parser.add_argument(
    "-c", "--display-currency", help="table display currency (e.g. KES)"
)
update_config_parser.add_argument(
    "-i", "--invoice-currency", help="invoice generation currency"
)
update_config_parser.add_argument(
    "-r", "--conversion-rate", type=float, help="manual conversion rate"
)
update_config_parser.add_argument(
    "-s", "--currency-segment", help="sendwave segmentName"
)
update_config_parser.add_argument(
    "--currency-receive-country", help="sendwave receiveCountryIso2"
)
update_config_parser.add_argument(
    "--currency-send-country", help="sendwave sendCountryIso2"
)
update_config_parser.add_argument(
    "-p",
    "--pdf-backend",
    choices=["auto", *BACKEND_PRIORITY],
    help="PDF rendering backend (saved to config)",
)

update_profile_parser = update_subparsers.add_parser(
    "profile", help="update profile"
)
update_profile_parser.add_argument("-n", "--name", help="name")
update_profile_parser.add_argument("-a", "--area", help="area")

update_profile_parser.add_argument("-c", "--country", help="country")


def add_update_delete_query_arguments(parser):
    parser.add_argument(
        "-r",
        "--raw",
        help="Raw sql query",
    )
    parser.add_argument(
        "-w",
        "--where",
        action="append",
        help='Specify conditions in the format "field[operator]value", e.g., -w id<=1 -w amount>0',
    )
    parser.add_argument(
        "-v",
        "--values",
        action="append",
        help='Specify values in the format "field=value", e.g., -v id=1 -v amount=100',
    )


update_client_parser = update_subparsers.add_parser(
    "client", help="update client"
)
add_update_delete_query_arguments(update_client_parser)

update_rates_parser = update_subparsers.add_parser(
    "rates", help="update rates"
)
add_update_delete_query_arguments(update_rates_parser)

update_jobs_parser = update_subparsers.add_parser("jobs", help="update job")
add_update_delete_query_arguments(update_jobs_parser)
update_jobs_parser.add_argument(
    "-T", "--table", action="store_true", help="Print cutoffs table"
)
update_jobs_parser.add_argument(
    "-c", "--client_id", type=int, help="Client ID"
)
update_jobs_parser.add_argument("-y", "--year", help="Year for cutoffs")
update_jobs_parser.add_argument(
    "-a",
    "--add-jobs",
    help="Additional job numbers to update, comma-separated (e.g. '923999,923876')",
)

delete_parser = base_subparsers.add_parser("delete", help="delete object")
delete_subparsers = delete_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)
delete_client_parser = delete_subparsers.add_parser(
    "clients", help="delete client"
)
add_update_delete_query_arguments(delete_client_parser)
delete_client_parser.add_argument(
    "-P", "--purge", action="store_true", help="Purge client data"
)
delete_client_parser.add_argument(
    "-N",
    "--no-confirm",
    action="store_true",
    help="Delete without confirmation",
)

delete_jobs_parser = delete_subparsers.add_parser("jobs", help="delete job")
add_update_delete_query_arguments(delete_jobs_parser)
delete_jobs_parser.add_argument(
    "-P", "--purge", action="store_true", help="Purge job data"
)
delete_jobs_parser.add_argument(
    "-N",
    "--no-confirm",
    action="store_true",
    help="Delete without confirmation",
)

invoice_parser = base_subparsers.add_parser(
    "invoice", help="generate invoice"
)
invoice_parser.add_argument("-c", "--client_id", help="Client ID")
invoice_parser.add_argument(
    "-w",
    "--where",
    action="append",
    help='Specify conditions in the format "field[operator]value", e.g., -w id<=1 -w amount>0',
)
invoice_parser.add_argument("-r", "--raw", help="Raw sql query")
invoice_parser.add_argument(
    "-p", "--print", action="store_true", help="Print invoice"
)
invoice_parser.add_argument(
    "-T", "--table", action="store_true", help="Print cutoffs table"
)
invoice_parser.add_argument(
    "-S",
    "--summary",
    action="store_true",
    help="Print annual summary invoice",
)
invoice_parser.add_argument(
    "-l", "--previous_year_cutoff", help="Previous year last cutoff"
)
invoice_parser.add_argument("-y", "--year", help="Year of cutoff")
invoice_parser.add_argument(
    "-t",
    "--invoice_template",
    help="Select invoice template",
    default=None,
    choices=invoice_template_themes(),
)
invoice_parser.add_argument(
    "-m", "--markdown", action="store_true", help="Preview markdown invoice"
)
invoice_parser.add_argument(
    "--csv", action="store_true", help="Generate csv invoice"
)
invoice_parser.add_argument(
    "-a",
    "--add-jobs",
    help="Additional job numbers to include, comma-separated (e.g. '923999,923876')",
)

purge_parser = base_subparsers.add_parser(
    "purge", help="purge job media files, ex. m4a, mp3, mp4"
)
purge_parser.add_argument(
    "-w",
    "--where",
    action="append",
    help='Specify conditions in the format "field[operator]value", e.g., -w id<=1 -w amount>0',
)
purge_parser.add_argument("-r", "--raw", help="Raw sql query")


open_parser = base_subparsers.add_parser(
    "open", help="open a job's directory in the system file manager"
)
open_parser.add_argument(
    "-j", "--job_id", type=int, required=True, help="Job ID"
)

backup_parser = base_subparsers.add_parser("backup", help="backup database")
restore_parser = base_subparsers.add_parser(
    "restore", help="restore database"
)


transcribe_parser = base_subparsers.add_parser(
    "transcribe", help="submit/poll/fetch external transcription for a job"
)
transcribe_subparsers = transcribe_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)

TRANSCRIPTION_PROVIDERS = ["speechmatics", "revai", "notebooklm"]
TRANSCRIPTION_READY_STATUSES = {"transcribed", "completed", "done"}

transcribe_submit_parser = transcribe_subparsers.add_parser(
    "submit", help="submit a job's media file for transcription"
)
transcribe_submit_parser.add_argument(
    "-j", "--job_id", type=int, required=True, help="Job ID"
)
transcribe_submit_parser.add_argument(
    "-P",
    "--provider",
    choices=TRANSCRIPTION_PROVIDERS,
    help="Transcription provider (prompted interactively if omitted)",
)
transcribe_submit_parser.add_argument(
    "--vocabulary",
    help="Comma-separated additional vocabulary terms",
)

transcribe_status_parser = transcribe_subparsers.add_parser(
    "status", help="poll transcription status for a job"
)
transcribe_status_parser.add_argument(
    "-j", "--job_id", type=int, required=True, help="Job ID"
)

transcribe_check_parser = transcribe_subparsers.add_parser(
    "check", help="poll a job's transcription and fetch it if ready"
)
transcribe_check_parser.add_argument(
    "-j", "--job_id", type=int, required=True, help="Job ID"
)
transcribe_check_parser.add_argument(
    "-m",
    "--metadata",
    help="Path to a metadata JSON file to enhance the transcript request",
)

transcribe_fetch_parser = transcribe_subparsers.add_parser(
    "fetch", help="fetch the transcript for a job"
)
transcribe_fetch_parser.add_argument(
    "-j", "--job_id", type=int, required=True, help="Job ID"
)
transcribe_fetch_parser.add_argument(
    "-m",
    "--metadata",
    help="Path to a metadata JSON file to enhance the transcript request",
)


def _mask_secret(key: str, value: Any) -> str:
    """Mask API-key-like values for safe display/logging."""
    if "API_KEY" not in key and "KEY" not in key:
        return str(value)
    if value and len(str(value)) > 8:
        value = str(value)
        return value[:4] + "*" * (len(value) - 8) + value[-4:]
    return "[REDACTED]"


config_parser = base_subparsers.add_parser(
    "config", help="manage LegatoFlow provider API config"
)
config_subparsers = config_parser.add_subparsers(
    title="subcommands", help="subcommand help"
)

config_show_parser = config_subparsers.add_parser(
    "show", help="show current configuration"
)

_PATH_CONFIG_KEYS = {"base_dir", "notebooklm_prompt_file", "notebooklm_storage_path"}


def _complete_config_key(cmd) -> List[cmd2.CompletionItem]:
    """'config set <TAB>': every configurable key with its current value."""
    return [
        cmd2.CompletionItem(key, "" if (v := config_manager.get(key)) is None else str(v))
        for key in configurable_keys()
    ]


def _complete_config_value(
    cmd, text: str, line: str, begidx: int, endidx: int, arg_tokens
) -> List[str]:
    """'config set <key> <TAB>': suggestions that fit the chosen key."""
    key = (arg_tokens.get("key") or [""])[0].lower()
    if key in _PATH_CONFIG_KEYS:
        return cmd.path_complete(text, line, begidx, endidx)
    if key == "pdf_backend":
        choices = ["auto", *BACKEND_PRIORITY]
    elif key == "invoice_theme":
        choices = invoice_template_themes()
    elif key in ("display_currency", "invoice_currency"):
        choices = sorted(CURRENCY_SYMBOLS)
    elif key == "ai_api_key_env":
        # Variable names only -- never their values.
        choices = sorted(n for n in os.environ if n.endswith("_API_KEY"))
    else:
        current = config_manager.get(key)
        choices = [] if current is None else [str(current)]
    return cmd.basic_complete(text, line, begidx, endidx, choices)


config_set_parser = config_subparsers.add_parser(
    "set", help="set a configuration value"
)
config_set_parser.add_argument(
    "key",
    help="Configuration key to set",
    choices_provider=_complete_config_key,
    descriptive_header="Current value",
)
config_set_parser.add_argument(
    "value", help="Value to set", completer=_complete_config_value
)


extract_parser = base_subparsers.add_parser(
    "extract", help="extract metadata from Notice and PBS PDFs"
)
extract_parser.add_argument(
    "-j",
    "--job_id",
    type=int,
    help="Job ID -- resolves notice/PBS interactively from the job's directory if -n/-p aren't given",
)
extract_parser.add_argument(
    "-n", "--notice", type=Path, help="Path to notice PDF"
)
extract_parser.add_argument(
    "-p", "--pbs", type=Path, help="Path to PBS PDF"
)
extract_parser.add_argument(
    "-o",
    "--output",
    type=Path,
    help="Output path for metadata JSON (default: <pbs_dir>/metadata.json)",
)

fill_parser = base_subparsers.add_parser(
    "fill", help="fill a docx template with metadata"
)
fill_parser.add_argument(
    "-j",
    "--job_id",
    type=int,
    help="Job ID -- resolves template/metadata interactively from the job's directory if not given explicitly",
)
fill_parser.add_argument(
    "-t", "--template", type=Path, help="Path to docx template"
)
fill_parser.add_argument(
    "-o",
    "--output",
    type=Path,
    help="Output path (default: <template>_filled.docx)",
)
fill_group = fill_parser.add_mutually_exclusive_group(required=False)
fill_group.add_argument(
    "-m", "--metadata", type=Path, help="Path to metadata JSON file"
)
fill_group.add_argument(
    "-n",
    "--notice",
    type=Path,
    help="Path to notice PDF (requires -p/--pbs; extracts metadata first)",
)
fill_parser.add_argument(
    "-p", "--pbs", type=Path, help="Path to PBS PDF (used with -n/--notice)"
)

process_parser = base_subparsers.add_parser(
    "process",
    help="full workflow: extract metadata, optionally fill a template, and transcribe",
)
process_parser.add_argument(
    "-j",
    "--job_id",
    type=int,
    help="Job ID -- resolves notice/PBS interactively from the job's directory and auto-fills --audio if -n/-p/-a aren't given",
)
process_parser.add_argument(
    "-n", "--notice", type=Path, help="Path to notice PDF"
)
process_parser.add_argument("-p", "--pbs", type=Path, help="Path to PBS PDF")
process_parser.add_argument(
    "-a", "--audio", type=Path, help="Path to audio/video file"
)
process_parser.add_argument(
    "-P",
    "--provider",
    choices=TRANSCRIPTION_PROVIDERS,
    required=True,
    help="Transcription provider",
)
process_parser.add_argument(
    "-t",
    "--template",
    type=Path,
    help="Path to docx template to fill (required -- prompted interactively with -j if omitted)",
)
process_parser.add_argument(
    "--wait",
    action="store_true",
    help="Wait for transcription to complete and fetch the transcript",
)


class TranscriptorCMD(cmd2.Cmd):
    prompt = "(trans5) "

    def __init__(self, app: None = None, history=True, alias=True):
        self.app = app or Transcriptor()

        history_file = (
            self.app.base_dir.joinpath(".history") if history else None
        )

        alias_script = (
            self.app.CONFIG_DIR.joinpath(".cmd2rc") if alias else None
        )

        super().__init__(
            persistent_history_file=history_file,
            persistent_history_length=500,
            allow_cli_args=False,
            startup_script=alias_script,
            silence_startup_script=True,
            allow_redirection=False,
        )

        self.debug = True

        self.add_settable(cmd2.Settable("debug", bool, "debug", self))
        self._update_prompt()
        from lexiflow.pdf import PDFRenderer

        available = PDFRenderer.available_backends() + ["auto"]
        self.add_settable(
            cmd2.Settable(
                "pdf_backend",
                str,
                "PDF rendering backend",
                self,
                choices=available,
            )
        )

        self.input_handler = CLIInputHandler(
            self.app.config, self.show_clients
        )

    def _update_prompt(self) -> None:
        """Update the CLI prompt to show current PDF backend."""
        from lexiflow.pdf import PDFRenderer

        backend = PDFRenderer.get_default_backend()
        if backend:
            self.prompt = f"(trans5 [{backend}]) "
        else:
            self.prompt = "(trans5 [auto]) "

    @property
    def pdf_backend(self) -> str:
        """Get current default PDF backend name."""
        from lexiflow.pdf import PDFRenderer

        backend = PDFRenderer.get_default_backend()
        return backend if backend else "auto"

    @pdf_backend.setter
    def pdf_backend(self, name: str) -> None:
        """Set default PDF backend and update prompt."""
        from lexiflow.pdf import PDFRenderer

        if name == "auto":
            # Clear default backend to allow auto-detection
            PDFRenderer._default_backend = None
        else:
            PDFRenderer.set_default_backend(name)
        self._update_prompt()

    def _apply_pdf_backend(self, name: str) -> None:
        """Use a newly configured backend now, if it is installed."""
        if name in ("auto", *PDFRenderer.available_backends()):
            self.pdf_backend = name
        else:
            self.poutput(not_installed_message(name))

    def do_EOF(self, arg):
        """

        Exit

        """

        self.poutput("\n** Exiting program, bye **")

        return True

    def do_exit(self, arg):
        """Exit"""

        self.poutput("\n** Exiting program, bye **")

        return True

    def do_quit(self, arg: str):
        """Exit"""

        self.poutput("\n** Exiting program, bye **")

        return True

    def emptyline(self):
        pass

    def do_clear(self, arg):
        """Clear screen"""

        os.system("cls" if os.name == "nt" else "clear")

    def show_config(self, arg: Namespace):
        """
        Show configuration
        Ex.
           show config
        """
        config = self.app.config
        TranscriptorView().print_table(config.__dict__, title="Configuration")

    show_config_parser.set_defaults(func=show_config)

    def show_profile(self, arg: Namespace):
        """
        Show profile
        Ex.
           show profile
        """
        if profile := self.app.profile:
            TranscriptorView().print_table(profile.__dict__, title="Profile")

    show_profile_parser.set_defaults(func=show_profile)

    def show_clients(self, args: Optional[Namespace]):
        """
        Show clients
        Ex.
           show clients
        """
        if args:
            if args.raw:
                clients = self.app.api.get_clients(raw_sql_stmt=args.raw)
            elif args.where:
                conditions = parse_conditions(args.where)
                clients = self.app.api.get_clients(conditions=conditions)
            else:
                clients = self.app.api.get_clients()
        else:
            clients = self.app.api.get_clients()
        TranscriptorView().print_table(
            clients, orientation="horizontal", title="Clients"
        )

    show_clients_parser.set_defaults(func=show_clients)

    def show_rates(self, args: Namespace):
        if args.raw:
            rates = self.app.api.get_rates(raw_sql_stmt=args.raw)
        elif args.where:
            conditions = parse_conditions(args.where)
            rates = self.app.api.get_rates(conditions=conditions)
        else:
            rates = self.app.api.get_rates()
        TranscriptorView().print_table(
            rates,
            orientation="horizontal",
            title="Rates",
            config=self.app.config,
        )

    show_rates_parser.set_defaults(func=show_rates)

    def show_jobs(self, args: Namespace):
        if args:
            if args.raw:
                jobs = self.app.api.get_jobs(raw_sql_stmt=args.raw)
            elif args.where:
                conditions = parse_conditions(args.where)
                jobs = self.app.api.get_jobs(conditions=conditions)
            elif args.all:
                jobs = self.app.api.get_jobs()
            else:
                jobs = self.app.api.get_jobs(
                    conditions={"status": [("=", "Pending")]}
                )

        TranscriptorView().print_table(
            jobs,
            orientation="horizontal",
            title="Jobs",
            config=self.app.config,
        )

    show_jobs_parser.set_defaults(func=show_jobs)

    def show_cutoffs(self, args: Namespace):
        cutoffs = self.app.load_cutoffs(as_str=True, year=args.year)
        formatted_cutoffs = [[str(i)] + row for i, row in enumerate(cutoffs)]
        TranscriptorView().print_table(
            formatted_cutoffs, orientation="horizontal", title="Cutoffs"
        )

    show_cutoffs_parser.set_defaults(func=show_cutoffs)

    def show_version(self, args: Namespace):
        self.poutput(f"Version: {self.app.version}")

    show_version_parser.set_defaults(func=show_version)

    def show_pdf_backends(self, args: Namespace):
        """Show available PDF backends and current default."""
        from lexiflow.pdf import PDFRenderer

        available = PDFRenderer.available_backends()
        current = PDFRenderer.get_default_backend()
        self.poutput(f"Available PDF backends: {', '.join(available)}")
        self.poutput(
            f"Current default backend: {current if current else 'auto (detected)'}"
        )
        self.poutput(f"Backend priority: playwright > weasyprint > xhtml2pdf")

    show_pdf_backends_parser.set_defaults(func=show_pdf_backends)

    @cmd2.with_argparser(show_parser)
    def do_show(self, args: Namespace):
        """

        Show command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("show")

    def add_client(self, args: Namespace):
        client_info = self.input_handler.get_client_info(args)

        if client_info["name"] and client_info["email"]:
            self.app.create_client(
                name=client_info["name"], email=client_info["email"]
            )

        else:
            self.poutput("Name and email are required.")

    add_client_parser.set_defaults(func=add_client)

    def add_job(self, args: Namespace):
        job_file_path = self.input_handler.get_job_file_path(args)

        if not job_file_path.exists():
            self.poutput(f"File not found: {job_file_path}")

            return

        if job_file_path:
            job_info = self.input_handler.get_job_info(args, job_file_path)

            def task_callback(task_file):
                return self.input_handler.get_task_info(args, task_file)

            if job_info:
                self.app.create_job(job_file_path, job_info, task_callback)

            else:
                self.poutput("Job information could not be collected.")

    add_job_parser.set_defaults(func=add_job)

    def add_cutoffs(self, args: Namespace):
        docx_path = self.input_handler.get_cutoff_file(args)

        if not docx_path.exists():
            self.poutput(f"File not found: {docx_path}")

            return

        cutoffs = generate_cutoff_list_from_docx(
            docx_path=str(docx_path), date_fmt=args.date_fmt
        )

        self.app.save_cutoffs(cutoffs, year=args.year)

    add_cutoffs_parser.set_defaults(func=add_cutoffs)

    @cmd2.with_argparser(add_parser)
    def do_add(self, args: Namespace):
        """

        Add command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("add")

    def update_config(self, args: Namespace):
        config = self.app.config

        if args.base_dir:
            config.base_dir = args.base_dir

        if args.date_format:
            config.date_format = args.date_format

        if args.display_currency:
            config.display_currency = args.display_currency

        if args.invoice_currency:
            config.invoice_currency = args.invoice_currency

        if args.conversion_rate is not None:
            config.conversion_rate = args.conversion_rate

        if args.currency_segment:
            config.currency_segment = args.currency_segment

        if args.currency_receive_country:
            config.currency_receive_country = args.currency_receive_country

        if args.currency_send_country:
            config.currency_send_country = args.currency_send_country

        if args.pdf_backend:
            config.pdf_backend = args.pdf_backend
            self._apply_pdf_backend(args.pdf_backend)

        self.app.config = config

        self.app.save_config()

    update_config_parser.set_defaults(func=update_config)

    def update_profile(self, args: Namespace):
        profile = self.app.profile

        if args.name:
            profile.name = args.name

        if args.area:
            profile.area = args.area

        if args.country:
            profile.country = args.country

        self.app.profile = profile

        self.app.save_profile()

    update_profile_parser.set_defaults(func=update_profile)

    def update_clients(self, args: Namespace):
        if args.raw:
            self.app.api.update("clients", raw_sql_stmt=args.raw)

        if args.where and args.values:
            where = parse_conditions(args.where)

            values = parse_conditions_as_dict(args.values)

            self.app.api.update_clients(conditions=where, values=values)

        else:
            self.poutput("Please provide conditions and values")

            return

    update_client_parser.set_defaults(func=update_clients)

    def update_rates(self, args: Namespace):
        if args.raw:
            self.app.api.update_rates(raw_sql_stmt=args.raw)

            return

        if args.where and args.values:
            where = parse_conditions(args.where)

            values = parse_conditions_as_dict(args.values)

            self.app.api.update_rates(conditions=where, values=values)

            return

        else:
            self.poutput("Please provide conditions and values")

            return

    update_rates_parser.set_defaults(func=update_rates)

    def update_job(self, args: Namespace):
        if args.table:
            if not args.client_id:
                self.show_clients(args=None)

                message = [
                    ("class:prompt", "Enter client id:"),
                    ("class:space", "  "),
                ]

                client_id = int(
                    prompt(
                        message,
                        style=style,
                        validator=positive_number_validator,
                    )
                )

                args.client_id = client_id  # Update the original args

            if not args.values:
                self.poutput("Please provide values to be updated.")

                return

            cutoffs = self.app.load_cutoffs(as_str=True, year=args.year)

            cutoffs = [
                ["index" if row == 0 else str(idx)] + row
                for idx, row in enumerate(cutoffs)
            ]

            TranscriptorView().print_table(cutoffs, orientation="horizontal")

            message = [
                ("class:prompt", "select deposit date. Use index number:"),
                ("class:space", "  "),
            ]

            cutoff_idx = prompt(
                message,
                style=style,
                validator=positive_number_validator,
            )

            previous_cutoff, cutoff = self.app.select_cutoff_period(
                int(cutoff_idx)
            )

            raw_cutoff_condition = f""" date_submitted > '{previous_cutoff}'

                  AND date_submitted <= '{cutoff}' AND client_id = {args.client_id}

                  """

            cutoff_condition = [
                f"date_submitted>{previous_cutoff}",
                f"date_submitted<={cutoff}",
                f"client_id={args.client_id}",
            ]

        if args.raw:
            if args.table:
                args.raw = args.raw + f" AND {raw_cutoff_condition}"

            self.app.update_jobs(raw_sql_stmt=args.raw)

        elif args.where and args.values:
            if args.table:
                args.where = args.where + cutoff_condition

            where = parse_conditions(args.where)

            values = parse_conditions_as_dict(args.values)

            if "date_submitted" in values:
                jobs = self.app.api.get_jobs(conditions=where)

                if jobs:
                    for job in jobs:
                        date_received = datetime.strptime(
                            job["date_received"], self.app.config.date_format
                        ).date()

                        date_submitted = datetime.strptime(
                            values["date_submitted"],
                            self.app.config.date_format,
                        ).date()

                        if date_submitted < date_received:
                            self.poutput(
                                "Error: Date submitted cannot be earlier than date received."
                            )

                            return

            self.app.update_jobs(conditions=where, values=values)

            if args.add_jobs and args.client_id:
                extra_numbers = [
                    n.strip() for n in args.add_jobs.split(",") if n.strip()
                ]
                for job_number in extra_numbers:
                    extra_cond = {
                        "job_number": [("=", job_number)],
                        "client_id": [("=", args.client_id)],
                    }
                    if "date_submitted" in values:
                        extra_job_list = self.app.api.get_jobs(
                            conditions=extra_cond
                        )
                        if extra_job_list:
                            for job in extra_job_list:
                                date_received = datetime.strptime(
                                    job["date_received"],
                                    self.app.config.date_format,
                                ).date()
                                date_submitted = datetime.strptime(
                                    values["date_submitted"],
                                    self.app.config.date_format,
                                ).date()
                                if date_submitted < date_received:
                                    self.poutput(
                                        f"Error: date_submitted before date_received for job {job_number}."
                                    )
                                    return
                    self.app.update_jobs(conditions=extra_cond, values=values)

        else:
            if args.table:
                conditions = parse_conditions(cutoff_condition)

                values = parse_conditions_as_dict(args.values)

                self.app.update_jobs(conditions=conditions, values=values)

                if args.add_jobs:
                    extra_numbers = [
                        n.strip()
                        for n in args.add_jobs.split(",")
                        if n.strip()
                    ]
                    for job_number in extra_numbers:
                        extra_cond = {
                            "job_number": [("=", job_number)],
                            "client_id": [("=", args.client_id)],
                        }
                        if "date_submitted" in values:
                            extra_job_list = self.app.api.get_jobs(
                                conditions=extra_cond
                            )
                            if extra_job_list:
                                for job in extra_job_list:
                                    date_received = datetime.strptime(
                                        job["date_received"],
                                        self.app.config.date_format,
                                    ).date()
                                    date_submitted = datetime.strptime(
                                        values["date_submitted"],
                                        self.app.config.date_format,
                                    ).date()
                                    if date_submitted < date_received:
                                        self.poutput(
                                            f"Error: date_submitted before date_received for job {job_number}."
                                        )
                                        return
                        self.app.update_jobs(
                            conditions=extra_cond, values=values
                        )

            else:
                self.poutput("Please provide conditions and values")

            return

    update_jobs_parser.set_defaults(func=update_job)

    @cmd2.with_argparser(update_parser)
    def do_update(self, args: Namespace):
        """

        Update command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("update")

    def delete_clients(self, args: Namespace):
        clients = None

        if not args.where and not args.raw:
            self.poutput("Please provide conditions to delete")

            return

        if args.raw:
            clients = self.app.api.get_clients(raw_sql_stmt=args.raw)

        elif args.where:
            conditions = parse_conditions(args.where)

            clients = self.app.api.get_clients(conditions=conditions)

        if not clients:
            self.poutput("No clients found")

            return

        if args.no_confirm:
            if args.purge:
                self.poutput(
                    "\n** DELETING CLIENTS WILL DELETE ALL CLIENT DATA (NO CONFIRMATION)**\n"
                )

            message = [
                (
                    "class:prompt",
                    "Are you sure you want to delete clients (NO CONFIRMATION)? (y/n):",
                ),
                ("class:space", "  "),
            ]

            to_delete = prompt(
                message,
                style=style,
                validator=yes_no_validator,
            )

            if to_delete.lower().startswith("y"):
                self.app.delete_clients(
                    conditions=conditions,
                    raw_sql_stmt=args.raw,
                    purge=args.purge,
                )

        else:
            for client in clients:
                client_name = client["name"]

                message = [
                    (
                        "class:prompt",
                        f"Are you sure you want to delete {client_name}? (y/n):",
                    ),
                    ("class:space", "  "),
                ]

                to_delete = prompt(
                    message,
                    style=style,
                    validator=yes_no_validator,
                )

                if to_delete.lower().startswith("y"):
                    self.poutput(
                        "\n** DELETING CLIENT WILL DELETE CLIENT'S JOBS AND RATES **\n"
                    )

                    if args.purge:
                        self.poutput(
                            "\n** DELETING CLIENT WILL DELETE ALL CLIENT DATA**\n"
                        )

                    message = [
                        ("class:prompt", f"Type {client_name} to confirm:"),
                        ("class:space", "  "),
                    ]

                    confirm_delete = prompt(message, style=style)

                    if confirm_delete == client_name:
                        self.app.delete_clients(
                            conditions={"name": [("=", client_name)]},
                            purge=args.purge,
                        )

                    else:
                        self.poutput("Operation aborted")

                        return

    delete_client_parser.set_defaults(func=delete_clients)

    def delete_jobs(self, args: Namespace):
        jobs = None
        conditions = None

        if args.raw:
            jobs = self.app.api.get_jobs(raw_sql_stmt=args.raw)

        if not args.where and not args.raw:
            self.poutput("Please provide conditions to delete")

            return

        elif args.where:
            conditions = parse_conditions(args.where)

            jobs = self.app.api.get_jobs(conditions=conditions)

        if not jobs:
            self.poutput("No jobs found")

            return

        if args.no_confirm:
            if args.purge:
                self.poutput(
                    "\n** DELETING CLIENTS WILL DELETE ALL CLIENT DATA (NO CONFIRMATION)**\n"
                )

            message = [
                (
                    "class:prompt",
                    "Are you sure you want to delete jobs (NO CONFIRMATION)? (y/n):",
                ),
                ("class:space", "  "),
            ]

            confirm_delete = prompt(
                message,
                style=style,
                validator=yes_no_validator,
            )

            if confirm_delete.lower().startswith("y"):
                self.app.delete_jobs(
                    conditions=conditions,
                    raw_sql_stmt=args.raw,
                    purge=args.purge,
                )

        else:
            for job in jobs:
                message = [
                    (
                        "class:prompt",
                        f"Are you sure you want to delete {job['job_number']}? (y/n):",
                    ),
                    ("class:space", "  "),
                ]

                confirm_delete = prompt(
                    message,
                    style=style,
                    validator=yes_no_validator,
                )

                if confirm_delete.lower().startswith("y"):
                    self.app.delete_jobs(
                        conditions=conditions,
                        raw_sql_stmt=args.raw,
                        purge=args.purge,
                    )

                else:
                    self.poutput("Operation aborted")

                    return

    delete_jobs_parser.set_defaults(func=delete_jobs)

    @cmd2.with_argparser(delete_parser)
    def do_delete(self, args: Namespace):
        """

        Delete command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("delete")

    def invoice(self, args: Namespace):
        if not any([args.raw, args.table, args.where, args.summary]):
            error = """Conditions must be provided or summary flag must be set.

    Ex. invoice -w 'date_submitted > \"2025-01-01\" -w date_submitted <= \"2025-01-31\"

            """

            self.poutput(error)

            self.do_help("invoice")

            return

        if not args.client_id:
            self.show_clients(args=None)

            message = [
                ("class:prompt", "Enter client id:"),
                ("class:space", "  "),
            ]

            client_id = int(
                prompt(
                    message, style=style, validator=positive_number_validator
                )
            )

            args.client_id = client_id  # Update the original args

        client_name = ""
        if args.summary:
            invoice_jobs_dict = self.app.get_summary_invoice_jobs(
                client_id=args.client_id,
                previous_year_cutoff=args.previous_year_cutoff,
                year=args.year,
            )

            if not invoice_jobs_dict:
                self.poutput("No jobs found for summary.")
                return

            html, client_name = self.app.generate_summary_invoice(
                invoice_jobs_dict
            )
            invoice_jobs = invoice_jobs_dict[client_name]

        if args.table:
            cutoffs = self.app.load_cutoffs(as_str=True, year=args.year)

            cutoffs = [
                ["index" if row == 0 else str(idx)] + row
                for idx, row in enumerate(cutoffs)
            ]

            TranscriptorView().print_table(cutoffs, orientation="horizontal")

            message = [
                ("class:prompt", "select deposit date. Use index number:"),
                ("class:space", "  "),
            ]

            cutoff_idx = prompt(
                message,
                style=style,
                validator=positive_number_validator,
            )

            previous_cutoff, cutoff = self.app.select_cutoff_period(
                int(cutoff_idx)
            )

            raw_cutoff_condition = f""" date_submitted > '{previous_cutoff}'

                  AND date_submitted <= '{cutoff}'

                  """

            cutoff_condition = [
                f"date_submitted>{previous_cutoff}",
                f"date_submitted<={cutoff}",
            ]

        if args.raw:
            if args.table:
                args.raw = args.raw + f" AND {raw_cutoff_condition}"

            invoice_jobs = self.app.get_invoice_jobs(
                client_id=args.client_id,
                raw_sql_stmt=args.raw,
            )

            html, client_name = self.app.generate_invoice(
                invoice_jobs,
                invoice_theme=args.invoice_template,
            )

        elif args.where:
            if args.table:
                args.where = args.where + cutoff_condition

            conditions = parse_conditions(args.where)

            invoice_jobs = self.app.get_invoice_jobs(
                client_id=args.client_id,
                conditions=conditions,
            )

            html, client_name = self.app.generate_invoice(
                invoice_jobs, invoice_theme=args.invoice_template
            )

        else:
            if args.table and not args.summary:
                conditions = parse_conditions(cutoff_condition)

                invoice_jobs = self.app.get_invoice_jobs(
                    client_id=args.client_id,
                    conditions=conditions,
                )

                html, client_name = self.app.generate_invoice(
                    invoice_jobs, invoice_theme=args.invoice_template
                )

        if args.add_jobs and not args.summary and invoice_jobs:
            extra_numbers = [
                n.strip() for n in args.add_jobs.split(",") if n.strip()
            ]
            if extra_numbers:
                extra_jobs = self.app.get_jobs_by_job_numbers(
                    args.client_id, extra_numbers
                )
                if extra_jobs:
                    existing = {j["job_number"] for j in invoice_jobs}
                    for job in extra_jobs:
                        if job["job_number"] not in existing:
                            invoice_jobs.append(job)
                            existing.add(job["job_number"])
                    html, client_name = self.app.generate_invoice(
                        invoice_jobs,
                        invoice_theme=args.invoice_template,
                    )

        if args.print:
            self.app.html_to_pdf(
                html, client_name, summary_invoice=args.summary
            )

        if args.csv:
            self.app.generate_csv_invoice(invoice_jobs, client_name)

        if args.markdown:
            md = self.app.to_md(html)

            TranscriptorView().console.print(md)

        else:
            title = f"Jobs for {client_name}"
            if args.summary:
                title = f"Summary Invoice for {client_name}"

            TranscriptorView().print_table(
                invoice_jobs,
                orientation="horizontal",
                title=title,
                config=self.app.config,
            )

    invoice_parser.set_defaults(func=invoice)

    @cmd2.with_argparser(invoice_parser)
    def do_invoice(self, args: Namespace):
        """

        Invoice command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("invoice")

    def purge(self, args):
        if not any([args.raw, args.where]):
            self.poutput("Please provide conditions to purge")

            return

        if args.raw:
            jobs = self.app.api.get_jobs(raw_sql_stmt=args.raw)

        else:
            conditions = parse_conditions(args.where)

            jobs = self.app.api.get_jobs(conditions=conditions)

        if not jobs:
            self.poutput("No jobs found")

        else:
            message = [
                ("class:prompt", "Are you sure you want to delete (y/n):"),
                ("class:space", "  "),
            ]

            confirm_delete = prompt(
                message,
                style=style,
                validator=yes_no_validator,
            )

            if confirm_delete.lower().startswith("y"):
                self.app.purge_job_files(jobs)

    purge_parser.set_defaults(func=purge)

    @cmd2.with_argparser(purge_parser)
    def do_purge(self, args: Namespace):
        """

        Purge command help

        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("purge")

    @cmd2.with_argparser(open_parser)
    def do_open(self, args: Namespace):
        """Open a job's directory in the system file manager."""
        try:
            job_dir = self.app.get_job_directory(args.job_id)
        except ValueError as e:
            self.poutput(f"Error: {e}")
            return
        open_in_file_manager(job_dir)

    @cmd2.with_argparser(backup_parser)
    def do_backup(self, args: Namespace):
        """Create a backup of the database."""
        try:
            backup_path = self.app.backup.create_backup()
            self.poutput(f"Backup created successfully: {backup_path}")
        except Exception as e:
            self.poutput(f"Error creating backup: {e}")

    @cmd2.with_argparser(restore_parser)
    def do_restore(self, args: Namespace):
        """Restore the database from a backup."""
        backups = self.app.backup.list_backups()
        if not backups:
            self.poutput("No backups found.")
            return

        self.poutput("Available backups:")
        for i, backup in enumerate(backups):
            self.poutput(f"{i + 1}: {backup.name}")

        try:
            selection = int(
                prompt("Enter the number of the backup to restore: ")
            )
            if 1 <= selection <= len(backups):
                backup_to_restore = backups[selection - 1]
                self.app.backup.restore_backup(backup_to_restore)
                self.poutput(
                    f"Database restored from {backup_to_restore.name}"
                )
            else:
                self.poutput("Invalid selection.")
        except ValueError:
            self.poutput("Invalid input. Please enter a number.")
        except Exception as e:
            self.poutput(f"Error restoring backup: {e}")

    def transcribe_submit(self, args: Namespace):
        provider = args.provider
        if provider is None:
            provider = self._prompt_pick_provider()
            if provider is None:
                return

        vocabulary = None
        if args.vocabulary:
            vocabulary = [
                term.strip()
                for term in args.vocabulary.split(",")
                if term.strip()
            ]
        thread = threading.Thread(
            target=self._submit_transcription_worker,
            args=(args.job_id, provider, vocabulary),
            daemon=True,
        )
        thread.start()
        self.poutput(
            f"Submitting job {args.job_id} to {provider} in the background..."
        )

    transcribe_submit_parser.set_defaults(func=transcribe_submit)

    def _submit_transcription_worker(self, job_id, provider, vocabulary):
        try:
            external_id = asyncio.run(
                self.app.submit_transcription(
                    job_id,
                    provider,
                    additional_vocabulary=vocabulary,
                )
            )
            self.poutput(
                f"Submitted job {job_id} to {provider}: {external_id}"
            )
        except (ValueError, FileNotFoundError) as e:
            self.poutput(f"Error: {e}")
        except Exception as e:
            self.poutput(f"Error submitting transcription: {e}")

    def transcribe_status(self, args: Namespace):
        try:
            status = asyncio.run(
                self.app.poll_transcription_status(args.job_id)
            )
        except ValueError as e:
            self.poutput(f"Error: {e}")
            return
        except Exception as e:
            self.poutput(f"Error polling transcription status: {e}")
            return

        if status is None:
            self.poutput(
                f"Job {args.job_id} has no transcription in progress, "
                "or the provider poll failed."
            )
        else:
            self.poutput(f"Job {args.job_id} status: {status}")

    transcribe_status_parser.set_defaults(func=transcribe_status)

    def _load_metadata_arg(
        self, metadata_arg: Optional[str]
    ) -> tuple[Optional[dict], bool]:
        """Load an optional -m JSON file. Returns (metadata, ok)."""
        if not metadata_arg:
            return None, True
        metadata_path = Path(metadata_arg)
        if not metadata_path.exists():
            self.poutput(f"Metadata file not found: {metadata_path}")
            return None, False
        return json.loads(metadata_path.read_text()), True

    def transcribe_check(self, args: Namespace):
        metadata, ok = self._load_metadata_arg(args.metadata)
        if not ok:
            return

        try:
            status = asyncio.run(
                self.app.poll_transcription_status(args.job_id)
            )
        except ValueError as e:
            self.poutput(f"Error: {e}")
            return
        except Exception as e:
            self.poutput(f"Error polling transcription status: {e}")
            return

        if status is None:
            self.poutput(
                f"Job {args.job_id} has no transcription in progress, "
                "or the provider poll failed."
            )
            return

        if str(status).lower() not in TRANSCRIPTION_READY_STATUSES:
            self.poutput(f"Job {args.job_id} status: {status} (not ready)")
            return

        try:
            transcript_path = asyncio.run(
                self.app.fetch_transcript(args.job_id, metadata=metadata)
            )
            self.poutput(f"Transcript saved to {transcript_path}")
        except ValueError as e:
            self.poutput(f"Error: {e}")
        except Exception as e:
            self.poutput(f"Error fetching transcript: {e}")

    transcribe_check_parser.set_defaults(func=transcribe_check)

    def transcribe_fetch(self, args: Namespace):
        metadata, ok = self._load_metadata_arg(args.metadata)
        if not ok:
            return

        try:
            transcript_path = asyncio.run(
                self.app.fetch_transcript(args.job_id, metadata=metadata)
            )
            self.poutput(f"Transcript saved to {transcript_path}")
        except ValueError as e:
            self.poutput(f"Error: {e}")
        except Exception as e:
            self.poutput(f"Error fetching transcript: {e}")

    transcribe_fetch_parser.set_defaults(func=transcribe_fetch)

    @cmd2.with_argparser(transcribe_parser)
    def do_transcribe(self, args: Namespace):
        """Submit, poll, and fetch external transcription for a job.

        Subcommands:
          submit - submit a job's media file for transcription
          status - poll the provider for a job's transcription status
          check  - poll and, if ready, fetch the transcript
          fetch  - fetch the transcript and save it to the job directory
        """

        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("transcribe")

    def config_show(self, args: Namespace):
        config_data = config_manager.config_data
        if not config_data:
            self.poutput(f"No configuration found at {config_manager.config_file}.")
        else:
            self.poutput(f"Current configuration ({config_manager.config_file}):")
            for key, value in config_data.items():
                self.poutput(f"  {key}: {_mask_secret(key, value)}")

        def _shown(name: str) -> str:
            value = os.getenv(name)
            return _mask_secret(name, value) if value else "(not set)"

        ai_key_env = ai_api_key_env_name(config_manager)
        self.poutput("Secrets (environment variables):")
        self.poutput(f"  AI key: {ai_key_env} (ai_api_key_env): {_shown(ai_key_env)}")
        for key in sorted(SECRET_KEYS - {DEFAULT_AI_API_KEY_ENV}):
            self.poutput(f"  {key}: {_shown(key)}")

    config_show_parser.set_defaults(func=config_show)

    def config_set(self, args: Namespace):
        try:
            config_manager.set(args.key, args.value)
        except ValueError as e:
            self.poutput(str(e))
            return
        # Same file as the Transcriptor config: reload so a later
        # save_config() doesn't overwrite this value with stale data.
        if Path(config_manager.config_file) == Path(self.app.CONFIG_FILE):
            self.app.config = self.app._load_config()
        self.poutput(f"Set {args.key} = {_mask_secret(args.key, args.value)}")
        if args.key.lower() == "pdf_backend":
            self._apply_pdf_backend(args.value)

    config_set_parser.set_defaults(func=config_set)

    @cmd2.with_argparser(config_parser)
    def do_config(self, args: Namespace):
        """

        Config command help

        """
        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("config")

    def extract(self, args: Namespace):
        notice, pbs = args.notice, args.pbs
        if notice is None and pbs is None:
            context = self._resolve_job_context(args)
            if context is None:
                return None
            _, job_dir = context

            notice = self._prompt_pick_file_optional(
                job_dir, [".pdf"], "notice"
            )
            pbs = self._prompt_pick_file_optional(
                job_dir,
                [".pdf"],
                "PBS",
                exclude={notice} if notice else set(),
            )
            if notice is None and pbs is None:
                self.poutput("Error: select at least one of notice or PBS.")
                return None

        output_path = args.output or ((pbs or notice).parent / "metadata.json")
        try:
            extractor = MetadataExtractor()
            metadata = extractor.extract_all(notice, pbs)
        except Exception as e:
            self.poutput(f"Error extracting metadata: {e}")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(metadata, indent=4))
        self.poutput(f"Metadata saved to {output_path}")
        return metadata

    extract_parser.set_defaults(func=extract)

    @cmd2.with_argparser(extract_parser)
    def do_extract(self, args: Namespace):
        """

        Extract command help

        """
        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("extract")

    def fill(self, args: Namespace):
        template = args.template
        metadata = None

        if args.metadata:
            if not args.metadata.exists():
                self.poutput(f"Metadata file not found: {args.metadata}")
                return
            metadata = json.loads(args.metadata.read_text())
        elif args.notice or args.pbs:
            metadata = self.extract(
                Namespace(
                    job_id=None, notice=args.notice, pbs=args.pbs, output=None
                )
            )
            if metadata is None:
                return
        else:
            context = self._resolve_job_context(args)
            if context is None:
                return
            _, job_dir = context

            if template is None:
                template = self._prompt_pick_file(
                    job_dir, [".docx"], "template"
                )
                if template is None:
                    return

            metadata_path = job_dir / "metadata.json"
            if metadata_path.exists():
                message = [
                    (
                        "class:prompt",
                        f"Found existing metadata.json in {job_dir}, use it? (y/n):",
                    ),
                    ("class:space", "  "),
                ]
                reuse = prompt(
                    message, style=style, validator=yes_no_validator
                )
                if reuse.lower().startswith("y"):
                    metadata = json.loads(metadata_path.read_text())

            if metadata is None:
                notice = self._prompt_pick_file_optional(
                    job_dir, [".pdf"], "notice"
                )
                pbs = self._prompt_pick_file_optional(
                    job_dir,
                    [".pdf"],
                    "PBS",
                    exclude={notice} if notice else set(),
                )
                if notice is None and pbs is None:
                    self.poutput(
                        "Error: select at least one of notice or PBS."
                    )
                    return
                metadata = self.extract(
                    Namespace(job_id=None, notice=notice, pbs=pbs, output=None)
                )
                if metadata is None:
                    return

        if template is None:
            self.poutput("Error: -t/--template is required")
            return

        try:
            result_path = fill_template(template, metadata, args.output)
        except Exception as e:
            self.poutput(f"Error filling template: {e}")
            return

        self.poutput(f"Filled template saved to {result_path}")

    fill_parser.set_defaults(func=fill)

    @cmd2.with_argparser(fill_parser)
    def do_fill(self, args: Namespace):
        """

        Fill command help

        """
        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("fill")

    def process(self, args: Namespace):
        notice, pbs, audio, template = (
            args.notice,
            args.pbs,
            args.audio,
            args.template,
        )
        job_id = args.job_id

        if (
            (notice is None and pbs is None)
            or audio is None
            or (template is None and args.job_id is not None)
        ):
            context = self._resolve_job_context(args)
            if context is None:
                return
            job, job_dir = context
            job_id = job["id"]

            if audio is None:
                audio = Path(job["job_path"])
                if not audio.exists():
                    self.poutput(f"Error: Job file not found: {audio}")
                    return

            if notice is None and pbs is None:
                notice = self._prompt_pick_file_optional(
                    job_dir, [".pdf"], "notice"
                )
                pbs = self._prompt_pick_file_optional(
                    job_dir,
                    [".pdf"],
                    "PBS",
                    exclude={notice} if notice else set(),
                )

            if template is None:
                template = self._prompt_pick_file(
                    job_dir, [".docx"], "template"
                )
                if template is None:
                    return

        if notice is None and pbs is None:
            self.poutput("Error: -n/--notice and/or -p/--pbs is required")
            return
        if template is None:
            self.poutput("Error: -t/--template is required")
            return

        output_dir = (pbs or notice).parent
        thread = threading.Thread(
            target=self._process_worker,
            args=(
                audio,
                notice,
                pbs,
                template,
                output_dir,
                args.provider,
                args.wait,
                job_id,
            ),
            daemon=True,
        )
        thread.start()
        self.poutput(f"Processing {audio.name} in the background...")

    process_parser.set_defaults(func=process)

    def _process_worker(
        self,
        audio: Path,
        notice: Path,
        pbs: Optional[Path],
        template: Path,
        output_dir: Path,
        provider: str,
        wait: bool,
        job_id: Optional[int],
    ) -> None:
        try:
            extractor = MetadataExtractor()
            metadata = extractor.extract_all(notice, pbs)
        except Exception as e:
            self.poutput(f"Error extracting metadata: {e}")
            return

        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=4))
        self.poutput(f"Metadata saved to {metadata_path}")

        try:
            filled_path = fill_template(
                template,
                metadata,
                output_dir / f"{template.stem}_filled.docx",
            )
            self.poutput(f"Filled template saved to {filled_path}")
        except Exception as e:
            self.poutput(f"Error filling template: {e}")
            return

        vocabulary = process_metadata_to_vocabulary(metadata)
        output_txt = output_dir / f"{audio.stem}.txt"

        try:
            asyncio.run(
                self._process_transcribe(
                    audio,
                    provider,
                    vocabulary,
                    output_txt,
                    wait,
                    job_id=job_id,
                    metadata=metadata,
                )
            )
        except Exception as e:
            self.poutput(f"Error during transcription: {e}")

    async def _process_transcribe(
        self,
        audio_path: Path,
        provider: str,
        vocabulary: list,
        output_path: Path,
        wait: bool,
        job_id: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        if job_id is not None:
            external_id = await self.app.submit_transcription(
                job_id,
                provider,
                additional_vocabulary=vocabulary,
                file_path=audio_path,
            )
            self.poutput(f"Submitted {audio_path} to {provider}: {external_id}")
            if wait:
                await self._wait_for_job_transcription(job_id, metadata)
            return

        service = get_service(provider)
        try:
            external_id = await service.submit_job(
                audio_path, additional_vocabulary=vocabulary
            )
            self.poutput(f"Submitted {audio_path} to {provider}: {external_id}")

            if not wait:
                return

            while True:
                await asyncio.sleep(5)
                status_info = await service.get_job_status(external_id)
                if status_info is None:
                    self.poutput("Failed to retrieve job status.")
                    return
                status = str(status_info.get("status", "")).lower()
                if status in TRANSCRIPTION_READY_STATUSES:
                    transcript = await service.get_transcript(external_id)
                    output_path.write_text(transcript, encoding="utf-8")
                    self.poutput(f"Transcript saved to {output_path}")
                    return
                elif status in ("failed", "error"):
                    self.poutput("Transcription failed.")
                    return
                else:
                    self.poutput(f"Job status: {status}. Waiting...")
        finally:
            await service.close()

    async def _wait_for_job_transcription(
        self, job_id: int, metadata: Optional[dict] = None
    ) -> None:
        while True:
            await asyncio.sleep(5)
            status = await self.app.poll_transcription_status(job_id)
            if status is None:
                self.poutput("Failed to retrieve job status.")
                return
            lowered = str(status).lower()
            if lowered in TRANSCRIPTION_READY_STATUSES:
                transcript_path = await self.app.fetch_transcript(
                    job_id, metadata=metadata
                )
                self.poutput(f"Transcript saved to {transcript_path}")
                return
            if lowered in ("failed", "error"):
                self.poutput("Transcription failed.")
                return
            self.poutput(f"Job status: {status}. Waiting...")

    @cmd2.with_argparser(process_parser)
    def do_process(self, args: Namespace):
        """

        Process command help

        """
        if hasattr(args, "func"):
            args.func(self, args)

        else:
            self.do_help("process")

    def _prompt_pick_file(
        self,
        directory: Path,
        extensions: list,
        label: str,
        exclude: set = frozenset(),
    ) -> Optional[Path]:
        candidates = list_candidate_files(directory, extensions, exclude=exclude)
        if not candidates:
            self.poutput(f"No {label} candidates found in {directory}")
            return None

        self.poutput(f"Select {label}:")
        for i, path in enumerate(candidates):
            self.poutput(f"{i + 1}: {path.name}")

        try:
            selection = int(prompt(f"Enter the number of the {label}: "))
        except ValueError:
            self.poutput("Invalid input. Please enter a number.")
            return None

        if 1 <= selection <= len(candidates):
            return candidates[selection - 1]

        self.poutput("Invalid selection.")
        return None

    def _prompt_pick_file_optional(
        self,
        directory: Path,
        extensions: list,
        label: str,
        exclude: set = frozenset(),
    ) -> Optional[Path]:
        """Like _prompt_pick_file, but lets the user skip (0) since this
        file is one of an and/or pair -- neither notice nor PBS alone is
        mandatory, only at least one of the two."""
        candidates = list_candidate_files(directory, extensions, exclude=exclude)
        if not candidates:
            self.poutput(f"No {label} candidates found in {directory}")
            return None

        self.poutput(f"Select {label} (0 to skip):")
        self.poutput("0: Skip")
        for i, path in enumerate(candidates):
            self.poutput(f"{i + 1}: {path.name}")

        try:
            selection = int(prompt(f"Enter the number of the {label}: "))
        except ValueError:
            self.poutput("Invalid input. Please enter a number.")
            return None

        if selection == 0:
            return None
        if 1 <= selection <= len(candidates):
            return candidates[selection - 1]

        self.poutput("Invalid selection.")
        return None

    def _prompt_pick_job_id(self) -> Optional[int]:
        try:
            job_id = int(prompt("Enter job ID: "))
        except ValueError:
            self.poutput("Invalid input. Please enter a number.")
            return None

        try:
            self.app.get_job_directory(job_id)
        except ValueError as e:
            self.poutput(f"Error: {e}")
            return None

        return job_id

    def _resolve_job_context(self, args: Namespace):
        job_id = getattr(args, "job_id", None)
        if job_id is None:
            job_id = self._prompt_pick_job_id()
            if job_id is None:
                return None

        jobs = self.app.api.get_jobs(conditions={"id": [("=", job_id)]})
        if not jobs:
            self.poutput(f"Error: No job found with id {job_id}")
            return None

        job = jobs[0]
        job_dir = Path(job["job_path"]).parent
        return job, job_dir

    def _prompt_pick_provider(self) -> Optional[str]:
        self.poutput("Select provider:")
        for i, provider in enumerate(TRANSCRIPTION_PROVIDERS):
            self.poutput(f"{i + 1}: {provider}")

        try:
            selection = int(prompt("Enter the number of the provider: "))
        except ValueError:
            self.poutput("Invalid input. Please enter a number.")
            return None

        if 1 <= selection <= len(TRANSCRIPTION_PROVIDERS):
            return TRANSCRIPTION_PROVIDERS[selection - 1]

        self.poutput("Invalid selection.")
        return None


def main(argv=None):
    c = TranscriptorCMD()

    if argv:
        alias_script = c.app.CONFIG_DIR.joinpath(".cmd2rc")
        if alias_script.exists():
            with open(os.devnull, "w") as devnull:
                _stdout = c.stdout
                c.stdout = devnull
                try:
                    c.do_run_script(str(alias_script))
                finally:
                    c.stdout = _stdout

        command = " ".join(argv)
        c.onecmd_plus_hooks(command)
        return

    try:
        sys.exit(c.cmdloop())
    except (KeyboardInterrupt, EOFError):
        c.poutput("\n** Exiting program, bye **\n")
        return True


if __name__ == "__main__":
    main()
