"""
Playwright PDF backend.
"""

import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from ..core import PDFBackend

logger = logging.getLogger(__name__)


class PlaywrightBackend(PDFBackend):
    """PDF backend using Playwright (headless Chromium).

    This backend is recommended for Windows compatibility.
    Ensure browser binaries are installed via `playwright install`.
    """

    def __init__(self) -> None:
        super().__init__()
        # Import here to allow optional dependency
        from playwright.async_api import async_playwright

        self.async_playwright = async_playwright
        logger.debug("Initialized Playwright backend")

    async def render_async(
        self, html: str, output_path: Path
    ) -> Optional[bytes]:
        """Render HTML to PDF asynchronously using Playwright."""
        logger.debug("Rendering PDF with Playwright to %s", output_path)

        # Font embedding (specific to invoice templates)
        fonts_dir = (
            Path(__file__).parent.parent.parent
            / "invoice_templates"
            / "fonts"
        )
        font_file = fonts_dir / "Montserrat-VariableFont_wght.ttf"
        html_with_font = html
        if font_file.exists():
            with open(font_file, "rb") as f:
                font_b64 = base64.b64encode(f.read()).decode()
            font_data_uri = f"data:font/ttf;charset=utf-8;base64,{font_b64}"
            html_with_font = html.replace(
                "url('fonts/Montserrat-VariableFont_wght.ttf')",
                f"url('{font_data_uri}')",
            )

        async with self.async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            try:
                await page.set_content(
                    html_with_font, wait_until="networkidle"
                )
                await page.evaluate("document.fonts.ready")  # wait for fonts

                pdf_bytes = await page.pdf(
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "0.5in",
                        "right": "0.5in",
                        "bottom": "0.5in",
                        "left": "0.5in",
                    },
                )
                output_path.write_bytes(pdf_bytes)
                logger.info("Playwright PDF generated: %s", output_path)
                return pdf_bytes
            finally:
                await browser.close()

    def render(self, html: str, output_path: Path) -> Optional[bytes]:
        """Synchronous wrapper for async PDF generation."""
        logger.debug("Synchronous PDF rendering with Playwright")
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, we need to run in a thread
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        lambda: asyncio.run(
                            self.render_async(html, output_path)
                        )
                    )
                    return future.result()
            else:
                # Loop exists but not running
                return loop.run_until_complete(
                    self.render_async(html, output_path)
                )
        except RuntimeError:
            # No event loop, create new one
            return asyncio.run(self.render_async(html, output_path))
