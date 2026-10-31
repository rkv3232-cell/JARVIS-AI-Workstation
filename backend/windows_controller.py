"""
JARVIS Autonomous Windows Master Controller
Enables direct control, toggling (ON/OFF), hardware adjustments,
media control, and process termination across Windows 10/11.
"""

import os
import re
import sys
import ctypes
import shutil
import subprocess
from typing import Dict, Any, Optional

# Virtual Key Codes for Windows Media & Volume Control
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

# =========================================================================
# 1. WINDOWS RUNTIME RADIOS CONTROLLER (Wi-Fi & Bluetooth ON / OFF)
# =========================================================================
RADIO_PS_SCRIPT = r"""
param(
    [string]$TargetKind = "Bluetooth",
    [string]$Action = "Set",      # "Set" or "Get"
    [string]$TargetState = "On"   # "On" or "Off"
)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }[0]

Function AwaitAction($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null

$radios = AwaitAction ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])

$found = $false
foreach ($r in $radios) {
    $kindStr = $r.Kind.ToString().ToLower()
    $nameStr = $r.Name.ToString().ToLower()
    $matchKind = $TargetKind.ToLower()

    if ($kindStr -like "*$matchKind*" -or $nameStr -like "*$matchKind*") {
        $found = $true
        $curr = $r.State.ToString()
        if ($Action -eq "Get") {
            Write-Output "STATUS_$($r.Kind)_$($curr)"
        } else {
            $desired = if ($TargetState -eq "On") { [Windows.Devices.Radios.RadioState]::On } else { [Windows.Devices.Radios.RadioState]::Off }
            $res = AwaitAction ($r.SetStateAsync($desired)) ([Windows.Devices.Radios.RadioAccessStatus])
            Write-Output "RESULT_$($r.Kind)_$($res)_$($TargetState)"
        }
    }
}

if (-not $found) {
    Write-Output "ERROR:RadioNotFound"
}
"""

def execute_radio_action(target_kind: str, action: str = "Set", target_state: str = "On") -> Dict[str, Any]:
    """
    Directly toggles or queries Windows hardware radios (Wi-Fi, Bluetooth)
    via official Windows.Devices.Radios WinRT API.
    """
    try:
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            f"& {{ {RADIO_PS_SCRIPT} }} -TargetKind '{target_kind}' -Action '{action}' -TargetState '{target_state}'"
        ]
        proc = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=8)
        output = proc.stdout.strip()

        if "RESULT_" in output:
            parts = output.split("RESULT_")[1].strip().split("_")
            # parts: [Kind, Status, TargetState]
            kind_name = "वाई-फाई (Wi-Fi)" if "wifi" in target_kind.lower() else "ब्लूटूथ (Bluetooth)"
            state_hi = "चालू (ON)" if target_state.lower() == "on" else "बंद (OFF)"
            return {
                "success": True,
                "kind": target_kind,
                "state": target_state,
                "message": f"जी सर, {kind_name} सफलतापूर्वक {state_hi} कर दिया गया है।"
            }
        elif "STATUS_" in output:
            parts = output.split("STATUS_")[1].strip().split("_")
            curr_state = parts[1] if len(parts) > 1 else "Unknown"
            kind_name = "वाई-फाई (Wi-Fi)" if "wifi" in target_kind.lower() else "ब्लूटूथ (Bluetooth)"
            state_hi = "चालू (ON)" if curr_state.lower() == "on" else "बंद (OFF)"
            return {
                "success": True,
                "kind": target_kind,
                "state": curr_state,
                "message": f"जी सर, वर्तमान में {kind_name} {state_hi} है।"
            }
        elif "RadioNotFound" in output:
            return {
                "success": False,
                "message": f"सिस्टम में {target_kind} रेडियो डिवाइस नहीं मिला।"
            }
        else:
            return {
                "success": False,
                "message": f"रेडियो कमांड निष्पादित करने में असमर्थ: {output or proc.stderr.strip()}"
            }
    except Exception as e:
        return {"success": False, "message": f"रेडियो निष्पादन त्रुटि: {str(e)}"}

# =========================================================================
# 2. MEDIA CONTROLLER (Play / Pause, Next Track, Previous Track)
# =========================================================================
def send_media_key(action: str) -> Dict[str, Any]:
    """
    Simulates native Windows multimedia keyboard events to control playback
    in Chrome (YouTube), Spotify, VLC, or any active media player.
    """
    action_low = action.lower()
    try:
        if any(w in action_low for w in ["play", "pause", "resume", "chalao", "roko", "band karo"]):
            ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 2, 0)
            return {"success": True, "message": "जी सर, मीडिया प्ले/पॉज़ (Play/Pause) टॉगल कर दिया गया है।"}
        elif any(w in action_low for w in ["next", "agla", "change", "badlo"]):
            ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 2, 0)
            return {"success": True, "message": "जी सर, अगला ट्रैक (Next Track) चला दिया गया है।"}
        elif any(w in action_low for w in ["prev", "previous", "pichla", "peeche"]):
            ctypes.windll.user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 2, 0)
            return {"success": True, "message": "जी सर, पिछला ट्रैक (Previous Track) लगा दिया गया है।"}
        elif any(w in action_low for w in ["stop", "ruk"]):
            ctypes.windll.user32.keybd_event(VK_MEDIA_STOP, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MEDIA_STOP, 0, 2, 0)
            return {"success": True, "message": "जी सर, मीडिया प्लेबैक रोक दिया गया है।"}
        return {"success": False, "message": "अमान्य मीडिया कमांड।"}
    except Exception as e:
        return {"success": False, "message": f"मीडिया की भेजने में समस्या: {e}"}

# =========================================================================
# 3. APPLICATION TERMINATION (Close / Kill Process)
# =========================================================================
APP_PROCESS_MAP = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "ब्राउज़र": ["chrome.exe"],
    "notepad": ["notepad.exe"],
    "नोटपैड": ["notepad.exe"],
    "calc": ["CalculatorApp.exe", "calc.exe"],
    "calculator": ["CalculatorApp.exe", "calc.exe"],
    "कैलकुलेटर": ["CalculatorApp.exe", "calc.exe"],
    "vscode": ["Code.exe"],
    "code": ["Code.exe"],
    "vs code": ["Code.exe"],
    "spotify": ["Spotify.exe"],
    "स्पॉटिफाई": ["Spotify.exe"],
    "terminal": ["WindowsTerminal.exe", "cmd.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "task manager": ["Taskmgr.exe"],
    "taskmgr": ["Taskmgr.exe"]
}

def close_running_app(app_name: str) -> Dict[str, Any]:
    """
    Terminates running applications cleanly or forcefully via taskkill.
    """
    app_low = app_name.lower().strip()
    proc_list = None
    for k, v in APP_PROCESS_MAP.items():
        if k in app_low or app_low in k:
            proc_list = v
            break

    if not proc_list:
        # Check if user mentioned exact exe name
        if app_low.endswith(".exe"):
            proc_list = [app_low]
        else:
            return {"success": False, "message": f"'{app_name}' के लिए प्रोसेस मैप नहीं मिला।"}

    killed_any = False
    for p in proc_list:
        res = subprocess.run(["taskkill", "/IM", p, "/F"], capture_output=True, text=True)
        if res.returncode == 0:
            killed_any = True

    if killed_any:
        return {"success": True, "message": f"जी सर, {app_name.title()} सफलतापूर्वक बंद कर दिया गया है।"}
    else:
        return {"success": False, "message": f"जी सर, {app_name.title()} वर्तमान में बैकग्राउंड में नहीं चल रहा था।"}

# =========================================================================
# 4. SYSTEM THEME TOGGLE (Dark Mode / Light Mode)
# =========================================================================
def set_windows_theme(dark_mode: bool) -> Dict[str, Any]:
    """Sets system-wide Windows theme (Apps and System shell)."""
    val = 0 if dark_mode else 1
    theme_name = "डार्क मोड (Dark Mode)" if dark_mode else "लाइट मोड (Light Mode)"
    ps_cmd = f"Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name AppsUseLightTheme -Value {val}; Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name SystemUsesLightTheme -Value {val}"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=5)
        return {"success": True, "message": f"जी सर, विंडोज़ में {theme_name} सक्रिय कर दिया गया है।"}
    except Exception as e:
        return {"success": False, "message": f"थीम बदलने में त्रुटि: {e}"}

# =========================================================================
# 5. RECYCLE BIN SILENT PURGE
# =========================================================================
def empty_recycle_bin() -> Dict[str, Any]:
    """Empties all recycled files silently without prompts."""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"], capture_output=True, timeout=6)
        return {"success": True, "message": "जी सर, रीसायकल बिन को पूरी तरह खाली और साफ़ कर दिया गया है।"}
    except Exception as e:
        return {"success": False, "message": f"रीसायकल बिन खाली करने में त्रुटि: {e}"}

# =========================================================================
# 6. WORKSTATION LOCK
# =========================================================================
def lock_workstation() -> Dict[str, Any]:
    """Locks the Windows user session immediately."""
    try:
        ctypes.windll.user32.LockWorkStation()
        return {"success": True, "message": "जी सर, आपका पीसी लॉक कर दिया गया है।"}
    except Exception as e:
        return {"success": False, "message": f"पीसी लॉक करने में त्रुटि: {e}"}
