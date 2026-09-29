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
