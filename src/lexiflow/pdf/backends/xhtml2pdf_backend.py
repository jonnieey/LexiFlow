"""
xhtml2pdf PDF backend.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

from ..core import PDFBackend

logger = logging.getLogger(__name__)


class XHTML2PDFBackend(PDFBackend):
    """PDF backend using xhtml2pdf (pisa).

    Pure Python backend with limited CSS support.
    """

    def __init__(self) -> None:
        super().__init__()
        # Import here to allow optional dependency
        from xhtml2pdf import pisa

        self.pisa = pisa
        logger.debug("Initialized xhtml2pdf backend")

    def render(self, html: str, output_path: Path) -> Optional[bytes]:
        """Render HTML to PDF using xhtml2pdf."""
        logger.debug("Rendering PDF with xhtml2pdf to %s", output_path)
        try:
            # Create PDF in memory
            pdf_buffer = BytesIO()
            result = self.pisa.CreatePDF(html, dest=pdf_buffer)
            if result.err:
                raise RuntimeError(f"xhtml2pdf error: {result.err}")
            pdf_bytes = pdf_buffer.getvalue()
            # Write to file
            output_path.write_bytes(pdf_bytes)
            logger.info("xhtml2pdf PDF generated: %s", output_path)
            return pdf_bytes
        except Exception as e:
            logger.error("xhtml2pdf rendering failed: %s", e)
            raise
