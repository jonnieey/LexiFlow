import tarfile
from datetime import datetime, timedelta
from pathlib import Path


class Backup:
    def __init__(self, base_dir: Path, backup_dir_name: str = "backups"):
        self.base_dir = base_dir
        self.backup_dir = self.base_dir / backup_dir_name
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.base_dir / "transcriptor.db"

    def get_last_backup_time(self) -> datetime | None:
        backups = sorted(
            self.backup_dir.glob("transcriptor-*.tar.gz"), reverse=True
        )
        if not backups:
            return None

        latest_backup = backups[0]
        try:
            timestamp_str = latest_backup.name.replace(
                "transcriptor-", ""
            ).replace(".tar.gz", "")
            return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
        except ValueError:
            return None

    def should_auto_backup(self) -> bool:
        last_backup_time = self.get_last_backup_time()

        if not last_backup_time:
            return True

        return datetime.now() - last_backup_time > timedelta(days=7)

    def create_backup(self, backup_name: str | None = None) -> Path:
        if not self.db_file.exists():
            raise FileNotFoundError("Database file not found.")

        if backup_name is None:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_name = f"transcriptor-{timestamp}.tar.gz"

        backup_path = self.backup_dir / backup_name

        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(self.db_file, arcname=self.db_file.name)

        return backup_path

    def list_backups(self) -> list[Path]:
        return sorted(self.backup_dir.glob("transcriptor-*.tar.gz"))

    def cleanup_old_backups(self, keep_count: int = 10) -> None:
        """Keep only the most recent backups."""
        backups = self.list_backups()
        if len(backups) > keep_count:
            to_delete = backups[:-keep_count]
            for backup in to_delete:
                backup.unlink()

    def restore_backup(self, backup_path: Path) -> None:
        if not backup_path.exists():
            raise FileNotFoundError("Backup file not found.")

        self.create_backup(backup_name="before-restore.tar.gz")

        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(path=self.base_dir, filter="data")
