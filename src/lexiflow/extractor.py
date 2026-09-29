import json
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dateutil import parser
from openai import OpenAI, OpenAIError
from pdfplumber import open as pdfopen
from pdfplumber.utils.pdfinternals import resolve_and_decode, resolve

from docx import Document
from docx.shared import Pt

from .config import settings
from .prompts import NOTICE_METADATA_SYSTEM_PROMPT, PBS_METADATA_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def get_ordinal_suffix(num):
    return f"{num}{'th' if 11 <= num % 100 <= 13 else {1:'st',2:'nd',3:'rd'}.get(num % 10,'th')}"


class MetadataExtractor:
    """
    Professional-grade metadata extractor for court notice PDFs (AI-parsed) and PBS AcroForm PDFs.

    Features:
    - Comprehensive error handling and logging
    - Robust PDF form parsing with recursive AcroForm support
    - Fallback attorney extraction for varying PBS form layouts
    - Automatic case-variant generation for template compatibility
    - Input validation and graceful degradation
    """

    def __init__(self) -> None:
        self.form_map: Dict[str, Any] = {}
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                f"{settings.AI_API_KEY_ENV} is not set (API key env var "
                "chosen by ai_api_key_env). Export it in your shell."
            )
        self.client: OpenAI = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.BASE_URL,
            timeout=60.0,
            max_retries=2,
        )
        self.logger = logging.getLogger(f"{__name__}.MetadataExtractor")

    def extract_all(
        self,
        notice_path: Optional[Path] = None,
        pbs_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Extract and merge metadata from notice and/or PBS PDFs --
        either one alone is sufficient."""
        if notice_path is None and pbs_path is None:
            raise ValueError(
                "At least one of notice_path or pbs_path is required."
            )
        notice_data = (
            self.extract_notice(notice_path) if notice_path is not None else {}
        )
        pbs_data = self.extract_pbs(pbs_path) if pbs_path is not None else {}
        data = {**notice_data, **pbs_data}
        return dict(sorted(data.items()))

    def map_to_template(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Convert flat metadata into template placeholders [KEY]."""
        return {f"[{key}]": value for key, value in metadata.items()} or {}

    def extract_notice(
        self, path: Path, pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Extract structured metadata from notice PDF via AI."""
        if pages is None:
            pages = [0, 1]

        try:
            if not path.exists():
                raise FileNotFoundError(f"Notice PDF not found: {path}")

            notice_text = self._extract_pdf_text(path=path, pages=pages)
            if not notice_text.strip():
                self.logger.warning(f"No text extracted from notice: {path}")

            ai_response = self._ai_notice_parse(notice_text)
            return dict(ai_response) if ai_response else {}

        except Exception as e:
            self.logger.error(f"Failed to extract notice metadata from {path}: {e}")
            return {}

    def _extract_pdf_text(self, path: Path, pages: List[int]) -> str:
        """Safely extract text from specific PDF pages."""
        try:
            all_text: List[str] = []
            with pdfopen(path) as pdf:
                target_pages = (
                    [pdf.pages[i] for i in pages if i < len(pdf.pages)]
                    if pages
                    else pdf.pages
                )
                for page in target_pages:
                    text = page.extract_text() or ""
                    all_text.append(text)
            return "\n".join(all_text)
        except Exception as e:
            self.logger.error(f"PDF text extraction failed for {path}: {e}")
            return ""

    def _ai_notice_parse(self, notice_text: str) -> Dict[str, Any]:
        """Call OpenAI to parse notice text into JSON metadata."""
        try:
            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[
                    {"role": "system", "content": NOTICE_METADATA_SYSTEM_PROMPT},
                    {"role": "user", "content": notice_text},
                ],
                response_format={"type": "json_object"},
            )

            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty or invalid response from AI model")

            content = response.choices[0].message.content
            return json.loads(content)

        except (OpenAIError, json.JSONDecodeError, IndexError, ValueError) as e:
            self.logger.error(f"AI parsing error: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error in AI notice parsing: {e}")
            return {}

    def extract_pbs(self, path: Path) -> Dict[str, Any]:
        """Extract PBS metadata: try AI on AcroForm dict, fallback to rule‑based."""
        # First, extract the raw AcroForm field dictionary
        raw_fields = self._extract_raw_acroform_fields(path)
        if not raw_fields:
            self.logger.warning(
                "No AcroForm fields extracted, falling back to rule‑based"
            )
            return self._extract_pbs_rule_based(path)

        # Try AI parsing on the raw field dict
        try:
            ai_result = self._ai_parse_acroform_fields(raw_fields)
            if ai_result and self._validate_pbs_ai_output(ai_result):
                self.logger.info(
                    "Successfully extracted PBS metadata via AI on AcroForm"
                )
                # Flatten the attorneys list into template keys
                ai_result = self._flatten_ai_attorneys(ai_result)
                return self._apply_case_variants(ai_result)
        except Exception as e:
            self.logger.warning(f"AI parsing on AcroForm failed: {e}")

        # Fallback to existing rule‑based processing
        self.logger.info("Falling back to rule‑based PBS extraction")
        return self._extract_pbs_rule_based(path)

    def _extract_raw_acroform_fields(self, path: Path) -> Dict[str, Any]:
        """Extract all AcroForm fields into a flat dictionary (same as before)."""
        self.form_map = {}
        try:
            with pdfopen(path) as pdf:
                if "AcroForm" not in pdf.doc.catalog:
                    raise ValueError("No AcroForm found")
                acroform = resolve(pdf.doc.catalog["AcroForm"])
                fields = resolve(acroform["Fields"])
                for field in fields:
                    self.parse_field_helper(field)
            # Return a copy of the raw map (without any cleaning)
            return dict(self.form_map)
        except Exception as e:
            self.logger.error(f"Failed to extract AcroForm fields from {path}: {e}")
            return {}

    def _ai_parse_acroform_fields(self, raw_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Send the raw AcroForm field dict to AI for structured extraction."""
        # Convert the dict to a readable JSON string (limit size)
        fields_json = json.dumps(raw_fields, indent=2, default=str)[:12000]
        try:
            response = self.client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[
                    {"role": "system", "content": PBS_METADATA_SYSTEM_PROMPT},
                    {"role": "user", "content": fields_json},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            self.logger.error(f"AI AcroForm parsing error: {e}")
            return {}

    def _validate_pbs_ai_output(self, data: Dict[str, Any]) -> bool:
        """Basic validation – at least witness name or case caption present."""
        return bool(data.get("WITNESS_NAME") or data.get("CASE_CAPTION"))

    def _flatten_ai_attorneys(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert AI's 'attorneys' list into flat template keys."""
        attorneys = data.pop("attorneys", [])
        if not attorneys:
            return data

        results = {}
        attorney_blocks = []
        for idx, atty in enumerate(attorneys[:4], start=1):
            name = atty.get("name", "").strip()
            if not name:
                continue
            cleaned_name = self._clean_attorney_name(name)
            results[f"TAKING_ATTORNEY{idx}"] = cleaned_name
            results[f"TAKING_ATTORNEY{idx}_LAST_NAME"] = self._get_attorney_last_name(
                name
            )

            firm = atty.get("firm", "").strip()
            addr = atty.get("address", "").strip()
            phone = atty.get("phone", "").strip()
            email = atty.get("email", "").strip()
            block_lines = [
                f"\t{name.upper()}",
                f"\t{firm.upper()}",
                f"\t{addr.upper()}",
                f"\t{phone}",
                f"\t{email.upper()}",
            ]
            block = "\n".join(block_lines)
            results[f"ATTORNEY_{idx}_BLOCK"] = block
            attorney_blocks.append(block)

        if attorney_blocks:
            results["ATTORNIES_BLOCK"] = "\n\n".join(attorney_blocks)

        data.update(results)
        return data

    def _extract_pbs_rule_based(self, path: Path) -> Dict[str, Any]:
        """Original rule‑based extraction (renamed from old extract_pbs)."""
        self.form_map = {}
        try:
            with pdfopen(path) as pdf:
                if "AcroForm" not in pdf.doc.catalog:
                    raise ValueError("PDF does not contain AcroForm data.")
                acroform = resolve(pdf.doc.catalog["AcroForm"])
                fields = resolve(acroform["Fields"])
                for field in fields:
                    self.parse_field_helper(field)
            extracted = self._process_raw_pbs_map()
            return self._apply_case_variants(extracted)
        except Exception as e:
            self.logger.error(f"Rule‑based PBS extraction failed from {path}: {e}")
            return {}

    def parse_field_helper(self, field: Any, prefix: Optional[str] = None) -> None:
        """Recursively parse AcroForm fields (handles nested Kids)."""
        try:
            resolved_field = field.resolve()
            field_name = ".".join(
                filter(
                    None,
                    [prefix, resolve_and_decode(resolved_field.get("T"))],
                )
            )

            if "Kids" in resolved_field:
                for kid in resolved_field["Kids"]:
                    self.parse_field_helper(kid, prefix=field_name)

            if "T" in resolved_field or "TU" in resolved_field:
                field_value = (
                    resolve_and_decode(resolved_field["V"])
                    if "V" in resolved_field
                    else None
                )
                self.form_map[field_name] = field_value

        except Exception as e:
            self.logger.warning(f"Skipped problematic field: {e}")

    def _process_raw_pbs_map(self) -> Dict[str, Any]:
        """Clean raw form data and map to structured keys."""
        # Clean form fields (remove empty/off values, normalize keys)
        cleaned_m: Dict[str, Any] = {}
        for k, v in self.form_map.items():
            if v is None:
                continue
            k_clean = k.replace(":", "").replace("\r", "")
            if isinstance(v, str):
                v_clean = v.strip()
                if not v_clean or v_clean.lower() == "off":
                    continue
                cleaned_m[k_clean] = v_clean
            else:
                cleaned_m[k_clean] = v

        extracted: Dict[str, Any] = {}

        # 1. Witness
        witness_name = cleaned_m.get("Witness 1", cleaned_m.get("name 2", ""))
        extracted["WITNESS_NAME"] = witness_name
        extracted["WITNESS_LAST_NAME"] = (
            witness_name.split()[-1] if witness_name else ""
        )

        # 2. Date (robust parsing)
        raw_date = cleaned_m.get("Job Date")
        extracted["RAW_DATE"] = raw_date
        try:
            if raw_date:
                dt = parser.parse(raw_date)
                extracted["DATE"] = dt.strftime("%B %d, %Y")
                day = dt.strftime("%d")
                extracted["DAY"] = day
                extracted["ORDINAL_DAY"] = get_ordinal_suffix(int(day))
                extracted["MONTH"] = dt.strftime("%B")
                extracted["YEAR"] = dt.strftime("%Y")
            else:
                extracted["DATE"] = ""
        except Exception as e:
            self.logger.warning(f"Date parse failed for '{raw_date}': {e}")
            extracted["DATE"] = raw_date or ""

        # 3. Time (AM/PM checkbox logic)
        start_time = cleaned_m.get("Start Time", cleaned_m.get("Start 2", ""))
        start_period = (
            "A.M."
            if cleaned_m.get("AM", cleaned_m.get("Start AM 2", "")) in ["On", "YES"]
            else "P.M."
        )
        extracted["START_TIME"] = f"{start_time} {start_period}".strip()

        end_time = cleaned_m.get("End Time", cleaned_m.get("End time 2", ""))
        end_period = (
            "A.M."
            if cleaned_m.get("AM_2", cleaned_m.get("End PM 2", "")) in ["On", "YES"]
            else "P.M."
        )
        extracted["END_TIME"] = f"{end_time} {end_period}".strip()

        extracted["COURT_REPORTER_NAME"] = cleaned_m.get("Court Reporter", "")
        extracted["JOB_NUMBER"] = cleaned_m.get("Job Number", "")
        extracted["CASE_CAPTION"] = cleaned_m.get("Case Caption", "").strip()

        # 4. Status checkboxes
        video_val = cleaned_m.get("Yes", cleaned_m.get("Video recorded yes 2", ""))
        extracted["VIDEO_RECORDED"] = "Yes" if video_val in ["On", "Yes"] else "No"

        waiver = cleaned_m.get("Combo Box7", cleaned_m.get("ReadWaiveBustCNA 2", ""))
        extracted["WAIVER_OF_READING"] = (
            "waived" if "waive" in waiver.lower() else "reserved"
        )

        # 5. Attorneys (specific fields first, then general fallback)
        extracted.update(self._format_pbs_attorney_appearances(cleaned_m))

        return extracted

    def extract_lawyers(
        self,
        data: Dict[str, Any],
        lawyer_indicator_keys: Optional[List[str]] = None,
        fields_to_extract: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Group and filter lawyer data from numbered form fields (e.g. "Attorney 3").
        """
        if lawyer_indicator_keys is None:
            lawyer_indicator_keys = ["Attorney"]

        groups: Dict[int, Dict[str, Any]] = {}
        for key, value in data.items():
            parts = key.split()
            if parts and parts[-1].isdigit():
                num = int(parts[-1])
                base = " ".join(parts[:-1])
                groups.setdefault(num, {})[base] = value

        # Sort by field number for deterministic order
        lawyer_groups = sorted(groups.items())

        lawyers: List[Dict[str, Any]] = []
        for _, fields in lawyer_groups:
            is_lawyer = any(
                indicator in fields
                and fields[indicator]
                and str(fields[indicator]).strip().lower() != "yes"
                for indicator in lawyer_indicator_keys
            )
            if is_lawyer:
                lawyer_info: Dict[str, Any] = {}
                if fields_to_extract is None:
                    lawyer_info.update(fields)
                else:
                    for base in fields_to_extract:
                        if base in fields:
                            lawyer_info[base] = fields[base]
                lawyers.append(lawyer_info)

        return lawyers

    def format_new_attorneys(self, lawyers: List[Dict[str, Any]]) -> Dict[str, str]:
        """Fallback attorney formatting using numbered groups."""
        results: Dict[str, str] = {}
        attorney_blocks: List[str] = []

        for idx, lawyer in enumerate(lawyers, 1):
            raw_attorney = str(lawyer.get("Attorney", "")).strip()
            if not raw_attorney:
                continue

            cleaned_name = self._clean_attorney_name(raw_attorney)

            results[f"TAKING_ATTORNEY{idx}"] = cleaned_name
            results[f"TAKING_ATTORNEY{idx}_LAST_NAME"] = self._get_attorney_last_name(
                raw_attorney
            )

            # Clean the Attorney field before building block
            # cleaned_lawyer = lawyer.copy()
            # cleaned_lawyer["Attorney"] = cleaned_name

            attorney_block = "\n".join(str(v) for v in lawyer.values()).upper()
            results[f"ATTORNEY_{idx}_BLOCK"] = attorney_block
            attorney_blocks.append(attorney_block)

        if attorney_blocks:
            results["ATTORNIES_BLOCK"] = "\n\n".join(attorney_blocks)

        return results

    def _format_pbs_attorney_appearances(self, m: Dict[str, Any]) -> Dict[str, str]:
        """Primary attorney formatting path (most common PBS form layout)."""
        results: Dict[str, str] = {}
        attorney_blocks: List[str] = []

        for i in range(1, 5):
            name_key = "Attorney 1" if i == 1 else f"Attorney{i}"
            raw_name = str(m.get(name_key, "")).strip()
            if not raw_name:
                break

            cleaned_name = self._clean_attorney_name(raw_name)

            results[f"TAKING_ATTORNEY{i}"] = cleaned_name
            results[f"TAKING_ATTORNEY{i}_LAST_NAME"] = self._get_attorney_last_name(
                raw_name
            )

            # Build block using CLEANED name
            firm = str(m.get("First Name" if i == 1 else f"First Name{i}", "")).strip()
            addr = str(
                m.get("Delivery Address" if i == 1 else f"Delivery Address{i}", "")
            ).strip()
            phone = str(m.get("Phone" if i == 1 else f"Phone{i}", "")).strip()
            email = str(m.get("email" if i == 1 else f"EMAIL {i}", "")).strip()

            block_lines = [
                f"\t{raw_name.upper()}",
                f"\t{firm.upper()}",
                f"\t{addr.upper()}",
                f"\t{phone}",
                f"\t{email.upper()}",
            ]
            attorney_block = "\n".join(block_lines)

            results[f"ATTORNEY_{i}_BLOCK"] = attorney_block
            attorney_blocks.append(attorney_block)

        if attorney_blocks:
            results["ATTORNIES_BLOCK"] = "\n\n".join(attorney_blocks)
            return results

        # ==================== FALLBACK PATH (alternate PBS layout) ====================
        fields_to_extract = [
            "Attorney",
            "Form Name",
            "Delivery Address",
            "Phone Number",
            "Email",
        ]
        lawyers = self.extract_lawyers(m, fields_to_extract=fields_to_extract)
        return self.format_new_attorneys(lawyers)

    def _apply_transformation(
        self,
        base_keys: List[str],
        extracted: Dict[str, Any],
        transform: callable,
    ) -> Dict[str, Any]:
        """Apply a string transformation (upper/title/lower) to matching keys."""
        updates: Dict[str, Any] = {}
        suffix = transform.__name__.split("_")[-1].upper()

        for base in base_keys:
            for key, value in extracted.items():
                if key.startswith(base):
                    transformed = transform(value) if isinstance(value, str) else value
                    updates[f"{key}_{suffix}"] = transformed
        return updates

    def _apply_case_variants(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Generate UPPER, Title, and lower variants for template use."""
        upper_keys = [
            "WITNESS_NAME",
            "DATE",
            "MONTH",
            "TAKING_ATTORNEY",
            "ATTORNEY_",
            "COURT_REPORTER_NAME",
        ]
        title_keys = [
            "WITNESS_NAME",
            "WITNESS_LAST_NAME",
            "DATE",
            "MONTH",
            "TAKING_ATTORNEY",
            "ATTORNEY_",
            "COURT_REPORTER_NAME",
        ]
        lower_keys = ["END_TIME", "WAIVER_OF_READING"]

        upper_updates = self._apply_transformation(upper_keys, extracted, str.upper)
        title_updates = self._apply_transformation(title_keys, extracted, str.title)
        lower_updates = self._apply_transformation(lower_keys, extracted, str.lower)

        return {**extracted, **upper_updates, **title_updates, **lower_updates}

    def _clean_attorney_name(self, name: str) -> str:
        """Remove all variations of ESQ / ESQUIRE using regex (case-insensitive)."""
        if not isinstance(name, str) or not name.strip():
            return ""

        # Remove ", ESQ.", ", ESQUIRE", " ESQ", "ESQ.", etc.
        cleaned = re.sub(r"(?i)\s*,\s*(?:ESQ\.?|ESQUIRE|ESQ)\b", "", name)
        cleaned = re.sub(r"(?i)\b(?:ESQ\.?|ESQUIRE|ESQ)\b", "", cleaned)
        cleaned = cleaned.strip().rstrip(",")
        return cleaned

    def _get_attorney_last_name(self, name: str) -> str:
        """Return last name from a cleaned attorney name."""
        cleaned = self._clean_attorney_name(name)
        parts = [p for p in cleaned.split() if p]
        return parts[-1] if parts else ""


def fill_template(
    template_path: Path, metadata: Dict[str, Any], output_path: Optional[Path] = None
) -> Path:
    """
    Replace placeholders like [KEY] in a docx template with values from metadata.
    If output_path is None, saves in same directory as template with "_filled" suffix.
    """
    if output_path is None:
        output_path = template_path.parent / f"{template_path.stem}_filled.docx"

    doc = Document(template_path)

    def replace_text(paragraphs):
        for p in paragraphs:
            for key, value in metadata.items():
                placeholder = f"[{key}]"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(value))
                    for run in p.runs:
                        run.font.name = "Courier New"
                        run.font.size = Pt(12)

    replace_text(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                replace_text(cell.paragraphs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    return output_path
