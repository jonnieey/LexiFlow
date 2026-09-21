from lexiflow import config as cfg


def _no_config(monkeypatch):
    monkeypatch.setattr(cfg.config_manager, "get", lambda *a, **k: None)


def test_file_manager_settings_default_empty(monkeypatch):
    _no_config(monkeypatch)
    monkeypatch.delenv("FILE_MANAGER", raising=False)
    monkeypatch.delenv("TERMINAL", raising=False)

    settings = cfg.Settings()

    assert settings.FILE_MANAGER == ""
    assert settings.TERMINAL == ""


def test_file_manager_settings_read_env(monkeypatch):
    _no_config(monkeypatch)
    monkeypatch.setenv("FILE_MANAGER", "clifm")
    monkeypatch.setenv("TERMINAL", "kitty -e")

    settings = cfg.Settings()

    assert settings.FILE_MANAGER == "clifm"
    assert settings.TERMINAL == "kitty -e"


def test_file_manager_settings_prefer_config_file(monkeypatch):
    values = {"FILE_MANAGER": "ranger", "TERMINAL": "alacritty -e"}
    monkeypatch.setattr(cfg.config_manager, "get", values.get)
    monkeypatch.delenv("FILE_MANAGER", raising=False)
    monkeypatch.delenv("TERMINAL", raising=False)

    settings = cfg.Settings()

    assert settings.FILE_MANAGER == "ranger"
    assert settings.TERMINAL == "alacritty -e"
