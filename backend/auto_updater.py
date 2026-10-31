import os
import json
import time
import shutil
import hashlib
import zipfile
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx
from cryptography.hazmat.primitives.asymmetric import ed25519

from .config import settings
from .security import log_audit_event

UPDATES_DIR = settings.BASE_DIR / "updates"
STAGING_DIR = UPDATES_DIR / "staging"
BACKUP_DIR = UPDATES_DIR / "backup"
UPDATE_HISTORY_FILE = settings.DATA_DIR / "update_history.json"

UPDATES_DIR.mkdir(parents=True, exist_ok=True)
STAGING_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_VERSION = "2.1.1"

# Pinned Ed25519 Public Key for Release Manifest Cryptographic Verification
PINNED_UPDATE_PUBLIC_KEY_HEX = "88af98807d780c1a8ae469381bafcde2671ab83c1eb1c8ae96680cf4d7e27440"

TRUSTED_RELEASE_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com"
}

class SecureAutoUpdater:
    """
    Cryptographically hardened Windows auto-updater.
    Enforces Ed25519 digital signature validation, SHA256 integrity,
    anti-downgrade checks, ZIP-slip defense, staging isolation, and automatic rollback.
    """
    @classmethod
    def get_current_version(cls) -> str:
        return CURRENT_VERSION

    @classmethod
    def verify_manifest_signature(cls, manifest_dict: Dict[str, Any], public_key_hex: Optional[str] = None) -> bool:
        """
        Cryptographically verifies the digital signature of the manifest_data block
        against the pinned Ed25519 public key.
        """
        try:
            manifest_data = manifest_dict.get("manifest_data")
            sig_hex = manifest_dict.get("signature") or manifest_dict.get("signature_hex")
            if not manifest_data or not sig_hex:
                return False

            pub_hex = public_key_hex or PINNED_UPDATE_PUBLIC_KEY_HEX
            pub_bytes = bytes.fromhex(pub_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)

            canonical_bytes = json.dumps(manifest_data, sort_keys=True, separators=(',', ':')).encode("utf-8")
            sig_bytes = bytes.fromhex(sig_hex)

            public_key.verify(sig_bytes, canonical_bytes)
            return True
        except Exception as e:
            print(f"[AutoUpdater] Signature verification error: {e}")
            return False

    @classmethod
    async def check_for_updates(cls, manifest_url: Optional[str] = None, public_key_hex: Optional[str] = None) -> Dict[str, Any]:
        """
        Polls the signed update manifest.
        Returns UPDATE_CHECK_UNAVAILABLE on connection failures instead of falsely claiming up to date.
        """
        url = manifest_url or "https://raw.githubusercontent.com/rkv3232-cell/JARVIS-AI-Workstation/main/updates/manifest.json"
        
        # Verify URL is HTTPS
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" and parsed.hostname not in ["127.0.0.1", "localhost"]:
            return {
                "success": False,
                "status": "INSECURE_MANIFEST_URL",
                "current_version": CURRENT_VERSION,
                "message": "Manifest URL must utilize HTTPS transport."
            }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    return {
                        "success": False,
                        "status": "UPDATE_CHECK_UNAVAILABLE",
                        "current_version": CURRENT_VERSION,
                        "message": f"Update check unavailable: HTTP {res.status_code} from manifest server."
                    }
                manifest = res.json()
        except Exception as e:
            return {
                "success": False,
                "status": "UPDATE_CHECK_UNAVAILABLE",
                "current_version": CURRENT_VERSION,
                "message": f"Update check unavailable: {str(e)}"
            }

        # 1. Cryptographic Signature Verification
        if not cls.verify_manifest_signature(manifest, public_key_hex=public_key_hex):
            log_audit_event("update_check", url, "high", "signature_failed")
            return {
                "success": False,
                "status": "SIGNATURE_VERIFICATION_FAILED",
                "current_version": CURRENT_VERSION,
                "message": "Untrusted or tampered update manifest: Digital signature validation failed."
            }

        manifest_data = manifest["manifest_data"]
        remote_ver = manifest_data.get("version", CURRENT_VERSION)
        
        # 2. Anti-downgrade & Version Check
        has_update = cls._is_newer(remote_ver, CURRENT_VERSION)

        return {
            "success": True,
            "status": "UPDATE_AVAILABLE" if has_update else "UP_TO_DATE",
            "current_version": CURRENT_VERSION,
            "remote_version": remote_ver,
            "update_available": has_update,
            "manifest_data": manifest_data if has_update else None
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
        """Computes and compares SHA256 checksum against signed manifest."""
        if not file_path.exists():
            return False
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        computed = sha.hexdigest().lower()
        return computed == expected_sha256.lower().strip()

    @classmethod
    def safe_extract_zip(cls, zip_path: Path, target_dir: Path) -> List[Path]:
        """
        Extracts ZIP archive with absolute ZIP-slip path traversal defense.
        """
        extracted_paths = []
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                resolved_target = (target_dir / member.filename).resolve()
                if target_dir not in resolved_target.parents and resolved_target != target_dir:
                    raise SecurityError(f"ZIP Slip exploit detected in member: {member.filename}")
                zf.extract(member, target_dir)
                extracted_paths.append(resolved_target)

        return extracted_paths

    @classmethod
    def create_backup_snapshot(cls) -> Optional[Path]:
        """Creates a timestamped rollback archive of current code before applying updates."""
        try:
            ts = int(time.time())
            snap_path = BACKUP_DIR / f"snapshot_{CURRENT_VERSION}_{ts}.zip"
            with zipfile.ZipFile(snap_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for folder in ["backend", "frontend"]:
                    src_dir = settings.BASE_DIR / folder
                    if not src_dir.exists():
                        continue
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
            cls._record_history("ROLLBACK", f"Rolled back to {snapshot_path.name}")
            log_audit_event("rollback_update", str(snapshot_path), "high", "success")
            return True
        except Exception as e:
            log_audit_event("rollback_update", str(snapshot_path), "high", "failed", error=str(e))
            return False

    @classmethod
    async def download_and_apply_update(
        cls,
        manifest_dict: Dict[str, Any],
        public_key_hex: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end update application with staging isolation,
        package integrity verification, and automatic rollback on failure.
        """
        # 1. Verify Digital Signature
        if not cls.verify_manifest_signature(manifest_dict, public_key_hex=public_key_hex):
            return {"success": False, "error": "Signature validation failed for manifest."}

        manifest_data = manifest_dict["manifest_data"]
        download_url = manifest_data.get("download_url", "")
        expected_sha = manifest_data.get("sha256", "")
        version = manifest_data.get("version", "unknown")

        # 2. Validate Trusted Release Origin (HTTPS only)
        parsed = urlparse(download_url)
        if parsed.scheme.lower() != "https" or parsed.hostname not in TRUSTED_RELEASE_HOSTS:
            return {"success": False, "error": f"Untrusted release origin '{parsed.hostname}'. Updates restricted to official hosts."}

        # 3. Create Pre-Update Rollback Snapshot
        snapshot_path = cls.create_backup_snapshot()
        if not snapshot_path:
            return {"success": False, "error": "Failed to create pre-update backup snapshot. Aborting."}

        staging_pkg = STAGING_DIR / f"package_{version}.zip"
        staging_unpacked = STAGING_DIR / f"unpacked_{version}"

        try:
            # 4. Download Package to Isolated Staging
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(download_url)
                if res.status_code != 200:
                    return {"success": False, "error": f"Download failed with HTTP {res.status_code}."}
                with open(staging_pkg, "wb") as f:
                    f.write(res.content)

            # 5. SHA256 Integrity Verification
            if not cls.verify_file_sha256(staging_pkg, expected_sha):
                log_audit_event("updater_sha_mismatch", str(staging_pkg), "high", "failed")
                staging_pkg.unlink(missing_ok=True)
                return {"success": False, "error": "Package SHA256 checksum mismatch. Download discarded."}

            # 6. Safe Extraction with ZIP-Slip Defense
            if staging_unpacked.exists():
                shutil.rmtree(staging_unpacked)
            cls.safe_extract_zip(staging_pkg, staging_unpacked)

            # 7. Apply Update Files Atomically
            for root, dirs, files in os.walk(staging_unpacked):
                rel_root = Path(root).relative_to(staging_unpacked)
                dest_dir = settings.BASE_DIR / rel_root
                dest_dir.mkdir(parents=True, exist_ok=True)
                for file in files:
                    src_file = Path(root) / file
                    dest_file = dest_dir / file
                    shutil.copy2(src_file, dest_file)

            cls._record_history("UPDATE_SUCCESS", f"Successfully upgraded to version {version}")
            log_audit_event("apply_update", version, "high", "success")

            return {
                "success": True,
                "version": version,
                "message": f"Update {version} installed successfully. Please restart J.A.R.V.I.S. Workstation."
            }

        except Exception as e:
            print(f"[AutoUpdater] Update failed. Initiating automatic rollback: {e}")
            cls.rollback_to_snapshot(snapshot_path)
            cls._record_history("UPDATE_FAILED_ROLLBACK", str(e))
            return {"success": False, "error": f"Update failed and was rolled back: {str(e)}"}
        finally:
            if staging_pkg.exists():
                staging_pkg.unlink(missing_ok=True)
            if staging_unpacked.exists():
                shutil.rmtree(staging_unpacked, ignore_errors=True)

    @classmethod
    def _record_history(cls, action: str, details: str):
        try:
            records = []
            if UPDATE_HISTORY_FILE.exists():
                try:
                    records = json.loads(UPDATE_HISTORY_FILE.read_text(encoding="utf-8"))
                except Exception:
                    records = []
            records.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "epoch": time.time(),
                "action": action,
                "details": details
            })
            UPDATE_HISTORY_FILE.write_text(json.dumps(records[-100:], indent=2), encoding="utf-8")
        except Exception:
            pass
