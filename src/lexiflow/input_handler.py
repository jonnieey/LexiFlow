import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from prompt_toolkit import prompt
from prompt_toolkit.styles import Style

from lexiflow.utils import (
    date_validator,
    extract_date_due,
    extract_job_number,
    file_validator,
    get_media_duration,
    job_type_validator,
    month_day_to_date,
    positive_number_validator,
    template_validator,
    yes_no_validator,
)

style = Style.from_dict(
    {
        "": "#FFA500 bg:#2A2B3C",
        "space": "bg:#2A2B3C",
        "prompt": "#8BE9FD bg:#2A2B3C",
    }
)


class CLIInputHandler:
    def __init__(self, app_config: Any, show_clients_func: Callable):
        self.app_config = app_config
        self.show_clients_func = show_clients_func

    def get_job_info(self, args: Any, job_file: Path) -> Dict[str, Any]:
        tmp_args = copy.copy(args)

        client_id = tmp_args.client_id
        job_number = tmp_args.job_number
        date_received = tmp_args.date_received
        date_due = tmp_args.date_due
        date_format = self.app_config.date_format

        if not client_id:
            self.show_clients_func(args=None)
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
            tmp_args.client_id = client_id

        if not job_number:
            message = [
                ("class:prompt", "Enter job number:"),
                ("class:space", "  "),
            ]
            job_number = extract_job_number(str(job_file)) or prompt(
                message, style=style
            )
            tmp_args.job_number = job_number

        if not date_received:
            message = [
                ("class:prompt", f"Enter date received [{date_format}]:"),
                ("class:space", "  "),
            ]
            date_received = prompt(
                message,
                style=style,
                default=str(datetime.now().strftime(date_format)),
                validator=date_validator,
            )
            tmp_args.date_received = date_received
        if not date_due:
            message = [
                ("class:prompt", f"Enter date due [{date_format}]:"),
                ("class:space", "  "),
            ]
            date_due = prompt(
                message,
                style=style,
                default=month_day_to_date(extract_date_due(str(job_file))),
                validator=date_validator,
            )
            tmp_args.date_due = date_due

        return {
            "client_id": client_id,
            "job_number": job_number,
            "date_received": date_received,
            "date_due": date_due,
        }

    def get_task_info(
        self, args: Any, task_file: Path
    ) -> Optional[Dict[str, Any]]:
        tmp_args = copy.copy(args)

        work_on_file = tmp_args.work_on_file
        job_type = tmp_args.job_type
        total_quantity = None
        quantity = tmp_args.quantity
        job_template = tmp_args.job_template
        note = tmp_args.note

        if not work_on_file:
            message = [
                (
                    "class:prompt",
                    f"Enter work on file [ ...{'/'.join(task_file.parts[-2:])}]:",
                ),
                ("class:space", "  "),
            ]
            work_on_file = prompt(
                message,
                style=style,
                validator=yes_no_validator,
            )
            tmp_args.work_on_file = work_on_file
        if not tmp_args.work_on_file.strip().lower().startswith("y"):
            return None

        if not job_type:
            message = [
                ("class:prompt", "Enter job type:"),
                ("class:space", "  "),
            ]
            job_type = prompt(
                message, style=style, validator=job_type_validator
            )
            tmp_args.job_type = job_type
        total_quantity = get_media_duration(task_file)
        if not quantity:
            message = [
                ("class:prompt", "Enter quantity:"),
                ("class:space", "  "),
            ]
            quantity = prompt(
                message, style=style, default=str(total_quantity)
            )
            tmp_args.quantity = quantity

        if not job_template:
            message = [
                ("class:prompt", "Enter job template:"),
                ("class:space", "  "),
            ]
            job_template = prompt(
                message, style=style, validator=template_validator
            )
            tmp_args.job_template = job_template
        if not note:
            message = [
                ("class:prompt", "Enter note:"),
                ("class:space", "  "),
            ]
            note = prompt(message, style=style, default="")
            tmp_args.notes = note

        return {
            "work_on_file": work_on_file,
            "job_type": job_type.lower(),
            "total_quantity": total_quantity,
            "quantity": quantity,
            "job_template": job_template,
            "note": note,
        }

    def get_client_info(self, args: Any) -> Dict[str, str]:
        name = args.name
        email = args.email

        if not name:
            message = [
                ("class:prompt", "Enter client name:"),
                ("class:space", "  "),
            ]
            name = prompt(message, style=style)

        if not email:
            message = [
                ("class:prompt", "Enter client email:"),
                ("class:space", "  "),
            ]
            email = prompt(message, style=style)

        return {"name": name, "email": email}

    def get_cutoff_file(self, args: Any) -> Path:
        if args.file:
            return Path(args.file)

        message = [
            ("class:prompt", "Enter cutoff file path:"),
            ("class:space", "  "),
        ]
        file_path_str = prompt(message, style=style, validator=file_validator)
        return Path(file_path_str)

    def get_job_file_path(self, args: Any) -> Path:
        if args.file:
            return Path(args.file)

        message = [
            ("class:prompt", "Enter job file path:"),
            ("class:space", "  "),
        ]
        file_path_str = prompt(message, style=style, validator=file_validator)
        return Path(file_path_str)
