import yaml

from lexiflow.models import Config


def test_config_new_fields_have_defaults():
    cfg = Config(base_dir="/tmp/x", date_format="%Y-%m-%d", invoice_theme="default")

    assert cfg.pdf_backend == "auto"
    assert cfg.ai_model is None
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
