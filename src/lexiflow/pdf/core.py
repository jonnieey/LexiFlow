"""
Core PDF rendering interface and backend registry.
"""

import importlib
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Type

logger = logging.getLogger(__name__)


class PDFBackend(ABC):
    """Abstract base class for PDF rendering backends."""

    @abstractmethod
    def render(self, html: str, output_path: Path) -> Optional[bytes]:
        """
        Render HTML to PDF file.

        Args:
            html: HTML content as string.
            output_path: Path to write PDF file.

        Returns:
            PDF bytes if backend supports it, otherwise None.
        """

    async def render_async(
        self, html: str, output_path: Path
    ) -> Optional[bytes]:
        """
        Async version of render.

        Raises NotImplementedError by default.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support async rendering"
        )


class PDFRenderer:
    """Main PDF renderer that delegates to a configured backend."""

    _backends: Dict[str, Type[PDFBackend]] = {}
    _default_backend: Optional[str] = None

    @classmethod
    def register_backend(
        cls, name: str, backend_class: Type[PDFBackend]
    ) -> None:
        """Register a backend class under the given name."""
        cls._backends[name] = backend_class
        logger.debug("Registered PDF backend '%s' -> %s", name, backend_class)

    @classmethod
    def get_backend(cls, name: str) -> PDFBackend:
        """Instantiate and return a backend by name."""
        if name not in cls._backends:
            raise ValueError(
                f"Unknown backend '{name}'. Available: {list(cls._backends.keys())}"
            )
        return cls._backends[name]()

    @classmethod
    def available_backends(cls) -> list[str]:
        """Return list of registered backend names."""
        return list(cls._backends.keys())

    @classmethod
    def set_default_backend(cls, name: str) -> None:
        """Set the default backend name."""
        if name not in cls._backends:
            raise ValueError(
                f"Cannot set unknown backend '{name}' as default. "
                f"Available: {list(cls._backends.keys())}"
            )
        cls._default_backend = name
        logger.info("Set default PDF backend to '%s'", name)

    @classmethod
    def get_default_backend(cls) -> Optional[str]:
        """Get the current default backend name."""
        return cls._default_backend

    def __init__(self, backend: Optional[str] = None):
        """
        Initialize renderer with optional backend name.

        If backend is None, uses the default backend (if set) or auto‑detects.
        """
        if backend is None:
            if self.__class__._default_backend is not None:
                backend = self.__class__._default_backend
            else:
                backend = auto_detect_engine()
        self.backend_name = backend
        self._backend_instance = self.__class__.get_backend(backend)
        logger.debug("Initialized PDFRenderer with backend '%s'", backend)

    def render(self, html: str, output_path: Path) -> Optional[bytes]:
        """Render HTML to PDF using the configured backend."""
        logger.info(
            "Rendering PDF with backend '%s' to %s",
            self.backend_name,
            output_path,
        )
        try:
            return self._backend_instance.render(html, output_path)
        except Exception as e:
            logger.error("PDF rendering failed: %s", e, exc_info=True)
            raise

    async def render_async(
        self, html: str, output_path: Path
    ) -> Optional[bytes]:
        """Render HTML to PDF asynchronously."""
        logger.info(
            "Rendering PDF asynchronously with backend '%s' to %s",
            self.backend_name,
            output_path,
        )
        try:
            return await self._backend_instance.render_async(
                html, output_path
            )
        except Exception as e:
            logger.error("Async PDF rendering failed: %s", e, exc_info=True)
            raise


def _register_backends() -> None:
    """Attempt to import and register all known backends."""
    backends = [
        (
            "playwright",
            "lexiflow.pdf.backends.playwright_backend",
            "PlaywrightBackend",
        ),
        (
            "weasyprint",
            "lexiflow.pdf.backends.weasyprint_backend",
            "WeasyPrintBackend",
        ),
        (
            "xhtml2pdf",
            "lexiflow.pdf.backends.xhtml2pdf_backend",
            "XHTML2PDFBackend",
        ),
    ]
    for name, module_name, class_name in backends:
        try:
            module = importlib.import_module(module_name)
            backend_class = getattr(module, class_name)
            PDFRenderer.register_backend(name, backend_class)
        except ImportError as e:
            logger.debug("Backend '%s' not available: %s", name, e)
        except Exception as e:
            logger.warning("Failed to register backend '%s': %s", name, e)


def auto_detect_engine() -> str:
    """
    Automatically detect which PDF backend is available.

    Priority order (based on Windows compatibility and ease of installation):
    1. playwright   (best for Windows, headless Chromium)
    2. weasyprint   (requires system libraries)
    3. xhtml2pdf    (pure Python, limited CSS support)

    Returns:
        Name of the first backend that can be imported.

    Raises:
        RuntimeError: If no backend could be imported.
    """
    candidates = ["playwright", "weasyprint", "xhtml2pdf"]
    for name in candidates:
        try:
            importlib.import_module(
                f"lexiflow.pdf.backends.{name}_backend"
            )
            logger.info("Auto‑detected PDF backend: %s", name)
            return name
        except ImportError:
            continue
    raise RuntimeError(
        "No PDF backend available. Install one of: playwright, weasyprint, xhtml2pdf"
    )


def render_pdf(
    html: str,
    output_path: Path,
    backend: Optional[str] = None,
    **kwargs,
) -> Optional[bytes]:
    """
    Convenience function to render HTML to PDF.

    Args:
        html: HTML content.
        output_path: Path to write PDF.
        backend: Backend name (None for auto‑detection).
        **kwargs: Ignored for compatibility.

    Returns:
        PDF bytes or None.
    """
    return PDFRenderer(backend).render(html, output_path)


# Register available backends on module import
_register_backends()

# Set default backend from environment variable, else first available backend
_default_from_env = os.environ.get("LEXIFLOW_PDF_BACKEND")
if _default_from_env and _default_from_env in PDFRenderer._backends:
    PDFRenderer.set_default_backend(_default_from_env)
elif PDFRenderer._backends:
    # Choose priority: playwright > weasyprint > xhtml2pdf
    for name in ["playwright", "weasyprint", "xhtml2pdf"]:
        if name in PDFRenderer._backends:
            PDFRenderer.set_default_backend(name)
            break
