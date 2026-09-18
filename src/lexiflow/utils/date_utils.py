import re
from datetime import date, datetime
from typing import List, Tuple


def str_to_date(date_string: str, date_fmt: str) -> datetime:
    """
    Convert a date string to a datetime object.

    Arguments:
        date_string (str): A string in the format '%m.%d'.
        date_fmt (str): The desired date format string.

    Returns:
        A datetime object representing the date in the given format,
    """
    if isinstance(date_string, (datetime, date)):
        return date_string
    return datetime.strptime(date_string, date_fmt)


def date_to_str(date_obj: datetime, date_fmt: str) -> str:
    """
    Convert a datetime object to a date string.

    Arguments:
        date_obj: A datetime object.
        date_fmt: Date format string.

    Retuns:
        A string representing the date in the given format,
    """
    return date_obj.strftime(date_fmt)


def to_date_object(iterable: List[str], date_fmt: str) -> Tuple[date, ...]:
    return tuple(
        str_to_date(date_str.strip(), date_fmt).date()
        for date_str in iterable
    )


def extract_date_due(file: str) -> str:
    date_due_pattern = re.compile(
        r"(?i)(DUE|BACK)[_/\s-](\d{1,2}[-./]\d{1,2})"
    )
    date_due_matches = date_due_pattern.search(file)
    return date_due_matches[2] if date_due_matches else ""


def month_day_to_date(
    date_str: str, date_fmt: str = "%Y-%m-%d", year: str = ""
) -> str:
    """
    Convert a month.day ('%m.%d') string to a full date string.

    Args:
        date_str (str): A string in the format '%m.%d'.
        date_fmt (str): The desired date format string.
        year (str): The year to append to the date string.

    Returns:
        A string representing the date in the given format,
        or an empty string if the input date_str is invalid.
    """
    try:
        if not year:
            current_year = f"{datetime.now().year}"
            year = current_year
        date_str = f"{date_str}.{year}"
        date_obj = datetime.strptime(date_str, "%m.%d.%Y")
        return date_obj.strftime(date_fmt)
    except ValueError:
        return ""
