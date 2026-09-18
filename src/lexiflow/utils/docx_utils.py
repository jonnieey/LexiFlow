from datetime import date
from typing import List, Tuple, Union

import docx  # type: ignore

from .date_utils import to_date_object


def extract_table_data_from_docx(docx_path: str) -> List[List[str]]:
    try:
        docx_file = docx.Document(docx_path)
    except ImportError:
        print("docx library not installed")
        return []
    except docx.opc.exceptions.PackageNotFoundError:
        print("Docx file not found")
        return []

    table_data: List[List[str]] = []
    for table in docx_file.tables:
        table_data.extend(
            [cell.text for cell in row.cells] for row in table.rows
        )
    return table_data


def generate_cutoff_list_from_docx(
    docx_path: str, date_fmt: str = ""
) -> List[Union[Tuple[date, ...], List[str]]]:
    date_fmt = date_fmt or "%m/%d/%Y"
    cutoff_list = extract_table_data_from_docx(docx_path)

    header, *rows = cutoff_list
    cutoffs = [header] + [to_date_object(row, date_fmt) for row in rows]
    return cutoffs
