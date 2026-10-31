import os
import json
import time
import shutil
import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

from .config import settings
from .security import log_audit_event

UPDATES_DIR = settings.BASE_DIR / "updates"
STAGING_DIR = UPDATES_DIR / "staging"
BACKUP_DIR = UPDATES_DIR / "backup"

UPDATES_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_VERSION = "2.1.0"

class SecureAutoUpdater:
    """
    Secure Windows auto-updater with SHA256 checksum verification,
    staging isolation, and automated rollback snapshot protection.
    """
    @classmethod
    def get_current_version(cls) -> str:
        return CURRENT_VERSION

    @classmethod
    async def check_for_updates(cls, manifest_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Polls the update manifest to check if a newer version is available.
        """
        url = manifest_url or "https://raw.githubusercontent.com/rkv3232-cell/JARVIS-AI-Workstation/main/updates/manifest.json"
        
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    manifest = res.json()
                    remote_ver = manifest.get("version", CURRENT_VERSION)
                    has_update = cls._is_newer(remote_ver, CURRENT_VERSION)
                    return {
                        "success": True,
                        "current_version": CURRENT_VERSION,
                        "remote_version": remote_ver,
                        "update_available": has_update,
                        "manifest": manifest if has_update else None
                    }
        except Exception as e:
            # Manifest check is non-fatal if offline
            pass

        return {
            "success": True,
            "current_version": CURRENT_VERSION,
            "remote_version": CURRENT_VERSION,
            "update_available": False,
            "note": "Latest version already installed or running in offline mode."
        }

    @classmethod
    def _is_newer(cls, remote: str, current: str) -> bool:
        try:
            r_parts = [int(x) for x in remote.split(".")]
            c_parts = [int(x) for x in current.split(".")]
            return r_parts > c_parts
        except Exception:
            return False

    @classmethod
    def verify_file_sha256(cls, file_path: Path, expected_sha256: str) -> bool:
        """Computes and compares SHA256 checksum against manifest."""
        if not file_path.exists():
            return False
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        computed = sha.hexdigest().lower()
        return computed == expected_sha256.lower().strip()

    @classmethod
    def create_backup_snapshot(cls) -> Optional[Path]:
        """Creates a timestamped rollback archive of current code before applying updates."""
        try:
            ts = int(time.time())
            snap_path = BACKUP_DIR / f"snapshot_{CURRENT_VERSION}_{ts}.zip"
            with zipfile.ZipFile(snap_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for folder in ["backend", "frontend"]:
                    src_dir = settings.BASE_DIR / folder
                    for root, _, files in os.walk(src_dir):
                        if "__pycache__" in root or ".git" in root:
                            continue
                        for file in files:
                            p = Path(root) / file
                            arcname = p.relative_to(settings.BASE_DIR)
                            zf.write(p, arcname)
            log_audit_event("create_update_snapshot", str(snap_path), "safe", "success")
            return snap_path
        except Exception as e:
            print(f"[AutoUpdater] Snapshot failed: {e}")
            return None

    @classmethod
    def rollback_to_snapshot(cls, snapshot_path: Path) -> bool:
        """Restores previous version snapshot in case of failed update."""
        try:
            if not snapshot_path.exists():
                return False
            with zipfile.ZipFile(snapshot_path, "r") as zf:
                zf.extractall(settings.BASE_DIR)
            log_audit_event("rollback_update", str(snapshot_path), "high", "success")
            return True
        except Exception as e:
            log_audit_event("rollback_update", str(snapshot_path), "high", "failed", error=str(e))
            return False

