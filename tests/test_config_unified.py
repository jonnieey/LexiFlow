import yaml

from lexiflow.models import Config


def test_config_new_fields_have_defaults():
    cfg = Config(base_dir="/tmp/x", date_format="%Y-%m-%d", invoice_theme="default")

    assert cfg.pdf_backend == "auto"
    assert cfg.ai_model is None
    assert cfg.ai_api_key_env is None
    assert cfg.base_url is None
    assert cfg.notebooklm_storage_path is None
    assert cfg.notebooklm_notebook_id is None
    assert cfg.notebooklm_prompt_file is None
    assert cfg.notebooklm_metadata_keys is None
    assert cfg.notebooklm_max_metadata_tokens is None
    assert cfg.file_manager == ""
    assert cfg.terminal == ""


def test_old_transcriptor_yaml_still_loads(tmp_path):
    old = tmp_path / "config.yaml"
    old.write_text(
        yaml.dump(
            {
                "base_dir": "/data",
                "date_format": "%d/%m/%Y",
                "invoice_theme": "nord",
            }
        )
    )

    cfg = Config.from_yaml(old)

    assert cfg.base_dir == "/data"
    assert cfg.pdf_backend == "auto"


def test_config_has_no_secret_fields():
    fields = set(Config.model_fields)
    assert not {"openai_api_key", "speechmatix_api_key", "revai_api_key"} & fields


# --- unified config file -------------------------------------------------

from pathlib import Path  # noqa: E402

from lexiflow import config as cfg  # noqa: E402


def test_default_config_path_is_lexiflow_yaml(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert cfg.default_config_path() == tmp_path / "lexiflow" / "config.yaml"


def test_transcriptor_uses_unified_config_path(monkeypatch, tmp_path):
    from lexiflow.base import Transcriptor

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    t = Transcriptor.__new__(Transcriptor)

    config_dir, config_file = t._get_config_paths(None)

    assert config_file == tmp_path / "lexiflow" / "config.yaml"
    assert config_dir == tmp_path / "lexiflow"


def test_manager_reads_uppercase_keys_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump({"ai_model": "gpt-x", "file_manager": "ranger"}))

    mgr = cfg.ConfigManager(config_file=path)

    assert mgr.get("AI_MODEL") == "gpt-x"
    assert mgr.get("FILE_MANAGER") == "ranger"
    assert mgr.get("TERMINAL", "d") == "d"


def test_manager_set_on_missing_file_seeds_loadable_config(tmp_path):
    path = tmp_path / "sub" / "config.yaml"
    mgr = cfg.ConfigManager(config_file=path)

    mgr.set("AI_MODEL", "gpt-x")

    loaded = Config.from_yaml(path)
    assert loaded.ai_model == "gpt-x"
    assert loaded.base_dir == cfg.DEFAULT_CONFIG["base_dir"]


def test_manager_set_preserves_external_changes(tmp_path):
    path = tmp_path / "config.yaml"
    mgr = cfg.ConfigManager(config_file=path)
    mgr.set("AI_MODEL", "gpt-x")

    # Another writer (e.g. Transcriptor.save_config) updates the file.
    data = yaml.safe_load(path.read_text())
    data["date_format"] = "%d/%m/%Y"
    path.write_text(yaml.dump(data))

    mgr.set("TERMINAL", "kitty -e")

    data = yaml.safe_load(path.read_text())
    assert data["date_format"] == "%d/%m/%Y"
    assert data["terminal"] == "kitty -e"
    assert data["ai_model"] == "gpt-x"


def test_manager_delete_removes_key(tmp_path):
    path = tmp_path / "config.yaml"
    mgr = cfg.ConfigManager(config_file=path)
    mgr.set("AI_MODEL", "gpt-x")

    mgr.delete("AI_MODEL")

    assert "ai_model" not in yaml.safe_load(path.read_text())
    assert mgr.get("AI_MODEL") is None


def test_manager_does_not_create_file_on_init(tmp_path):
    path = tmp_path / "config.yaml"
    cfg.ConfigManager(config_file=path)

    assert not Path(path).exists()


# --- env-only secrets ----------------------------------------------------

import pytest  # noqa: E402

SECRETS = ["OPENAI_API_KEY", "SPEECHMATIX_API_KEY", "REVAI_API_KEY"]


@pytest.mark.parametrize("key", SECRETS)
def test_settings_ignore_secret_in_config_file(monkeypatch, key):
    monkeypatch.setattr(cfg.config_manager, "get", lambda *a, **k: "from-file")
    monkeypatch.delenv(key, raising=False)

    assert not getattr(cfg.Settings(), key)


@pytest.mark.parametrize("key", SECRETS)
def test_settings_read_secret_from_env(monkeypatch, key):
    monkeypatch.setattr(cfg.config_manager, "get", lambda *a, **k: "from-file")
    monkeypatch.setenv(key, "from-env")

    assert getattr(cfg.Settings(), key) == "from-env"


@pytest.mark.parametrize("key", SECRETS + ["openai_api_key"])
def test_manager_refuses_to_store_secrets(tmp_path, key):
    path = tmp_path / "config.yaml"
    mgr = cfg.ConfigManager(config_file=path)

    with pytest.raises(ValueError, match="environment variable"):
        mgr.set(key, "sk-123456789")

    assert not path.exists()


def test_migrate_from_env_skips_secrets(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-secret123\nAI_MODEL=gpt-x\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    path = tmp_path / "config.yaml"
    mgr = cfg.ConfigManager(config_file=path)

    assert mgr.migrate_from_env(env) is True

    data = yaml.safe_load(path.read_text())
    assert data["ai_model"] == "gpt-x"
    assert "openai_api_key" not in data


def test_cli_config_set_secret_prints_guidance(tmp_path, monkeypatch):
    from lexiflow import cli

    mgr = cfg.ConfigManager(config_file=tmp_path / "config.yaml")
    monkeypatch.setattr(cli, "config_manager", mgr)
    out = []
    fake = type("F", (), {"poutput": lambda self, m: out.append(m)})()

    cli.TranscriptorCMD.config_set(
        fake, type("A", (), {"key": "OPENAI_API_KEY", "value": "sk-1"})()
    )

    text = "\n".join(out)
    assert "export OPENAI_API_KEY=" in text
    assert "sk-1" not in text


def test_cli_config_show_lists_secret_env_vars_masked(tmp_path, monkeypatch):
    from lexiflow import cli

    mgr = cfg.ConfigManager(config_file=tmp_path / "config.yaml")
    mgr.set("AI_MODEL", "gpt-x")
    monkeypatch.setattr(cli, "config_manager", mgr)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abcdefghijkl")
    monkeypatch.delenv("REVAI_API_KEY", raising=False)
    out = []
    fake = type("F", (), {"poutput": lambda self, m: out.append(m)})()

    cli.TranscriptorCMD.config_show(fake, None)

    text = "\n".join(out)
    assert "ai_model: gpt-x" in text
    assert "OPENAI_API_KEY: sk-a" in text
    assert "sk-abcdefghijkl" not in text
    assert "REVAI_API_KEY: (not set)" in text


# --- legacy migration ----------------------------------------------------

import json  # noqa: E402


def _legacy(tmp_path, transcriptor=None, legatoflow=None):
    t = tmp_path / "transcriptor" / "config.yaml"
    l = tmp_path / "legatoflow" / "config"
    if transcriptor is not None:
        t.parent.mkdir(parents=True)
        t.write_text(yaml.dump(transcriptor))
    if legatoflow is not None:
        l.parent.mkdir(parents=True)
        l.write_text(json.dumps(legatoflow))
    return t, l


def test_migrate_merges_both_legacy_files(tmp_path):
    t, l = _legacy(
        tmp_path,
        transcriptor={
            "base_dir": "/data",
            "date_format": "%d/%m/%Y",
            "invoice_theme": "nord",
        },
        legatoflow={"AI_MODEL": "gpt-x", "TERMINAL": "kitty -e"},
    )
    target = tmp_path / "lexiflow" / "config.yaml"

    assert cfg.migrate_legacy_configs(target, t, l) is True

    loaded = Config.from_yaml(target)
    assert loaded.base_dir == "/data"
    assert loaded.invoice_theme == "nord"
    assert loaded.ai_model == "gpt-x"
    assert loaded.terminal == "kitty -e"


def test_migrate_skips_secrets_and_warns(tmp_path, capsys):
    t, l = _legacy(
        tmp_path,
        legatoflow={"OPENAI_API_KEY": "sk-secret", "REVAI_API_KEY": "rv"},
    )
    target = tmp_path / "lexiflow" / "config.yaml"

    cfg.migrate_legacy_configs(target, t, l)

    raw = target.read_text()
    assert "sk-secret" not in raw
    assert "openai_api_key" not in raw.lower()
    err = capsys.readouterr().err
    assert "OPENAI_API_KEY" in err and "REVAI_API_KEY" in err
    assert "sk-secret" not in err
    # base_dir etc. seeded from defaults so the file is loadable
    assert Config.from_yaml(target).base_dir == cfg.DEFAULT_CONFIG["base_dir"]


def test_migrate_noop_when_target_exists(tmp_path):
    t, l = _legacy(tmp_path, legatoflow={"AI_MODEL": "gpt-x"})
    target = tmp_path / "lexiflow" / "config.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.dump({**cfg.DEFAULT_CONFIG, "ai_model": "keep"}))

    assert cfg.migrate_legacy_configs(target, t, l) is False
    assert Config.from_yaml(target).ai_model == "keep"


def test_migrate_noop_without_legacy_files(tmp_path):
    t, l = _legacy(tmp_path)
    target = tmp_path / "lexiflow" / "config.yaml"

    assert cfg.migrate_legacy_configs(target, t, l) is False
    assert not target.exists()


def test_migrate_leaves_legacy_files_in_place(tmp_path):
    t, l = _legacy(
        tmp_path,
        transcriptor={"base_dir": "/d", "date_format": "%Y", "invoice_theme": "x"},
        legatoflow={"AI_MODEL": "gpt-x"},
    )

    cfg.migrate_legacy_configs(tmp_path / "lexiflow" / "config.yaml", t, l)

    assert t.exists() and l.exists()


def test_cli_config_set_refreshes_in_memory_config(tmp_path, monkeypatch):
    """A later save_config must not clobber a value set via 'config set'."""
    from lexiflow import cli
    from lexiflow.base import Transcriptor

    path = tmp_path / "config.yaml"
    Config(**cfg.DEFAULT_CONFIG).write(path)
    mgr = cfg.ConfigManager(config_file=path)
    monkeypatch.setattr(cli, "config_manager", mgr)

    app = Transcriptor.__new__(Transcriptor)
    app.CONFIG_FILE = path
    app.config = Config.from_yaml(path)
    fake = type("F", (), {"poutput": lambda self, m: None, "app": app})()

    cli.TranscriptorCMD.config_set(
        fake, type("A", (), {"key": "AI_MODEL", "value": "gpt-x"})()
    )
    app.save_config()

    assert Config.from_yaml(path).ai_model == "gpt-x"
