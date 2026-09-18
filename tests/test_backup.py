import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from lexiflow.backup import Backup

# Constants for testing
TEST_BASE_DIR = Path(__file__).parent / "test_backup_data"


@pytest.fixture(scope="module")
def test_base_dir():
    # Setup
    test_dir = TEST_BASE_DIR
    test_dir.mkdir(exist_ok=True)
    yield test_dir
    # Teardown
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def backup_obj(test_base_dir):
    # Setup
    backup = Backup(base_dir=test_base_dir)
    # Create a dummy db file
    (test_base_dir / "transcriptor.db").touch()
    yield backup
    # Teardown - clean up backups
    shutil.rmtree(backup.backup_dir, ignore_errors=True)
    backup.backup_dir.mkdir(exist_ok=True)


def test_initialization(backup_obj, test_base_dir):
    assert backup_obj.base_dir == test_base_dir
    assert backup_obj.backup_dir == test_base_dir / "backups"
    assert backup_obj.backup_dir.exists()
    assert backup_obj.db_file == test_base_dir / "transcriptor.db"


def test_create_backup(backup_obj):
    backup_path = backup_obj.create_backup()
    assert backup_path.exists()
    assert tarfile.is_tarfile(backup_path)
    assert "transcriptor-" in backup_path.name
    assert backup_path.name.endswith(".tar.gz")

    # Verify content
    with tarfile.open(backup_path, "r:gz") as tar:
        names = tar.getnames()
        assert "transcriptor.db" in names


def test_create_backup_custom_name(backup_obj):
    custom_name = "custom_backup.tar.gz"
    backup_path = backup_obj.create_backup(backup_name=custom_name)
    assert backup_path.name == custom_name
    assert backup_path.exists()


def test_create_backup_no_db(backup_obj, test_base_dir):
    # Remove db file temporarily
    db_file = test_base_dir / "transcriptor.db"
    if db_file.exists():
        db_file.unlink()

    with pytest.raises(FileNotFoundError):
        backup_obj.create_backup()

    # Restore db file
    db_file.touch()


def test_get_last_backup_time(backup_obj):
    # Clear backups
    for f in backup_obj.backup_dir.glob("*"):
        f.unlink()

    assert backup_obj.get_last_backup_time() is None

    # Create a backup
    backup_obj.create_backup()
    last_time = backup_obj.get_last_backup_time()
    assert isinstance(last_time, datetime)

    # Check that it's recent
    assert datetime.now() - last_time < timedelta(minutes=1)


def test_get_last_backup_time_invalid_files(backup_obj):
    # Create invalid backup file
    (backup_obj.backup_dir / "transcriptor-invalid.tar.gz").touch()
    # Should handle gracefully (return None or ignore)
    # If it's the only file, it might try to parse and fail, returning None?
    # Logic: sorted reverse. If invalid file is named such that it comes first?
    # "transcriptor-invalid" vs "transcriptor-2023..."
    # "i" > "2". So invalid comes first.

    # Clear valid backups first
    for f in backup_obj.backup_dir.glob("transcriptor-*.tar.gz"):
        if "invalid" not in f.name:
            f.unlink()

    assert backup_obj.get_last_backup_time() is None


def test_should_auto_backup(backup_obj):
    # Clear backups
    for f in backup_obj.backup_dir.glob("*"):
        f.unlink()

    # Case 1: No backups
    assert backup_obj.should_auto_backup() is True

    # Case 2: Recent backup
    backup_obj.create_backup()
    assert backup_obj.should_auto_backup() is False

    # Case 3: Old backup (simulate by mocking get_last_backup_time or renaming file)
    with patch.object(backup_obj, "get_last_backup_time") as mock_get_time:
        mock_get_time.return_value = datetime.now() - timedelta(days=8)
        assert backup_obj.should_auto_backup() is True


def test_list_backups(backup_obj):
    # Clear backups
    for f in backup_obj.backup_dir.glob("*"):
        f.unlink()

    backup_obj.create_backup(backup_name="transcriptor-backup1.tar.gz")
    backup_obj.create_backup(backup_name="transcriptor-backup2.tar.gz")

    backups = backup_obj.list_backups()
    assert len(backups) == 2
    # Check sorting (default glob isn't guaranteed sorted, but list_backups sorts)
    assert backups == sorted(backups)


def test_cleanup_old_backups(backup_obj):
    # Clear backups
    for f in backup_obj.backup_dir.glob("*"):
        f.unlink()

    # Create 5 backups
    for i in range(5):
        # We need different timestamps
        timestamp = (datetime.now() - timedelta(minutes=5 - i)).strftime(
            "%Y%m%d%H%M%S"
        )
        (backup_obj.backup_dir / f"transcriptor-{timestamp}.tar.gz").touch()

    assert len(backup_obj.list_backups()) == 5

    # Keep only 3
    backup_obj.cleanup_old_backups(keep_count=3)

    remaining = backup_obj.list_backups()
    assert len(remaining) == 3
    # Should keep the most recent ones (last 3 in sorted list)
    # Since we created them in order, the last 3 should be kept.


def test_restore_backup(backup_obj, test_base_dir):
    # Setup: create a backup with a specific file inside
    db_file = test_base_dir / "transcriptor.db"
    db_file.write_text("original content")

    backup_path = backup_obj.create_backup()

    # Modify current db
    db_file.write_text("modified content")

    # Restore
    backup_obj.restore_backup(backup_path)

    # Verify db content restored
    assert db_file.read_text() == "original content"

    # Verify 'before-restore' backup created
    assert (backup_obj.backup_dir / "before-restore.tar.gz").exists()


def test_restore_backup_not_found(backup_obj):
    with pytest.raises(FileNotFoundError):
        backup_obj.restore_backup(Path("non_existent_backup.tar.gz"))


def test_restore_backup_rejects_path_traversal(backup_obj, test_base_dir):
    malicious_path = backup_obj.backup_dir / "malicious.tar.gz"
    with tarfile.open(malicious_path, "w:gz") as tar:
        info = tarfile.TarInfo(name="../evil.txt")
        data = b"pwned"
        info.size = len(data)
        import io

        tar.addfile(info, io.BytesIO(data))

    with pytest.raises(Exception):
        backup_obj.restore_backup(malicious_path)

    assert not (test_base_dir.parent / "evil.txt").exists()
