import pytest

from lexiflow.pdf import core
from lexiflow.pdf.core import PDFRenderer


class _Dummy:
    def render(self, html, output_path):
        return None


@pytest.fixture
def backends(monkeypatch):
    monkeypatch.setattr(
        PDFRenderer,
        "_backends",
        {"playwright": _Dummy, "weasyprint": _Dummy, "xhtml2pdf": _Dummy},
    )
    monkeypatch.setattr(PDFRenderer, "_default_backend", None)


def test_env_overrides_config(backends):
    core.apply_default_backend(env_value="xhtml2pdf", config_value="weasyprint")
    assert PDFRenderer.get_default_backend() == "xhtml2pdf"


def test_config_used_when_no_env(backends):
    core.apply_default_backend(env_value=None, config_value="weasyprint")
    assert PDFRenderer.get_default_backend() == "weasyprint"


@pytest.mark.parametrize("value", [None, "", "auto"])
def test_auto_uses_priority_order(backends, value):
    core.apply_default_backend(env_value=None, config_value=value)
    assert PDFRenderer.get_default_backend() == "playwright"


def test_unavailable_config_backend_falls_back(backends, monkeypatch, caplog):
    monkeypatch.setattr(
        PDFRenderer, "_backends", {"xhtml2pdf": _Dummy, "weasyprint": _Dummy}
    )
    caplog.set_level("WARNING", logger="lexiflow.pdf.core")
    core.apply_default_backend(env_value=None, config_value="playwright")
    assert PDFRenderer.get_default_backend() == "weasyprint"
    assert "playwright" in caplog.text


def test_reads_config_file_value(backends, monkeypatch):
    from lexiflow import config as cfg

    monkeypatch.delenv("LEXIFLOW_PDF_BACKEND", raising=False)
    monkeypatch.setattr(
        cfg.config_manager, "get", lambda k, d=None: "xhtml2pdf" if k.lower() == "pdf_backend" else d
    )
    core.apply_default_backend()
    assert PDFRenderer.get_default_backend() == "xhtml2pdf"
