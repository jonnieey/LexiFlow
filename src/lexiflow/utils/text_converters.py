import re

job_number_pattern = re.compile(r"\b(\d{6,8})\b")


def extract_job_number(file: str) -> str:
    """
    Get job number from path-like string.

    Arguments:
        file: Path-like string

    Returns:
        String (6-8 digit number string) ex. 534223.
    """
    job_number_matches = job_number_pattern.search(file)

    return job_number_matches.group(1) if job_number_matches else ""


def convert_case(string: str, from_: str, to_: str) -> str:
    """
    Convert string case replacing from_ to to_.

    Arguments:
        string: String to convert case.
        from_: string to replace.
        to_: string to replace to.

    Returns:
        Case converted string
    """
    pattern = re.compile(from_, re.IGNORECASE)
    return pattern.sub(to_, string)


def sc(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    return convert_case(s, r"[ -]", "_")


def nc(s: str) -> str:
    return convert_case(s, r"[-_]", " ")


def kc(s):
    s = re.sub(r'[<>:"/\\|?*]', "", s)
    return convert_case(s, r"[ _]", "-")


def tc(s: str) -> str:
    return nc(s).title()
