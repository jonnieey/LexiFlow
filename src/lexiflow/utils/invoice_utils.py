import re
from pathlib import Path
from typing import Optional

from bs4.element import Tag
from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    select_autoescape,
)
from markdownify import MarkdownConverter  # type: ignore

from lexiflow.models import Invoice, SummaryInvoice
from lexiflow.pdf import PDFRenderer, render_pdf
from lexiflow.utils.currency import currency_symbol


def _init_jinja_env(custom_templates_dir: Optional[Path]) -> Environment:
    loaders = []
    if custom_templates_dir is not None:
        loaders.append(FileSystemLoader(custom_templates_dir))
    loaders.append(PackageLoader("lexiflow", "invoice_templates"))  # type: ignore
    loader = ChoiceLoader(loaders)
    return Environment(
        loader=loader,
        autoescape=select_autoescape(),
        undefined=StrictUndefined,
    )


async def htmlstr_to_pdf_async(
    htmlstr: str, output_path: Path
) -> Optional[bytes]:
    """Async HTML to PDF rendering using the configured PDF backend."""
    output_path = Path(output_path)
    return await PDFRenderer().render_async(htmlstr, output_path)


def htmlstr_to_pdf(htmlstr: str, output_path: Path) -> Optional[bytes]:
    """Render HTML to PDF using the configured PDF backend."""
    output_path = Path(output_path)
    return render_pdf(htmlstr, output_path)


def render_invoice(
    invoice: Invoice,
    custom_templates_dir: Optional[Path] = None,
    template_name: Optional[str] = None,
) -> str:
    if template_name is None:
        template_name = "invoice_default.html"
    template = _init_jinja_env(custom_templates_dir).get_template(
        template_name
    )
    return template.render(
        invoice=invoice,
        currency_symbol=currency_symbol(
            getattr(invoice, "currency", "USD") or "USD"
        ),
    )


def render_summary_invoice(
    summary_invoice: SummaryInvoice,
    custom_templates_dir: Optional[Path] = None,
    template_name: Optional[str] = None,
) -> str:
    if template_name is None:
        template_name = "summary_invoice.html"
    template = _init_jinja_env(custom_templates_dir).get_template(
        template_name
    )
    return template.render(
        summary_invoice=summary_invoice,
        currency_symbol=currency_symbol(
            getattr(summary_invoice, "currency", "USD") or "USD"
        ),
    )


def write_pdf(
    invoice,
    output_path: Path,
    custom_templates_dir: Optional[Path] = None,
    template_name: Optional[str] = None,
) -> Optional[bytes]:
    return htmlstr_to_pdf(
        render_invoice(invoice, custom_templates_dir, template_name),
        output_path,
    )


class MDConverter(MarkdownConverter):
    """
    Converter for Markdown to HTML
    """

    def convert_tr(self, el: Tag, text: str, convert_as_inline: bool) -> str:
        return super().convert_tr(el, text, convert_as_inline) + "\n"


def md(html: str, **options) -> str:
    """
    Convert Markdown to HTML
    """
    return MDConverter(**options).convert(html)


def html_to_md(html: str) -> str:
    markdown = md(html)
    md_table = markdown[markdown.find("![]()") + 5 :]
    md_table = re.sub(r"\n{2,}", "\n\n", md_table)
    return md_table


def invoice_template_themes():
    invoice_template_dir = Path(__file__).parent.parent / "invoice_templates"
    template_themes = []
    for invoice_file in invoice_template_dir.iterdir():
        if invoice_file.stem.startswith("invoice_"):
            template_themes.append(invoice_file.stem.replace("invoice_", ""))
    return template_themes
