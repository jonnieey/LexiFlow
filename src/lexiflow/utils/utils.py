import re
from pathlib import Path

from .currency import (
    convert,
    currency_symbol,
    fetch_rate,
    format_money,
    get_rate,
)
from .date_utils import (
    date_to_str,
    extract_date_due,
    month_day_to_date,
    str_to_date,
    to_date_object,
)
from .docx_utils import extract_table_data_from_docx
from .filesystem import get_media_files, mkdirp, next_non_existent_file, touch
from .invoice_utils import (
    html_to_md,
    htmlstr_to_pdf,
    invoice_template_themes,
    render_invoice,
    render_summary_invoice,
    write_pdf,
)
from .media_utils import get_media_duration, round_up, seconds_to_minutes
from .sql_parsers import (
    parse_conditions,
    parse_conditions_as_dict,
    parse_sql_update_query,
)
from .text_converters import convert_case, extract_job_number, kc, nc, sc, tc
from .validators import (
    date_validator,
    file_validator,
    job_type_validator,
    positive_number_validator,
)
from .validators import template_mapping as TEMPLATE_MAPPING
from .validators import template_validator, yes_no_validator
from .vocabulary import (
    clean_vocabulary,
    estimate_token_count,
    filter_metadata_for_llm,
    format_metadata_for_prompt,
    process_metadata_to_vocabulary,
    tokenize_metadata_value,
)


def get_version():
    try:
        init_file_path = Path(__file__).parent.parent / "__about__.py"
        with open(init_file_path, "r") as fd:
            init_content = fd.read()

            version_match = re.search(
                r"^__version__\s*=\s*['\"]([^'\"]*)['\"]",
                init_content,
                re.MULTILINE,
            )

            if version_match:
                return version_match.group(1)
            else:
                raise ValueError("Could not determine version")
    except FileNotFoundError:
        raise FileNotFoundError(f"__init__.py not found at {init_file_path}")
    except ValueError as e:
        raise ValueError(f"Error determining version: {e}")
