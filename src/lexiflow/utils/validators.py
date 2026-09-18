import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from prompt_toolkit.validation import Validator


def is_file(text: str) -> bool:
    path = Path(text.strip("'").strip('"'))
    return path.is_file()


def is_positive_number(text: str) -> bool:
    try:
        return Decimal(text) > 0
    except (InvalidOperation, TypeError):
        return False


def is_valid_date(text: str) -> bool:
    return bool(re.match(r"([0-9]{2,4}[./-]){2}[0-9]{2,4}", text))


def is_valid_yes_no(text: str) -> bool:
    return bool(re.match(r"(?i)^[YyNn](?:es|o)?$", text))


def is_valid_job_type(text: str) -> bool:
    return bool(re.match(r"(?i)^(?:Normal|Interpreted|Expedite)$", text))


def get_template_mapping():
    template_mapping_skeleton = {
        "zd": "Zoom Deposition Block Files.docx",
        "nh": "Hearing Block Files.docx",
        "zeo": "Zoom Examination Under Oath Block Files.docx",
        "zh": "Zoom Hearing Block Files.docx",
        "zus": "Zoom Unsworn Statement Block Files.docx",
        "zwc": "Zoom Workers Comp Deposition Block Files.docx",
        "tt": "Tape Transcript.docx",
        "me": "Compulsory Medical Exam Template.docx",
        "zdi": "Zoom Deposition Block File with Interpreter.docx",
        "od": "Overflow Deposition Block Files.docx",
        "oh": "Overflow Hearing Block Files.docx",
    }
    short_names = [f"{key}a" for key in template_mapping_skeleton.keys()]
    auto_templates_names = [
        f"{Path(value).stem}-auto.docx"
        for value in template_mapping_skeleton.values()
    ]
    auto_templates_mapping = dict(zip(short_names, auto_templates_names))
    return {**template_mapping_skeleton, **auto_templates_mapping}


template_mapping = get_template_mapping()


def is_valid_template(text: str):
    if text.lower() in template_mapping:
        return True
    else:
        return False


def ValidatorWrapper(
    func: Callable, error_message: str, mve: bool = True
) -> Validator:
    return Validator.from_callable(
        func, error_message, move_cursor_to_end=mve
    )


file_validator = ValidatorWrapper(is_file, "File does not exist")
positive_number_validator = ValidatorWrapper(
    is_positive_number, "Must be greater than zero"
)
date_validator = ValidatorWrapper(is_valid_date, "Invalid date")
yes_no_validator = ValidatorWrapper(
    is_valid_yes_no, "Invalid input, expects [Y, Yes, N, No]"
)
job_type_validator = ValidatorWrapper(
    is_valid_job_type,
    "Invalid job type, expects [Normal Interpreted Expedite]",
)
template_validator = ValidatorWrapper(
    is_valid_template,
    f"Invalid template name, expects {' '.join(list(template_mapping.keys()))}",
)
