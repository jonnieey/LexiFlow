"""Tab completion for 'config set <key> <value>'."""

from unittest.mock import MagicMock

import pytest

from lexiflow import cli
from lexiflow.config import ConfigManager, configurable_keys
from lexiflow.pdf import BACKEND_PRIORITY


@pytest.fixture
def manager(tmp_path, monkeypatch):
    mgr = ConfigManager(config_file=tmp_path / "config.yaml")
    mgr.set("ai_model", "deepseek-v4-flash")
    monkeypatch.setattr(cli, "config_manager", mgr)
    return mgr


def _fake_cmd():
    cmd = MagicMock()
    cmd.basic_complete.side_effect = lambda text, line, b, e, choices: [
        c for c in choices if c.startswith(text)
    ]
    cmd.path_complete.return_value = ["<paths>"]
    return cmd


def _value(key, text=""):
    line = f"config set {key} {text}"
    return cli._complete_config_value(
        _fake_cmd(), text, line, len(line) - len(text), len(line),
        arg_tokens={"key": [key], "value": [text]},
    )


def test_key_choices_list_every_configurable_key_with_current_value(manager):
    items = cli._complete_config_key(_fake_cmd())

    assert [str(i) for i in items] == configurable_keys()
    by_key = {str(i): i.description for i in items}
    assert by_key["ai_model"] == "deepseek-v4-flash"
    assert "pdf_backend" in by_key and "ai_api_key_env" in by_key


def test_parser_wires_completion():
    key_action, value_action = [
        a for a in cli.config_set_parser._actions if a.dest in ("key", "value")
    ]
    assert key_action.get_choices_callable() is not None
    assert value_action.get_choices_callable() is not None


def test_value_pdf_backend(manager):
    assert _value("pdf_backend") == ["auto", *BACKEND_PRIORITY]


def test_value_invoice_theme(manager):
    from lexiflow.utils import invoice_template_themes

    assert sorted(_value("invoice_theme")) == sorted(invoice_template_themes())


def test_value_currency(manager):
    assert "KES" in _value("display_currency")
    assert "USD" in _value("INVOICE_CURRENCY")


def test_value_ai_api_key_env_lists_names_only(manager, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-secret-value")
    monkeypatch.setenv("NOT_A_KEY_VAR", "x")

    values = _value("ai_api_key_env")

    assert "DEEPSEEK_API_KEY" in values
    assert "NOT_A_KEY_VAR" not in values
    assert all("secret" not in v for v in values)


@pytest.mark.parametrize(
    "key", ["base_dir", "notebooklm_prompt_file", "notebooklm_storage_path"]
)
def test_value_paths(manager, key):
    assert _value(key) == ["<paths>"]


def test_value_other_key_suggests_current_value(manager):
    assert _value("ai_model") == ["deepseek-v4-flash"]


# --- end-to-end through cmd2's completion machinery ----------------------

from cmd2.rl_utils import readline  # noqa: E402
from unittest.mock import patch  # noqa: E402

from lexiflow.models import Config  # noqa: E402


@pytest.fixture
def app(tmp_path, manager):
    config = Config(
        base_dir=str(tmp_path), date_format="%Y-%m-%d", invoice_theme="default"
    )
    with patch("lexiflow.cli.Transcriptor", autospec=True) as mock:
        mock.return_value.config = config
        mock.return_value.base_dir = tmp_path
        mock.return_value.CONFIG_DIR = tmp_path
        mock.return_value.backup = MagicMock()
        yield cli.TranscriptorCMD(history=False, alias=True)


def _complete(app, line):
    text = line.split(" ")[-1]
    begidx, endidx = len(line) - len(text), len(line)
    with patch.object(readline, "get_line_buffer", lambda: line), patch.object(
        readline, "get_begidx", lambda: begidx
    ), patch.object(readline, "get_endidx", lambda: endidx):
        app.complete(text, 0)
    return app.completion_matches


def test_tab_after_config_set_lists_keys(app):
    matches = _complete(app, "config set ")
    assert set(configurable_keys()) <= {m.strip() for m in matches}


def test_tab_completes_pdf_backend_values(app):
    matches = _complete(app, "config set pdf_backend ")
    assert {m.strip() for m in matches} == {"auto", *BACKEND_PRIORITY}


def test_tab_completes_partial_key(app):
    matches = _complete(app, "config set pdf_")
    assert [m.strip() for m in matches] == ["pdf_backend"]
