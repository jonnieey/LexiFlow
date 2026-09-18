"""
WeasyPrint PDF backend.
"""

import logging
from pathlib import Path
from typing import Optional

from ..core import PDFBackend

logger = logging.getLogger(__name__)


class WeasyPrintBackend(PDFBackend):
    """PDF backend using WeasyPrint.

    Requires system dependencies (GTK, Cairo). See WeasyPrint documentation.
    """

    def __init__(self) -> None:
        super().__init__()
        # Import here to allow optional dependency
        from weasyprint import HTML

        self.HTML = HTML
        logger.debug("Initialized WeasyPrint backend")

    def render(self, html: str, output_path: Path) -> Optional[bytes]:
        """Render HTML to PDF using WeasyPrint."""
        logger.debug("Rendering PDF with WeasyPrint to %s", output_path)
        try:
            pdf_bytes = self.HTML(string=html).write_pdf(output_path)
            logger.info("WeasyPrint PDF generated: %s", output_path)
            return pdf_bytes
        except Exception as e:
            logger.error("WeasyPrint rendering failed: %s", e)
            raise
