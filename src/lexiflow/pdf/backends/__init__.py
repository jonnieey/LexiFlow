"""
PDF backends for transcriptor.
"""

from .playwright_backend import PlaywrightBackend
from .weasyprint_backend import WeasyPrintBackend
from .xhtml2pdf_backend import XHTML2PDFBackend

__all__ = ["WeasyPrintBackend", "PlaywrightBackend", "XHTML2PDFBackend"]
