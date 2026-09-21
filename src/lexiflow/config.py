import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration stored in ~/.config/legatoflow/config"""

    def __init__(self):
        self.config_dir = Path.home() / ".config" / "legatoflow"
        self.config_file = self.config_dir / "config"
        self.config_data: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file or create default"""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    self.config_data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(
                    "Failed to load config from %s, starting empty: %s",
                    self.config_file,
                    e,
                )
                self.config_data = {}
        else:
            self.config_data = {}
            self._save_config()

    def _save_config(self) -> None:
        """Save configuration to file"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config_data, f, indent=2)
        except IOError as e:
            logger.error("Failed to save config to %s: %s", self.config_file, e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self.config_data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value"""
        self.config_data[key] = value
        self._save_config()

    def delete(self, key: str) -> None:
        """Delete a configuration value"""
        if key in self.config_data:
            del self.config_data[key]
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

        # Map environment variables to config keys
        env_mapping = {
            "OPENAI_API_KEY": "OPENAI_API_KEY",
            "AI_MODEL": "AI_MODEL",
            "BASE_URL": "BASE_URL",
            "SPEECHMATIX_API_KEY": "SPEECHMATIX_API_KEY",
            "REVAI_API_KEY": "REVAI_API_KEY",
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
    """Settings dataclass that reads from both environment and config file"""

    OPENAI_API_KEY: str = field(
        default_factory=lambda: (
            config_manager.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        )
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
        default_factory=lambda: (
            config_manager.get("SPEECHMATIX_API_KEY")
            or os.getenv("SPEECHMATIX_API_KEY", None)
        )
    )
    REVAI_API_KEY: str | None = field(
        default_factory=lambda: (
            config_manager.get("REVAI_API_KEY") or os.getenv("REVAI_API_KEY", None)
        )
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
