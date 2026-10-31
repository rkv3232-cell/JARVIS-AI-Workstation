import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VBS_SCRIPT = BASE_DIR / "scripts" / "create_desktop_shortcut.vbs"

def create_shortcut():
    print(f"Creating Windows Desktop shortcut for J.A.R.V.I.S. APEX...")
    try:
        subprocess.run(["cscript", "//nologo", str(VBS_SCRIPT)], cwd=str(BASE_DIR), check=True)
        print("Shortcut created on Desktop successfully!")
    except Exception as e:
        print(f"Error creating shortcut via cscript: {e}")

if __name__ == "__main__":
    create_shortcut()
