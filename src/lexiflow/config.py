import os
import logging
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


def is_secret_key(key: str) -> bool:
    return key.upper() in SECRET_KEYS


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

    def migrate_from_env(self, env_path: Optional[Path] = None) -> bool:
        """Migrate configuration from .env file to config file"""
        if env_path is None:
            # Try to find .env in common locations
            possible_paths = [
                Path.cwd() / ".env",
                Path(__file__).parent / ".env",
                Path(__file__).parent.parent / ".env",
            ]

            for path in possible_paths:
                if path.exists():
                    env_path = path
                    break

        if not env_path or not env_path.exists():
            return False

        # Load .env file
        load_dotenv(env_path, override=True)

        # Map environment variables to config keys (secrets stay in env)
        env_mapping = {
            "AI_MODEL": "AI_MODEL",
            "BASE_URL": "BASE_URL",
            "NOTEBOOKLM_STORAGE_PATH": "NOTEBOOKLM_STORAGE_PATH",
            "NOTEBOOKLM_NOTEBOOK_ID": "NOTEBOOKLM_NOTEBOOK_ID",
            "NOTEBOOKLM_PROMPT_FILE": "NOTEBOOKLM_PROMPT_FILE",
            "NOTEBOOKLM_METADATA_KEYS": "NOTEBOOKLM_METADATA_KEYS",
            "NOTEBOOKLM_MAX_METADATA_TOKENS": "NOTEBOOKLM_MAX_METADATA_TOKENS",
            "FILE_MANAGER": "FILE_MANAGER",
            "TERMINAL": "TERMINAL",
        }

        migrated = False
        for env_key, config_key in env_mapping.items():
            value = os.getenv(env_key)
            if value and not self.get(config_key):
                self.set(config_key, value)
                migrated = True

        return migrated


# Load legacy .env for backward compatibility
load_dotenv(override=True)

# Initialize config manager
config_manager = ConfigManager()

# Try to migrate from .env if config is empty
if not config_manager.config_data:
    config_manager.migrate_from_env()


@dataclass
class Settings:
    """Settings from the config file and environment.

    Secrets (``SECRET_KEYS``) come from environment variables only.
    """

    OPENAI_API_KEY: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY") or ""
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
