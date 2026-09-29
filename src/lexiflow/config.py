import os
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv
from platformdirs import user_config_dir, user_data_dir
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


CONFIG_APP_NAME = "lexiflow"
DATA_APP_NAME = "transcriptor"
CONFIG_FILE_NAME = "config.yaml"

DEFAULT_CONFIG = {
    "base_dir": f"{user_data_dir(DATA_APP_NAME)}",
    "date_format": "%Y-%m-%d",
    "invoice_theme": "default",
    "display_currency": "USD",
    "conversion_rate": 0.0,
    "currency_segment": "",
    "currency_receive_country": "",
    "currency_send_country": "us",
    "invoice_currency": "USD",
}


# Secrets are read from environment variables only, never from the file.
SECRET_KEYS = frozenset({"OPENAI_API_KEY", "SPEECHMATIX_API_KEY", "REVAI_API_KEY"})


DEFAULT_AI_API_KEY_ENV = "OPENAI_API_KEY"


def is_secret_key(key: str) -> bool:
    key = key.upper()
    return key in SECRET_KEYS or key.endswith("_API_KEY")


def default_config_path() -> Path:
    """Path of the single unified config file."""
    return Path(user_config_dir(CONFIG_APP_NAME)) / CONFIG_FILE_NAME


class ConfigManager:
    """Key/value access to the unified YAML config file.

    Keys are accepted in the legacy LegatoFlow UPPER_CASE form and stored
    lowercase, matching the ``Config`` model fields.
    """

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = Path(config_file or default_config_path())
        self.config_dir = self.config_file.parent
        self.config_data: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file (empty if missing)"""
        if not self.config_file.exists():
            self.config_data = {}
            return
        try:
            with open(self.config_file, "r") as f:
                self.config_data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError) as e:
            logger.warning(
                "Failed to load config from %s, starting empty: %s",
                self.config_file,
                e,
            )
            self.config_data = {}

    def _save_config(self) -> None:
        """Save configuration to file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                yaml.dump(self.config_data, f)
        except IOError as e:
            logger.error("Failed to save config to %s: %s", self.config_file, e)

    def _reload_for_write(self) -> None:
        """Re-read the file so other writers' changes are kept."""
        self._load_config()
        if not self.config_data:
            self.config_data = dict(DEFAULT_CONFIG)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        value = self.config_data.get(key.lower())
        return default if value is None else value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        if is_secret_key(key):
            raise ValueError(
                f"{key.upper()} is a secret; set it as an environment "
                f"variable (export {key.upper()}=...) instead of in the "
                "config file."
            )
        self._reload_for_write()
        self.config_data[key.lower()] = value
        self._save_config()

    def delete(self, key: str) -> None:
        """Delete a configuration value"""
        self._reload_for_write()
        if key.lower() in self.config_data:
            del self.config_data[key.lower()]
            self._save_config()


def _legacy_transcriptor_config() -> Path:
    return Path(user_config_dir(DATA_APP_NAME)) / CONFIG_FILE_NAME


def _legacy_legatoflow_config() -> Path:
    return Path.home() / ".config" / "legatoflow" / "config"


def migrate_legacy_configs(
    target: Optional[Path] = None,
    transcriptor_file: Optional[Path] = None,
    legatoflow_file: Optional[Path] = None,
) -> bool:
    """One-time merge of the Transcriptor YAML and LegatoFlow JSON configs.

    Only runs when the unified file does not exist yet. Secrets in the
    LegatoFlow file are not copied; the user is told to export them.
    Legacy files are left untouched.
    """
    target = Path(target or default_config_path())
    transcriptor_file = Path(transcriptor_file or _legacy_transcriptor_config())
    legatoflow_file = Path(legatoflow_file or _legacy_legatoflow_config())

    if target.exists() and target.stat().st_size > 0:
        return False
    if not transcriptor_file.exists() and not legatoflow_file.exists():
        return False

    data: Dict[str, Any] = dict(DEFAULT_CONFIG)
    skipped_secrets = []
    try:
        if transcriptor_file.exists():
            with open(transcriptor_file, "r") as f:
                data.update(yaml.safe_load(f) or {})
        if legatoflow_file.exists():
            with open(legatoflow_file, "r") as f:
                for key, value in (json.load(f) or {}).items():
                    if is_secret_key(key):
                        skipped_secrets.append(key.upper())
                    elif value is not None:
                        data[key.lower()] = value
    except (IOError, yaml.YAMLError, json.JSONDecodeError) as e:
        logger.warning("Failed to read legacy config, skipping migration: %s", e)
        return False

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            yaml.dump(data, f)
    except IOError as e:
        logger.error("Failed to write migrated config to %s: %s", target, e)
        return False

    print(f"LexiFlow: merged legacy config into {target}", file=sys.stderr)
    if skipped_secrets:
        print(
            f"LexiFlow: API keys are no longer read from {legatoflow_file}. "
            "Set them as environment variables instead: "
            + ", ".join(sorted(skipped_secrets)),
            file=sys.stderr,
        )
    return True


def load_env_file(path: Optional[Path] = None) -> None:
    """Load a .env file for development; shell env vars always win."""
    if path is None:
        load_dotenv(override=False)
    else:
        load_dotenv(path, override=False)


load_env_file()

migrate_legacy_configs()

# Initialize config manager
config_manager = ConfigManager()


def ai_api_key_env_name(manager: Optional[ConfigManager] = None) -> str:
    """Env var the AI API key is read from (config > env > default)."""
    return (
        (manager or config_manager).get("AI_API_KEY_ENV")
        or os.getenv("AI_API_KEY_ENV")
        or DEFAULT_AI_API_KEY_ENV
    )


@dataclass
class Settings:
    """Settings from the config file and environment.

    Secrets (``SECRET_KEYS``) come from environment variables only.
    """

    # Name of the env var holding the AI key (e.g. DEEPSEEK_API_KEY when
    # BASE_URL points at DeepSeek). OPENAI_API_KEY holds its value.
    AI_API_KEY_ENV: str = field(default_factory=lambda: ai_api_key_env_name())
    OPENAI_API_KEY: str = field(
        default_factory=lambda: os.getenv(ai_api_key_env_name()) or ""
    )
    AI_MODEL: str = field(
        default_factory=lambda: (
            config_manager.get("AI_MODEL") or os.getenv("AI_MODEL", "gpt-4o-mini")
        )
    )
    BASE_URL: str | None = field(
        default_factory=lambda: (
            config_manager.get("BASE_URL") or os.getenv("BASE_URL", None)
        )
    )
    SPEECHMATIX_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("SPEECHMATIX_API_KEY")
    )
    REVAI_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("REVAI_API_KEY")
    )
    NOTEBOOKLM_STORAGE_PATH: str | None = field(
        default_factory=lambda: (
            config_manager.get("NOTEBOOKLM_STORAGE_PATH")
            or os.getenv("NOTEBOOKLM_STORAGE_PATH", None)
        )
    )
    NOTEBOOKLM_NOTEBOOK_ID: str | None = field(
        default_factory=lambda: (
            config_manager.get("NOTEBOOKLM_NOTEBOOK_ID")
            or os.getenv("NOTEBOOKLM_NOTEBOOK_ID", None)
        )
    )
    NOTEBOOKLM_PROMPT_FILE: str | None = field(
        default_factory=lambda: (
            config_manager.get("NOTEBOOKLM_PROMPT_FILE")
            or os.getenv("NOTEBOOKLM_PROMPT_FILE", None)
        )
    )
    NOTEBOOKLM_METADATA_KEYS: str = field(
        default_factory=lambda: (
            config_manager.get("NOTEBOOKLM_METADATA_KEYS")
            or os.getenv(
                "NOTEBOOKLM_METADATA_KEYS",
                "WITNESS_NAME,CASE_NUMBER,DATE,TAKING_ATTORNEY,COURT_REPORTER_NAME,PLAINTIFF,DEFENDANT",
            )
        )
    )
    NOTEBOOKLM_MAX_METADATA_TOKENS: int = field(
        default_factory=lambda: (
            config_manager.get("NOTEBOOKLM_MAX_METADATA_TOKENS")
            or int(os.getenv("NOTEBOOKLM_MAX_METADATA_TOKENS", "530"))
        )
    )
    FILE_MANAGER: str = field(
        default_factory=lambda: (
            config_manager.get("FILE_MANAGER") or os.getenv("FILE_MANAGER", "")
        )
    )
    TERMINAL: str = field(
        default_factory=lambda: (
            config_manager.get("TERMINAL") or os.getenv("TERMINAL", "")
        )
    )


settings = Settings()
