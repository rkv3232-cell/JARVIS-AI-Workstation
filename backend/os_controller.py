import os
import re
import shutil
import ctypes
import subprocess
import webbrowser
from typing import Dict, Any, Optional

from .security import (
    action_registry,
    log_audit_event,
    RiskLevel,
    PendingAction
)
from .windows_controller import (
    execute_radio_action,
    send_media_key,
    close_running_app,
    set_windows_theme,
    empty_recycle_bin,
    lock_workstation
)

# Virtual Key Codes for Windows Media Control
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

def set_system_volume_percent(percent: int) -> bool:
    """
    Sets the exact master Windows volume slider (0-100%) natively using pycaw.
    """
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        target_scalar = max(0.0, min(1.0, percent / 100.0))
        vol.SetMasterVolumeLevelScalar(target_scalar, None)
        log_audit_event("set_volume", f"{percent}%", "safe", "success")
        return True
    except Exception as e:
        print(f"[Volume Error pycaw]: {e}")
        return False

def _send_volume_key(vk_code: int, times: int = 1) -> bool:
    try:
        for _ in range(times):
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
        return True
    except Exception:
        return False

# =========================================================================
# 1. WINDOWS SETTINGS URI SCHEMES (ms-settings:)
# =========================================================================
SETTINGS_MAP = {
    # Wi-Fi & Network
    "wifi": ("ms-settings:network-wifi", "वाई-फाई (Wi-Fi) सेटिंग्स"),
    "network": ("ms-settings:network", "नेटवर्क सेटिंग्स"),
    "ethernet": ("ms-settings:network-ethernet", "ईथरनेट सेटिंग्स"),
    "hotspot": ("ms-settings:network-mobilehotspot", "मोबाइल हॉटस्पॉट सेटिंग्स"),
    "vpn": ("ms-settings:network-vpn", "VPN सेटिंग्स"),
    "proxy": ("ms-settings:network-proxy", "प्रॉक्सी सेटिंग्स"),

    # Bluetooth & Devices
    "bluetooth": ("ms-settings:bluetooth", "ब्लूटूथ और डिवाइसेस सेटिंग्स"),
    "printers": ("ms-settings:printers", "प्रिंटर सेटिंग्स"),
    "mouse": ("ms-settings:mousetouchpad", "माउस और टचपैड सेटिंग्स"),

    # Display, Sound, Battery, Storage
    "display": ("ms-settings:display", "स्क्रीन और डिस्प्ले सेटिंग्स"),
    "sound": ("ms-settings:sound", "ऑडियो और साउंड सेटिंग्स"),
    "volume": ("ms-settings:sound", "ऑडियो सेटिंग्स"),
    "battery": ("ms-settings:batterysaver", "बैटरी और पावर सेटिंग्स"),
    "power": ("ms-settings:powersleep", "पावर और स्लीप सेटिंग्स"),
    "sleep": ("ms-settings:powersleep", "पावर और स्लीप सेटिंग्स"),
    "storage": ("ms-settings:storagesense", "स्टोरेज और डिस्क क्लीन सेटिंग्स"),
    "notifications": ("ms-settings:notifications", "नोटिफिकेशन सेटिंग्स"),

    # Personalization & Themes
    "personalization": ("ms-settings:personalization", "पर्सनलाइजेशन सेटिंग्स"),
    "themes": ("ms-settings:themes", "थीम्स सेटिंग्स"),
    "colors": ("ms-settings:colors", "कलर और अपीयरेंस सेटिंग्स"),
    "background": ("ms-settings:personalization-background", "वॉलपेपर और बैकग्राउंड सेटिंग्स"),
    "lock screen": ("ms-settings:lockscreen", "लॉक स्क्रीन सेटिंग्स"),

    # Windows Update, Apps, Privacy, Time
    "update": ("ms-settings:windowsupdate", "विंडोज़ अपडेट (Windows Update)"),
    "windows update": ("ms-settings:windowsupdate", "विंडोज़ अपडेट"),
    "apps": ("ms-settings:appsfeatures", "इंस्टॉल्ड ऐप्स सेटिंग्स"),
    "default apps": ("ms-settings:defaultapps", "डिफ़ॉल्ट ऐप्स सेटिंग्स"),
    "time": ("ms-settings:dateandtime", "तारीख और समय सेटिंग्स"),
    "date": ("ms-settings:dateandtime", "तारीख और समय सेटिंग्स"),
    "privacy": ("ms-settings:privacy", "प्राइवेसी और सिक्योरिटी सेटिंग्स"),

    # Generic Settings Root
    "settings": ("ms-settings:", "विंडोज़ सेटिंग्स (Windows Settings)"),
    "pc settings": ("ms-settings:", "पीसी सेटिंग्स"),
    "system settings": ("ms-settings:", "सिस्टम सेटिंग्स")
}

# =========================================================================
# 2. SYSTEM UTILITIES & ADMINISTRATIVE TOOLS
# =========================================================================
SYSTEM_TOOLS_MAP = {
    "task manager": ("taskmgr.exe", "टास्क मैनेजर (Task Manager)"),
    "taskmgr": ("taskmgr.exe", "टास्क मैनेजर"),
    "control panel": ("control.exe", "कंट्रोल पैनल (Control Panel)"),
    "device manager": ("devmgmt.msc", "डिवाइस मैनेजर (Device Manager)"),
    "disk management": ("diskmgmt.msc", "डिस्क मैनेजमेंट"),
    "services": ("services.msc", "विंडोज़ सर्विसेज (Services)"),
    "registry editor": ("regedit.exe", "रजिस्ट्री एडिटर (Registry Editor)"),
    "regedit": ("regedit.exe", "रजिस्ट्री एडिटर"),
    "system info": ("msinfo32.exe", "सिस्टम इन्फोर्मेशन"),
    "msinfo": ("msinfo32.exe", "सिस्टम इन्फोर्मेशन"),
    "resource monitor": ("resmon.exe", "रिसोर्स मॉनिटर"),
    "performance monitor": ("perfmon.exe", "परफॉर्मेंस मॉनिटर"),
    "event viewer": ("eventvwr.exe", "इवेंट व्यूअर")
}

# =========================================================================
# 3. SPECIAL SHELL FOLDERS (Explorer shortcuts)
# =========================================================================
FOLDERS_MAP = {
    "downloads": ("shell:Downloads", "डाउनलोड्स (Downloads) फोल्डर"),
    "documents": ("shell:Personal", "डॉक्यूमेंट्स (Documents) फोल्डर"),
    "pictures": ("shell:My Pictures", "पिक्चर्स (Pictures) फोल्डर"),
    "videos": ("shell:My Video", "वीडियोज (Videos) फोल्डर"),
    "music": ("shell:My Music", "म्यूजिक (Music) फोल्डर"),
    "desktop folder": ("shell:Desktop", "डेस्कटॉप फोल्डर"),
    "this pc": ("shell:MyComputerFolder", "दिस पीसी (This PC)"),
    "my computer": ("shell:MyComputerFolder", "माई कंप्यूटर"),
    "my pc": ("shell:MyComputerFolder", "माई पीसी"),
    "recycle bin": ("shell:RecycleBinFolder", "रीसायकल बिन (Recycle Bin)")
}

# =========================================================================
# 4. DESKTOP APPLICATIONS MAP
# =========================================================================
APP_MAP = {
    "chrome": "chrome.exe",
    "browser": "chrome.exe",
    "google chrome": "chrome.exe",
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "spotify": "spotify:",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "folder": "explorer.exe",
    "whatsapp": "whatsapp:",
    "discord": "discord:",
    "telegram": "telegram:",
    "vscode": "code.cmd",
    "code": "code.cmd",
    "editor": "code.cmd"
}

# =========================================================================
# 5. WEB SERVICES & TRADING PORTALS
# =========================================================================
URL_MAP = {
    "tradingview": "https://www.tradingview.com",
    "trading view": "https://www.tradingview.com",
    "chart": "https://www.tradingview.com",
    "charts": "https://www.tradingview.com",
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://www.github.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "binance": "https://www.binance.com",
    "zerodha": "https://kite.zerodha.com",
    "kite": "https://kite.zerodha.com",
    "dhan": "https://web.dhan.co",
    "groww": "https://groww.in",
    "upstox": "https://pro.upstox.com",
    "angelone": "https://www.angelone.in",
    "angel": "https://www.angelone.in",
    "sensibull": "https://web.sensibull.com",
    "moneycontrol": "https://www.moneycontrol.com",
    "nse": "https://www.nseindia.com",
    "nseindia": "https://www.nseindia.com",
    "bse": "https://www.bseindia.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "cricbuzz": "https://www.cricbuzz.com",
    "cricinfo": "https://www.espncricinfo.com",
    "espn": "https://www.espncricinfo.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://www.instagram.com",
    "insta": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram web": "https://web.telegram.org"
}

# Devanagari to English phonetic mappings
HINDI_NAME_MAP = {
    "क्रोम": "chrome",
    "यूट्यूब": "youtube",
    "ट्रेडिंगव्यू": "tradingview",
    "ट्रेडिंग": "tradingview",
    "कैलकुलेटर": "calc",
    "नोटपैड": "notepad",
    "गूगल": "google",
    "जीमेल": "gmail",
    "व्हाट्सएप": "whatsapp",
    "टेलीग्राम": "telegram",
    "स्पॉटिफाई": "spotify",
    "जीरोधा": "zerodha",
    "काइट": "zerodha",
    "धन": "dhan",
    "ग्रो": "groww",
    "अपस्टॉक्स": "upstox",
    "टर्मिनल": "terminal",
    "ब्राउज़र": "chrome",
    "सेटिंग्स": "settings",
    "सेटिंग": "settings",
    "वाईफाई": "wifi",
    "वाई-फाई": "wifi",
    "ब्लूटूथ": "bluetooth",
    "टास्क मैनेजर": "task manager",
    "कंट्रोल पैनल": "control panel",
    "डिस्प्ले": "display",
    "डाउनलोड्स": "downloads",
    "डॉक्यूमेंट्स": "documents",
    "रीसायकल बिन": "recycle bin",
    "कचरा": "recycle bin",
    "स्क्रीनशॉट": "screenshot",
    "ब्राइटनेस": "brightness",
    "रोशनी": "brightness",
    "वॉल्यूम": "volume",
    "आवाज": "volume",
    "साउंड": "volume"
}

ACTION_VERBS = [
    "open", "kholo", "khol", "kholiye", "kholna", "open karo", "khol do",
    "chalao", "chala", "chalu", "chalu karo", "chalao ji", "shuru karo",
    "start", "launch", "run", "play", "visit", "go to", "show", "dikhao",
    "खोलो", "खोल", "खोलिए", "खोल दो", "चलाओ", "चला", "चालू करो", "शुरू करो", "दिखाओ"
]

FILLER_WORDS = [
    "karo", "kar", "do", "kariye", "please", "bhai", "jarvis", "ek", "baar",
    "ko", "par", "pe", "me", "mein", "app", "application", "website", "site",
    "mera", "meri", "zara", "jaldi", "system", "pc", "computer", "se",
    "करो", "कर", "दो", "करिए", "प्लीज", "भाई", "जार्विस", "एक", "बार",
    "को", "पर", "पे", "में", "ऐप", "एप्लीकेशन", "वेबसाइट", "साइट",
    "मेरा", "मेरी", "ज़रा", "जल्दी", "सिस्टम", "पीसी", "कंप्यूटर", "से"
]

def _launch_native_target(target: str) -> bool:
    """
    Safely launches URLs, URI schemes, or binaries using os.startfile or shell=False subprocess.
    Avoids shell=True command injection risks.
    """
    try:
        if target.startswith("http://") or target.startswith("https://"):
            webbrowser.open(target)
            return True
        elif target.startswith("ms-settings:") or target.startswith("shell:") or target.endswith(":"):
            os.startfile(target)
            return True
        else:
            exe_path = shutil.which(target) or target
            subprocess.Popen([exe_path], shell=False)
            return True
    except Exception as e:
        # Fallback to os.startfile for registered Windows verbs/extensions
        try:
            os.startfile(target)
            return True
        except Exception as e2:
            print(f"[Safe Launch Error] {target}: {e} / {e2}")
            return False

async def execute_confirmed_action(action: PendingAction) -> Dict[str, Any]:
    """
    Executes a high-impact operation that has received explicit user confirmation.
    Logs result to data/audit_log.json.
    """
    act_type = action.action_type
    params = action.params
    
    try:
        if act_type == "close_app":
            app_name = params.get("app_name", "")
            res = close_running_app(app_name)
            log_audit_event("close_app", app_name, "high", "success" if res.get("success") else "failed", "user", res)
            return res
            
        elif act_type == "empty_recycle_bin":
            res = empty_recycle_bin()
            log_audit_event("empty_recycle_bin", "RecycleBin", "high", "success" if res.get("success") else "failed", "user", res)
            return res
            
        elif act_type == "delete_file":
            file_path = params.get("path", "")
            if os.path.exists(file_path):
                os.remove(file_path)
                res = {"success": True, "message": f"फाइल '{file_path}' हटा दी गई है।"}
                log_audit_event("delete_file", file_path, "high", "success", "user")
                return res
            else:
                res = {"success": False, "message": f"फाइल '{file_path}' नहीं मिली।"}
                log_audit_event("delete_file", file_path, "high", "failed", "user", {"reason": "not_found"})
                return res
                
        elif act_type == "change_theme":
            dark_mode = params.get("dark_mode", True)
            res = set_windows_theme(dark_mode)
            log_audit_event("change_theme", "dark" if dark_mode else "light", "medium", "success", "user")
            return res

        elif act_type == "workflow_execution":
            wf_id = params.get("workflow_id")
            run_id = params.get("run_id")
            from .workflows.workflow_engine import WorkflowEngine
            res = await WorkflowEngine.resume_confirmed_workflow(wf_id, run_id)
            log_audit_event("workflow_execution", wf_id, "high", "success" if res.get("success") else "failed", "user", res)
            return res
            
        return {"success": False, "message": f"अज्ञात कन्फर्मेशन एक्शन प्रकार: {act_type}"}
    except Exception as e:
        log_audit_event(act_type, action.target, "high", "error", "user", error=str(e))
        return {"success": False, "message": f"कार्रवाई निष्पादन में त्रुटि: {str(e)}"}

def execute_os_command(user_query: str) -> Dict[str, Any]:
    """
    Directly executes desktop launch actions with strict safety guards,
    replacing shell=True with os.startfile and registered allowlists.
    High-risk destructive actions trigger a two-step confirmation token.
    """
    raw_cmd = user_query.strip()
    cmd = raw_cmd.lower()

    # Pre-process: Replace Hindi keywords with canonical English keys
    for hi, en in HINDI_NAME_MAP.items():
        if hi in cmd:
            cmd = cmd.replace(hi, en)

    # =========================================================================
    # A. HARDWARE RADIOS (Wi-Fi & Bluetooth ON / OFF)
    # =========================================================================
    wifi_patterns = ["wifi", "wi-fi", "वाईफाई", "वाई-फाई", "internet"]
    bt_patterns = ["bluetooth", "ब्लूटूथ"]

    has_wifi = any(p in cmd for p in wifi_patterns)
    has_bt = any(p in cmd for p in bt_patterns)

    turn_on = any(v in cmd for v in ["on", "start", "enable", "chalu", "chalao", "kholo", "ऑन", "चालू", "खोलो"])
    turn_off = any(v in cmd for v in ["off", "stop", "disable", "band", "roko", "ऑफ", "बंद", "रोको"])
    query_status = any(v in cmd for v in ["status", "check", "batao", "kya hai", "dekho", "स्थिति", "बताओ"])

    if has_wifi or has_bt:
        target_kind = "WiFi" if has_wifi else "Bluetooth"
        if turn_off:
            res = execute_radio_action(target_kind, action="Set", target_state="Off")
            log_audit_event("toggle_radio", f"{target_kind}_Off", "medium", "success")
            return {"status": "success", "message": res["message"]}
        elif turn_on:
            res = execute_radio_action(target_kind, action="Set", target_state="On")
            log_audit_event("toggle_radio", f"{target_kind}_On", "medium", "success")
            return {"status": "success", "message": res["message"]}
        elif query_status:
            res = execute_radio_action(target_kind, action="Get")
            return {"status": "success", "message": res["message"]}

    # =========================================================================
    # B. MULTIMEDIA PLAYBACK CONTROL
    # =========================================================================
    media_words = ["play", "pause", "resume", "stop", "next", "previous", "track", "song", "gana", "video",
                   "अगला", "पिछला", "रोको", "चलाओ", "गाना", "गीत", "बजाओ"]
    if any(mw in cmd for mw in media_words) and any(v in cmd for v in ["gana", "song", "video", "media", "track", "next", "prev", "play", "pause"]):
        res = send_media_key(cmd)
        if res.get("success"):
            return {"status": "success", "message": res["message"]}

    # =========================================================================
    # C. APPLICATION TERMINATION (HIGH RISK -> REQUIRES CONFIRMATION)
    # =========================================================================
    close_words = ["close", "kill", "exit", "band karo", "hatao", "khatam karo", "बंद करो", "हटाओ", "काटो"]
    if any(cw in cmd for cw in close_words):
        for app_key in APP_MAP.keys():
            if app_key in cmd:
                # Register high-risk action for explicit two-step approval
                pending = action_registry.register(
                    action_type="close_app",
                    target=app_key,
                    description=f"Terminate process '{app_key.title()}' ({APP_MAP[app_key]})",
                    risk_level=RiskLevel.HIGH,
                    params={"app_name": app_key},
                    ttl_seconds=60
                )
                log_audit_event("request_close_app", app_key, "high", "pending_confirmation", "system")
                return {
                    "status": "pending_confirmation",
                    "requires_approval": True,
                    "action_id": pending.action_id,
                    "pending_action": pending.to_dict(),
                    "message": f"सुरक्षा पुष्टि आवश्यक: क्या आप सचमुच {app_key.title()} को बंद करना चाहते हैं? (Pending Confirmation ID: {pending.action_id})"
                }

    # =========================================================================
    # D. RECYCLE BIN PURGE (HIGH RISK -> REQUIRES CONFIRMATION)
    # =========================================================================
    bin_words = ["empty recycle bin", "clean recycle bin", "recycle bin khali", "recycle bin saaf", "कचरा पेटी खाली", "रीसायकल बिन खाली"]
    if any(bw in cmd for bw in bin_words):
        pending = action_registry.register(
            action_type="empty_recycle_bin",
            target="RecycleBin",
            description="Permanently delete all files from Windows Recycle Bin",
            risk_level=RiskLevel.HIGH,
            params={},
            ttl_seconds=60
        )
        log_audit_event("request_empty_recycle_bin", "RecycleBin", "high", "pending_confirmation", "system")
        return {
            "status": "pending_confirmation",
            "requires_approval": True,
            "action_id": pending.action_id,
            "pending_action": pending.to_dict(),
            "message": "सुरक्षा पुष्टि आवश्यक: क्या आप सचमुच रीसायकल बिन को पूरी तरह खाली करना चाहते हैं? (Pending Confirmation ID: " + pending.action_id + ")"
        }

    # =========================================================================
    # E. SYSTEM THEME TOGGLE (Dark Mode / Light Mode)
    # =========================================================================
    if "dark mode" in cmd or "डार्क मोड" in cmd:
        res = set_windows_theme(True)
        return {"status": "success", "message": res["message"]}
    elif "light mode" in cmd or "लाइट मोड" in cmd:
        res = set_windows_theme(False)
        return {"status": "success", "message": res["message"]}

    # =========================================================================
    # F. WORKSTATION LOCK
    # =========================================================================
    lock_words = ["lock pc", "lock computer", "lock screen", "pc lock", "स्क्रीन लॉक", "पीसी लॉक"]
    if any(lw in cmd for lw in lock_words):
        res = lock_workstation()
        log_audit_event("lock_pc", "workstation", "safe", "success")
        return {"status": "success", "message": res["message"]}

    # =========================================================================
    # G. VOLUME & AUDIO CONTROL
    # =========================================================================
    vol_match = re.search(r'(?:volume|sound|awaaz|aawaz|आवाज|साउंड)\s*(?:set\s*to\s*|karo\s*|ko\s*)?(\d{1,3})%?', cmd)
    if vol_match:
        val = int(vol_match.group(1))
        if 0 <= val <= 100:
            if set_system_volume_percent(val):
                return {"status": "success", "message": f"जी सर, सिस्टम वॉल्यूम {val}% पर सेट कर दिया गया है।"}

    if any(w in cmd for w in ["mute", "silent", "awaaz band", "आवाज बंद"]):
        _send_volume_key(VK_VOLUME_MUTE)
        log_audit_event("mute_volume", "master", "safe", "success")
        return {"status": "success", "message": "जी सर, वॉल्यूम म्यूट कर दिया गया है।"}

    if any(w in cmd for w in ["unmute", "awaaz kholo"]):
        _send_volume_key(VK_VOLUME_MUTE)
        log_audit_event("unmute_volume", "master", "safe", "success")
        return {"status": "success", "message": "जी सर, वॉल्यूम अनम्यूट कर दिया गया है।"}

    if any(w in cmd for w in ["volume up", "awaaz badhao", "आवाज बढ़ाओ"]):
        _send_volume_key(VK_VOLUME_UP, 4)
        return {"status": "success", "message": "जी सर, वॉल्यूम बढ़ा दिया गया है।"}

    if any(w in cmd for w in ["volume down", "awaaz kam karo", "आवाज कम करो"]):
        _send_volume_key(VK_VOLUME_DOWN, 4)
        return {"status": "success", "message": "जी सर, वॉल्यूम कम कर दिया गया है।"}

    # =========================================================================
    # H. CHECK FOR WINDOWS SETTINGS (ms-settings:) -> Clean os.startfile()
    # =========================================================================
    for s_key, (s_uri, s_name) in SETTINGS_MAP.items():
        if f"{s_key} setting" in cmd or f"{s_key} सेटिंग्स" in cmd or (f"settings" in cmd and s_key in cmd) or (s_key in cmd and any(v in cmd for v in ACTION_VERBS)):
            try:
                os.startfile(s_uri)
                log_audit_event("open_settings", s_uri, "safe", "success")
                return {"status": "success", "message": f"जी सर, {s_name} खोल दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"{s_name} खोलने में त्रुटि: {e}"}

    # If user just asked to open settings generally
    if "settings" in cmd or "setting" in cmd or "सेटिंग" in cmd:
        if any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 2:
            try:
                os.startfile("ms-settings:")
                log_audit_event("open_settings", "ms-settings:", "safe", "success")
                return {"status": "success", "message": "जी सर, विंडोज़ सेटिंग्स खोल दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"सेटिंग्स खोलने में त्रुटि: {e}"}

    # =========================================================================
    # I. CHECK SYSTEM UTILITIES & ADMINISTRATIVE TOOLS
    # =========================================================================
    for tool_key, (tool_target, tool_name) in SYSTEM_TOOLS_MAP.items():
        if tool_key in cmd and (any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 3):
            try:
                _launch_native_target(tool_target)
                log_audit_event("launch_tool", tool_target, "safe", "success")
                return {"status": "success", "message": f"जी सर, {tool_name} खोल दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"{tool_name} शुरू करने में त्रुटि: {e}"}

    # =========================================================================
    # J. CHECK SHELL FOLDERS (Downloads, Documents, This PC, etc.)
    # =========================================================================
    for f_key, (f_uri, f_name) in FOLDERS_MAP.items():
        if f_key in cmd and (any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 3):
            try:
                os.startfile(f_uri)
                log_audit_event("open_folder", f_uri, "safe", "success")
                return {"status": "success", "message": f"जी सर, {f_name} खोल दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"{f_name} खोलने में समस्या: {e}"}

    # Guard against informational questions
    question_words = [
        "who", "what", "why", "how", "when", "where", "which", "whose",
        "kaun", "kya", "kyu", "kyon", "kaise", "kab", "kaha", "kiska", "kitna",
        "कौन", "क्या", "क्यों", "कैसे", "कब", "कहाँ", "किसका", "कितना",
        "ceo", "सीईओ", "batao", "बताओ", "bataiye", "बताइए", "search", "सर्च", "खोजो"
    ]
    if any(re.search(rf'\b{re.escape(qw)}\b', cmd) for qw in question_words):
        return {"status": "not_handled", "message": "Query is a question or search, not an OS launch action."}

    has_action_verb = any(v in cmd for v in ACTION_VERBS)
    tokens = cmd.split()
    is_standalone_app = len(tokens) <= 2 and any(k in cmd for k in list(URL_MAP.keys()) + list(APP_MAP.keys()))

    if not (has_action_verb or is_standalone_app):
        return {"status": "not_handled", "message": "Command not recognized as a desktop action."}

    # Extract clean target by removing action verbs and filler words
    cleaned = cmd
    for word in sorted(ACTION_VERBS + FILLER_WORDS, key=len, reverse=True):
        cleaned = re.sub(rf'\b{re.escape(word)}\b', ' ', cleaned)
    target = re.sub(r'\s+', ' ', cleaned).strip()

    # Special handling for TradingView with specific symbols
    if "tradingview" in target or "chart" in target or "charts" in target:
        if "nifty" in cmd or "निफ्टी" in cmd:
            webbrowser.open("https://www.tradingview.com/chart/?symbol=NSE:NIFTY")
            log_audit_event("open_url", "TradingView:NIFTY", "safe", "success")
            return {"status": "success", "message": "जी सर, निफ्टी का लाइव ट्रेडिंगव्यू चार्ट खोल दिया गया है।"}
        elif "bank" in cmd or "बैंक" in cmd:
            webbrowser.open("https://www.tradingview.com/chart/?symbol=NSE:BANKNIFTY")
            log_audit_event("open_url", "TradingView:BANKNIFTY", "safe", "success")
            return {"status": "success", "message": "जी सर, बैंकनिफ्टी का लाइव ट्रेडिंगव्यू चार्ट खोल दिया गया है।"}
        elif "btc" in cmd or "bitcoin" in cmd or "बिटकॉइन" in cmd:
            webbrowser.open("https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT")
            log_audit_event("open_url", "TradingView:BTCUSDT", "safe", "success")
            return {"status": "success", "message": "जी सर, बिटकॉइन का लाइव चार्ट खोल दिया गया है।"}
        else:
            webbrowser.open("https://www.tradingview.com")
            log_audit_event("open_url", "TradingView", "safe", "success")
            return {"status": "success", "message": "जी सर, ट्रेडिंगव्यू खोल दिया गया है।"}

    # Check against URL_MAP (Websites)
    for key, url in URL_MAP.items():
        if key == target or f" {key} " in f" {target} " or (len(key) >= 4 and key in target):
            webbrowser.open(url)
            log_audit_event("open_url", url, "safe", "success")
            return {"status": "success", "message": f"जी सर, {key.title()} खोल दिया गया है।"}

    # Check against APP_MAP (Desktop Applications)
    for app_key, exe_target in APP_MAP.items():
        if app_key == target or f" {app_key} " in f" {target} " or (len(app_key) >= 4 and app_key in target):
            try:
                if app_key in ["vscode", "code", "editor"]:
                    if not shutil.which("code"):
                        webbrowser.open("https://vscode.dev")
                        log_audit_event("open_url", "https://vscode.dev", "safe", "success")
                        return {"status": "success", "message": "जी सर, VS Code Web एडिटर खोल दिया गया है।"}
                
                _launch_native_target(exe_target)
                log_audit_event("launch_app", exe_target, "medium", "success")
                return {"status": "success", "message": f"जी सर, {app_key.title()} लॉन्च कर दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"{app_key.title()} शुरू करने में समस्या आई: {str(e)}"}

    # Check if target looks like a domain
    domain_match = re.search(r'([a-zA-Z0-9-]+\.(?:com|in|org|net|co|io|ai|tv|app))', cmd)
    if domain_match:
        domain = domain_match.group(1)
        full_url = f"https://{domain}"
        webbrowser.open(full_url)
        log_audit_event("open_url", full_url, "safe", "success")
        return {"status": "success", "message": f"जी सर, {domain} खोल दिया गया है।"}

    # Generic website fallback if user explicitly said 'kholo' or 'open'
    if has_action_verb and target and len(target) >= 3:
        clean_target = re.sub(r'[^a-zA-Z0-9]', '', target)
        if clean_target:
            webbrowser.open(f"https://www.{clean_target}.com")
            log_audit_event("open_url", f"https://www.{clean_target}.com", "safe", "success")
            return {"status": "success", "message": f"जी सर, {clean_target.title()} वेबसाइट खोल दी गई है।"}

    return {"status": "not_handled", "message": "Command not recognized as a desktop action."}

# Backward compatibility alias
execute_os_action = execute_os_command
