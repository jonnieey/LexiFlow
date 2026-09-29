"""Invoice PDF generation honours the selected default PDF backend."""

import asyncio

import pytest

from lexiflow.pdf.core import PDFBackend, PDFRenderer
from lexiflow.utils import invoice_utils


class _SyncOnly(PDFBackend):
    calls = []

    def render(self, html, output_path):
        _SyncOnly.calls.append(("sync", html, output_path))
        return b"%PDF-sync"


class _AsyncCapable(PDFBackend):
    calls = []

    def render(self, html, output_path):
        _AsyncCapable.calls.append(("sync", html, output_path))
        return b"%PDF-sync"

    async def render_async(self, html, output_path):
        _AsyncCapable.calls.append(("async", html, output_path))
        return b"%PDF-async"


@pytest.fixture
def backends(monkeypatch):
    _SyncOnly.calls = []
    _AsyncCapable.calls = []
    monkeypatch.setattr(
        PDFRenderer,
        "_backends",
        {"playwright": _AsyncCapable, "weasyprint": _SyncOnly},
    )


def test_sync_invoice_uses_selected_backend(backends, monkeypatch, tmp_path):
    monkeypatch.setattr(PDFRenderer, "_default_backend", "weasyprint")

    invoice_utils.htmlstr_to_pdf("<p>x</p>", tmp_path / "a.pdf")

    assert _SyncOnly.calls == [("sync", "<p>x</p>", tmp_path / "a.pdf")]
    assert _AsyncCapable.calls == []


def test_async_invoice_uses_selected_sync_backend(backends, monkeypatch, tmp_path):
    monkeypatch.setattr(PDFRenderer, "_default_backend", "weasyprint")

    result = asyncio.run(
        invoice_utils.htmlstr_to_pdf_async("<p>x</p>", tmp_path / "a.pdf")
    )

    assert result == b"%PDF-sync"
    assert _SyncOnly.calls == [("sync", "<p>x</p>", tmp_path / "a.pdf")]
    assert _AsyncCapable.calls == []


def test_async_invoice_uses_native_async_when_supported(
    backends, monkeypatch, tmp_path
):
    monkeypatch.setattr(PDFRenderer, "_default_backend", "playwright")

    result = asyncio.run(
        invoice_utils.htmlstr_to_pdf_async("<p>x</p>", tmp_path / "a.pdf")
    )

    assert result == b"%PDF-async"
    assert _AsyncCapable.calls == [("async", "<p>x</p>", tmp_path / "a.pdf")]


def test_html_to_pdf_uses_selected_backend(backends, monkeypatch, tmp_path):
    from lexiflow.base import Transcriptor

    monkeypatch.setattr(PDFRenderer, "_default_backend", "weasyprint")
    t = Transcriptor.__new__(Transcriptor)
    t.base_dir = tmp_path

    t.html_to_pdf("<p>inv</p>", "Acme")

    assert len(_SyncOnly.calls) == 1
    assert _SyncOnly.calls[0][1] == "<p>inv</p>"
    assert _AsyncCapable.calls == []
