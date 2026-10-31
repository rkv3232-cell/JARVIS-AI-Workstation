import pytest
import hashlib
from pathlib import Path
from backend.auto_updater import SecureAutoUpdater

def test_version_parsing_and_comparison():
    assert SecureAutoUpdater.get_current_version() == "2.1.0"
    
    # Newer remote versions
    assert SecureAutoUpdater._is_newer("2.2.0", "2.1.0") is True
    assert SecureAutoUpdater._is_newer("3.0.0", "2.1.0") is True
    assert SecureAutoUpdater._is_newer("2.1.1", "2.1.0") is True

    # Same or older versions
    assert SecureAutoUpdater._is_newer("2.1.0", "2.1.0") is False
    assert SecureAutoUpdater._is_newer("2.0.9", "2.1.0") is False

def test_file_sha256_verification(tmp_path):
    test_file = tmp_path / "payload.bin"
    content = b"JARVIS_SECURE_UPDATE_PAYLOAD_TEST_DATA"
    test_file.write_bytes(content)

    expected_sha = hashlib.sha256(content).hexdigest()
    assert SecureAutoUpdater.verify_file_sha256(test_file, expected_sha) is True

    # Bad checksum
    assert SecureAutoUpdater.verify_file_sha256(test_file, "0" * 64) is False

def test_backup_snapshot_creation():
    snap = SecureAutoUpdater.create_backup_snapshot()
    if snap:
        assert snap.exists()
        assert snap.suffix == ".zip"
        # Cleanup test snapshot
        try:
            snap.unlink()
        except Exception:
            pass
