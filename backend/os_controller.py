import os
import re
import shutil
import ctypes
import subprocess
import webbrowser
from typing import Dict, Any
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
    "wifi": ("start ms-settings:network-wifi", "वाई-फाई (Wi-Fi) सेटिंग्स"),
    "network": ("start ms-settings:network", "नेटवर्क सेटिंग्स"),
    "ethernet": ("start ms-settings:network-ethernet", "ईथरनेट सेटिंग्स"),
    "hotspot": ("start ms-settings:network-mobilehotspot", "मोबाइल हॉटस्पॉट सेटिंग्स"),
    "vpn": ("start ms-settings:network-vpn", "VPN सेटिंग्स"),
    "proxy": ("start ms-settings:network-proxy", "प्रॉक्सी सेटिंग्स"),

    # Bluetooth & Devices
    "bluetooth": ("start ms-settings:bluetooth", "ब्लूटूथ और डिवाइसेस सेटिंग्स"),
    "printers": ("start ms-settings:printers", "प्रिंटर सेटिंग्स"),
    "mouse": ("start ms-settings:mousetouchpad", "माउस और टचपैड सेटिंग्स"),

    # Display, Sound, Battery, Storage
    "display": ("start ms-settings:display", "स्क्रीन और डिस्प्ले सेटिंग्स"),
    "sound": ("start ms-settings:sound", "ऑडियो और साउंड सेटिंग्स"),
    "volume": ("start ms-settings:sound", "ऑडियो सेटिंग्स"),
    "battery": ("start ms-settings:batterysaver", "बैटरी और पावर सेटिंग्स"),
    "power": ("start ms-settings:powersleep", "पावर और स्लीप सेटिंग्स"),
    "sleep": ("start ms-settings:powersleep", "पावर और स्लीप सेटिंग्स"),
    "storage": ("start ms-settings:storagesense", "स्टोरेज और डिस्क क्लीन सेटिंग्स"),
    "notifications": ("start ms-settings:notifications", "नोटिफिकेशन सेटिंग्स"),

    # Personalization & Themes
    "personalization": ("start ms-settings:personalization", "पर्सनलाइजेशन सेटिंग्स"),
    "themes": ("start ms-settings:themes", "थीम्स सेटिंग्स"),
    "colors": ("start ms-settings:colors", "कलर और अपीयरेंस सेटिंग्स"),
    "background": ("start ms-settings:personalization-background", "वॉलपेपर और बैकग्राउंड सेटिंग्स"),
    "lock screen": ("start ms-settings:lockscreen", "लॉक स्क्रीन सेटिंग्स"),

    # Windows Update, Apps, Privacy, Time
    "update": ("start ms-settings:windowsupdate", "विंडोज़ अपडेट (Windows Update)"),
    "windows update": ("start ms-settings:windowsupdate", "विंडोज़ अपडेट"),
    "apps": ("start ms-settings:appsfeatures", "इंस्टॉल्ड ऐप्स सेटिंग्स"),
    "default apps": ("start ms-settings:defaultapps", "डिफ़ॉल्ट ऐप्स सेटिंग्स"),
    "time": ("start ms-settings:dateandtime", "तारीख और समय सेटिंग्स"),
    "date": ("start ms-settings:dateandtime", "तारीख और समय सेटिंग्स"),
    "privacy": ("start ms-settings:privacy", "प्राइवेसी और सिक्योरिटी सेटिंग्स"),

    # Generic Settings Root
    "settings": ("start ms-settings:", "विंडोज़ सेटिंग्स (Windows Settings)"),
    "pc settings": ("start ms-settings:", "पीसी सेटिंग्स"),
    "system settings": ("start ms-settings:", "सिस्टम सेटिंग्स")
}

# =========================================================================
# 2. SYSTEM UTILITIES & ADMINISTRATIVE TOOLS
# =========================================================================
SYSTEM_TOOLS_MAP = {
    "task manager": ("taskmgr", "टास्क मैनेजर (Task Manager)"),
    "taskmgr": ("taskmgr", "टास्क मैनेजर"),
    "control panel": ("control", "कंट्रोल पैनल (Control Panel)"),
    "device manager": ("devmgmt.msc", "डिवाइस मैनेजर (Device Manager)"),
    "disk management": ("diskmgmt.msc", "डिस्क मैनेजमेंट"),
    "services": ("services.msc", "विंडोज़ सर्विसेज (Services)"),
    "registry editor": ("regedit", "रजिस्ट्री एडिटर (Registry Editor)"),
    "regedit": ("regedit", "रजिस्ट्री एडिटर"),
    "system info": ("msinfo32", "सिस्टम इन्फोर्मेशन"),
    "msinfo": ("msinfo32", "सिस्टम इन्फोर्मेशन"),
    "resource monitor": ("resmon", "रिसोर्स मॉनिटर"),
    "performance monitor": ("perfmon", "परफॉर्मेंस मॉनिटर"),
    "event viewer": ("eventvwr", "इवेंट व्यूअर")
}

# =========================================================================
# 3. SPECIAL SHELL FOLDERS (Explorer shortcuts)
# =========================================================================
FOLDERS_MAP = {
    "downloads": ("explorer.exe shell:Downloads", "डाउनलोड्स (Downloads) फोल्डर"),
    "documents": ("explorer.exe shell:Personal", "डॉक्यूमेंट्स (Documents) फोल्डर"),
    "pictures": ("explorer.exe shell:My Pictures", "पिक्चर्स (Pictures) फोल्डर"),
    "videos": ("explorer.exe shell:My Video", "वीडियोज (Videos) फोल्डर"),
    "music": ("explorer.exe shell:My Music", "म्यूजिक (Music) फोल्डर"),
    "desktop folder": ("explorer.exe shell:Desktop", "डेस्कटॉप फोल्डर"),
    "this pc": ("explorer.exe shell:MyComputerFolder", "दिस पीसी (This PC)"),
    "my computer": ("explorer.exe shell:MyComputerFolder", "माई कंप्यूटर"),
    "my pc": ("explorer.exe shell:MyComputerFolder", "माई पीसी"),
    "recycle bin": ("explorer.exe shell:RecycleBinFolder", "रीसायकल बिन (Recycle Bin)")
}

# =========================================================================
# 4. DESKTOP APPLICATIONS MAP
# =========================================================================
APP_MAP = {
    "chrome": "start chrome",
    "browser": "start chrome",
    "google chrome": "start chrome",
    "notepad": "notepad",
    "calc": "calc",
    "calculator": "calc",
    "terminal": "start wt || start cmd",
    "cmd": "start cmd",
    "command prompt": "start cmd",
    "powershell": "start powershell",
    "spotify": "start spotify:",
    "explorer": "explorer",
    "files": "explorer",
    "folder": "explorer",
    "whatsapp": "start whatsapp:",
    "discord": "start discord:",
    "telegram": "start telegram:",
    "vscode": "code",
    "code": "code",
    "editor": "code"
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
    "mera", "meri", "humara", "chahiye", "zara", "ki", "ka", "ke",
    "करो", "कर", "दो", "जार्विस", "एप्लिकेशन", "वेबसाइट", "का", "की", "के", "में", "पर"
]

def execute_os_action(command_str: str) -> dict:
    """
    Interprets and executes all Windows PC settings, system utilities,
    applications, websites, themes (dark/light), lock workstation, recycle bin,
    precise volume, and precise screen brightness natively without internet search.
    """
    cmd = command_str.lower().strip()
    
    # 1. Phonetic replacement for Devanagari names
    for h_k, e_v in HINDI_NAME_MAP.items():
        cmd = cmd.replace(h_k, e_v)

    # =========================================================================
    # A0. WI-FI HARDWARE TOGGLE (ON / OFF / STATUS)
    # =========================================================================
    if any(w in cmd for w in ["wifi", "wi-fi", "वाईफाई", "वाई-फाई"]):
        if any(w in cmd for w in [" on", " chalu", " चालू", " ऑन", "enable", "start", "shuru"]):
            res = execute_radio_action("WiFi", action="Set", target_state="On")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}
        elif any(w in cmd for w in [" off", " band", " बंद", " ऑफ", "disable", "stop"]):
            res = execute_radio_action("WiFi", action="Set", target_state="Off")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}
        elif any(w in cmd for w in ["status", "state", "kaisa", "hai ya", "चालू है या", "स्थिति"]):
            res = execute_radio_action("WiFi", action="Get")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}

    # =========================================================================
    # A1. BLUETOOTH HARDWARE TOGGLE (ON / OFF / STATUS)
    # =========================================================================
    if any(w in cmd for w in ["bluetooth", "ब्लूटूथ"]):
        if any(w in cmd for w in [" on", " chalu", " चालू", " ऑन", "enable", "start", "shuru"]):
            res = execute_radio_action("Bluetooth", action="Set", target_state="On")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}
        elif any(w in cmd for w in [" off", " band", " बंद", " ऑफ", "disable", "stop"]):
            res = execute_radio_action("Bluetooth", action="Set", target_state="Off")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}
        elif any(w in cmd for w in ["status", "state", "kaisa", "hai ya", "चालू है या", "स्थिति"]):
            res = execute_radio_action("Bluetooth", action="Get")
            return {"status": "success" if res["success"] else "error", "message": res["message"]}

    # =========================================================================
    # A2. MEDIA CONTROLS (Play, Pause, Next Track, Previous Track)
    # =========================================================================
    media_kw = ["song", "gaana", "music", "video", "track", "गाना", "म्यूजिक", "वीडियो", "प्लेबैक"]
    if any(w in cmd for w in ["next", "agla", "अगला"]) and any(w in cmd for w in media_kw):
        res = send_media_key("next")
        return {"status": "success" if res["success"] else "error", "message": res["message"]}
    elif any(w in cmd for w in ["prev", "previous", "pichla", "पिछला"]) and any(w in cmd for w in media_kw):
        res = send_media_key("prev")
        return {"status": "success" if res["success"] else "error", "message": res["message"]}
    elif any(w in cmd for w in ["play", "pause", "resume", "roko", "chalao"]) and any(w in cmd for w in media_kw):
        res = send_media_key("play")
        return {"status": "success" if res["success"] else "error", "message": res["message"]}

    # =========================================================================
    # A3. APPLICATION TERMINATION (Close / Kill running applications)
    # =========================================================================
    if any(w in cmd for w in ["close", "band karo", "band kar do", "हटाओ", "बंद करो", "काटो"]):
        for app_c in ["chrome", "google chrome", "notepad", "calc", "calculator", "vscode", "code", "vs code", "spotify", "terminal", "cmd", "powershell", "task manager"]:
            if app_c in cmd:
                res = close_running_app(app_c)
                return {"status": "success" if res["success"] else "error", "message": res["message"]}

    # =========================================================================
    # A. WINDOWS THEME CONTROL (Dark Mode / Light Mode)
    # =========================================================================
    if any(k in cmd for k in ["dark mode", "dark theme", "डार्क मोड", "डार्क थीम"]):
        try:
            ps_cmd = 'Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name AppsUseLightTheme -Value 0; Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name SystemUsesLightTheme -Value 0'
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, shell=True)
            return {"status": "success", "message": "जी सर, विंडोज़ में डार्क मोड (Dark Mode) सक्रिय कर दिया गया है।"}
        except Exception as e:
            return {"status": "error", "message": f"डार्क मोड लगाने में त्रुटि: {e}"}

    if any(k in cmd for k in ["light mode", "light theme", "लाइट मोड", "लाइट थीम", "white mode"]):
        try:
            ps_cmd = 'Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name AppsUseLightTheme -Value 1; Set-ItemProperty -Path HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize -Name SystemUsesLightTheme -Value 1'
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, shell=True)
            return {"status": "success", "message": "जी सर, विंडोज़ में लाइट मोड (Light Mode) सक्रिय कर दिया गया है।"}
        except Exception as e:
            return {"status": "error", "message": f"लाइट मोड लगाने में त्रुटि: {e}"}

    # =========================================================================
    # B. LOCK WORKSTATION / SCREEN LOCK
    # =========================================================================
    if any(k in cmd for k in ["lock pc", "lock screen", "screen lock", "pc lock", "सिस्टम लॉक", "स्क्रीन लॉक"]):
        try:
            ctypes.windll.user32.LockWorkStation()
            return {"status": "success", "message": "जी सर, आपके निर्देशानुसार पीसी को लॉक कर दिया गया है।"}
        except Exception as e:
            return {"status": "error", "message": f"पीसी लॉक करने में त्रुटि: {e}"}

    # =========================================================================
    # C. SCREENSHOT / SNIPPING TOOL
    # =========================================================================
    if any(k in cmd for k in ["screenshot", "screen shot", "snipping tool", "snip", "स्क्रीनशॉट"]):
        try:
            subprocess.Popen("explorer.exe ms-screenclip:", shell=True)
            return {"status": "success", "message": "जी सर, स्क्रीनशॉट (Snipping Tool) सक्रिय कर दिया गया है।"}
        except Exception:
            try:
                subprocess.Popen("snippingtool", shell=True)
                return {"status": "success", "message": "जी सर, स्निपिंग टूल खोल दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"स्क्रीनशॉट टूल खोलने में त्रुटि: {e}"}

    # =========================================================================
    # D. RECYCLE BIN (Empty or Open)
    # =========================================================================
    if any(k in cmd for k in ["empty recycle bin", "recycle bin khali", "recycle bin clean", "kachra saaf", "कचरा खाली", "रीसायकल बिन खाली"]):
        try:
            subprocess.run(["powershell", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"], capture_output=True, shell=True)
            return {"status": "success", "message": "जी सर, रीसायकल बिन को पूरी तरह खाली और साफ़ कर दिया गया है।"}
        except Exception as e:
            return {"status": "error", "message": f"रीसायकल बिन खाली करने में त्रुटि: {e}"}

    # =========================================================================
    # E. PRECISE BRIGHTNESS CONTROL (Specific Percent & Up/Down)
    # =========================================================================
    has_bright_word = any(w in cmd for w in ["brightness", "roshni", "ब्राइटनेस", "रोशनी"])
    if has_bright_word:
        m_b = re.search(r'(\d{1,3})\s*%', cmd) or re.search(r'(?:brightness|roshni|ब्राइटनेस|रोशनी)\s*(?:ko|to|pe|par|karo|set)?\s*(\d{1,3})', cmd)
        if m_b:
            target_bright = int(m_b.group(1))
            if 0 <= target_bright <= 100:
                try:
                    import screen_brightness_control as sbc
                    sbc.set_brightness(target_bright)
                    return {"status": "success", "message": f"जी सर, स्क्रीन ब्राइटनेस {target_bright}% पर सेट कर दी गई है।"}
                except Exception as e:
                    return {"status": "error", "message": f"ब्राइटनेस {target_bright}% करने में त्रुटि: {e}"}

        bright_up_keys = ["up", "increase", "badhao", "बढ़ाओ", "high"]
        if any(k in cmd for k in bright_up_keys):
            try:
                import screen_brightness_control as sbc
                curr = sbc.get_brightness()[0]
                target_b = min(100, curr + 15)
                sbc.set_brightness(target_b)
                return {"status": "success", "message": f"जी सर, ब्राइटनेस {target_b}% कर दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"ब्राइटनेस बढ़ाने में त्रुटि: {e}"}

        bright_down_keys = ["down", "decrease", "lower", "kam karo", "kam", "कम करो", "कम"]
        if any(k in cmd for k in bright_down_keys):
            try:
                import screen_brightness_control as sbc
                curr = sbc.get_brightness()[0]
                target_b = max(10, curr - 15)
                sbc.set_brightness(target_b)
                return {"status": "success", "message": f"जी सर, ब्राइटनेस {target_b}% कर दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"ब्राइटनेस घटाने में त्रुटि: {e}"}

    # =========================================================================
    # F. ABSOLUTE VOLUME PERCENTAGE CONTROL
    # =========================================================================
    has_vol_word = any(w in cmd for w in ["volume", "velome", "volum", "volme", "valume", "sound", "awaz", "आवाज", "वॉल्यूम"])
    if has_vol_word:
        m_v = re.search(r'(\d{1,3})\s*%', cmd) or re.search(r'(?:volume|velome|volum|volme|valume|sound|awaz|आवाज|वॉल्यूम)\s*(?:ko|to|pe|par|karo|set)?\s*(\d{1,3})', cmd)
        if m_v:
            target_pct = int(m_v.group(1))
            if 0 <= target_pct <= 100:
                if set_system_volume_percent(target_pct):
                    return {"status": "success", "message": f"जी सर, सिस्टम वॉल्यूम {target_pct}% पर सेट कर दिया गया है।"}
                return {"status": "error", "message": f"वॉल्यूम {target_pct}% पर सेट करने में त्रुटि आई।"}

        # Relative Volume Controls (Up / Down / Mute)
        vol_up_keys = ["up", "increase", "badhao", "बढ़ाओ", "high"]
        if any(k in cmd for k in vol_up_keys):
            if _send_volume_key(VK_VOLUME_UP, 5):
                return {"status": "success", "message": "जी सर, वॉल्यूम बढ़ा दिया गया है।"}
            return {"status": "error", "message": "वॉल्यूम बढ़ाने में त्रुटि आई।"}

        vol_down_keys = ["down", "decrease", "lower", "kam karo", "kam", "कम करो", "कम"]
        if any(k in cmd for k in vol_down_keys):
            if _send_volume_key(VK_VOLUME_DOWN, 5):
                return {"status": "success", "message": "जी सर, वॉल्यूम कम कर दिया गया है।"}
            return {"status": "error", "message": "वॉल्यूम कम करने में त्रुटि आई।"}

        mute_keys = ["mute", "unmute", "band karo", "बंद करो", "म्यूट"]
        if any(k in cmd for k in mute_keys):
            if _send_volume_key(VK_VOLUME_MUTE, 1):
                return {"status": "success", "message": "जी सर, ऑडियो म्यूट / अनम्यूट टॉगल कर दी गई है।"}
            return {"status": "error", "message": "म्यूट करने में त्रुटि आई।"}

    # =========================================================================
    # F.2 OPEN LATEST CYBER / WEB INTELLIGENCE PDF REPORT
    # =========================================================================
    report_open_keys = ["open report", "open pdf", "रिपोर्ट खोलो", "पीडीएफ खोलो", "show report", "pdf खोलो", "latest report"]
    if any(k in cmd for k in report_open_keys):
        from pathlib import Path
        rep_dir = Path(__file__).resolve().parent.parent / "frontend" / "reports"
        if rep_dir.exists():
            pdfs = sorted(rep_dir.glob("*.pdf"), key=os.path.getmtime, reverse=True)
            if pdfs:
                latest_pdf = str(pdfs[0])
                try:
                    os.startfile(latest_pdf)
                    return {"status": "success", "message": f"जी सर, नवीनतम इंटेलिजेंस रिपोर्ट '{pdfs[0].name}' आपके कंप्यूटर पर खोल दी गई है।"}
                except Exception as e:
                    return {"status": "error", "message": f"रिपोर्ट खोलने में त्रुटि: {e}"}
        return {"status": "error", "message": "सर, अभी तक कोई पीडीएफ रिपोर्ट जनरेट नहीं हुई है।"}

    # =========================================================================
    # G. DIRECT FULL URLS (http / https)
    # =========================================================================
    url_match = re.search(r'(https?://[^\s]+)', cmd)
    if url_match:
        inspect_words = ["check", "analyze", "report", "detail", "fraud", "scam", "fake", "kya", "kaisa", "सुरक्षित", "चेक", "रिपोर्ट", "विवरण"]
        open_verbs = ["open", "kholo", "chalao", "browse", "visit", "खोलो", "चलाओ"]
        if not any(w in cmd for w in inspect_words) and (any(v in cmd for v in open_verbs) or cmd.strip() == url_match.group(1)):
            target_url = url_match.group(1)
            webbrowser.open(target_url)
            return {"status": "success", "message": f"जी सर, {target_url} ब्राउज़र में खोल दिया गया है।"}

    # =========================================================================
    # H. CHECK FOR WINDOWS SETTINGS (ms-settings:)
    # =========================================================================
    for s_key, (s_cmd, s_name) in SETTINGS_MAP.items():
        if f"{s_key} setting" in cmd or f"{s_key} सेटिंग्स" in cmd or (f"settings" in cmd and s_key in cmd) or (s_key in cmd and any(v in cmd for v in ACTION_VERBS)):
            try:
                subprocess.Popen(s_cmd, shell=True)
                return {"status": "success", "message": f"जी सर, {s_name} खोल दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"{s_name} खोलने में त्रुटि: {e}"}

    # If user just asked to open settings generally ("settings kholo", "open settings", "सेटिंग्स")
    if "settings" in cmd or "setting" in cmd or "सेटिंग" in cmd:
        if any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 2:
            try:
                subprocess.Popen("start ms-settings:", shell=True)
                return {"status": "success", "message": "जी सर, विंडोज़ सेटिंग्स खोल दी गई है।"}
            except Exception as e:
                return {"status": "error", "message": f"सेटिंग्स खोलने में त्रुटि: {e}"}

    # =========================================================================
    # I. CHECK SYSTEM UTILITIES & ADMINISTRATIVE TOOLS
    # =========================================================================
    for tool_key, (tool_cmd, tool_name) in SYSTEM_TOOLS_MAP.items():
        if tool_key in cmd and (any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 3):
            try:
                subprocess.Popen(tool_cmd, shell=True)
                return {"status": "success", "message": f"जी सर, {tool_name} खोल दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"{tool_name} शुरू करने में त्रुटि: {e}"}

    # =========================================================================
    # J. CHECK SHELL FOLDERS (Downloads, Documents, This PC, etc.)
    # =========================================================================
    for f_key, (f_cmd, f_name) in FOLDERS_MAP.items():
        if f_key in cmd and (any(v in cmd for v in ACTION_VERBS) or len(cmd.split()) <= 3):
            try:
                subprocess.Popen(f_cmd, shell=True)
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
            return {"status": "success", "message": "जी सर, निफ्टी का लाइव ट्रेडिंगव्यू चार्ट खोल दिया गया है।"}
        elif "bank" in cmd or "बैंक" in cmd:
            webbrowser.open("https://www.tradingview.com/chart/?symbol=NSE:BANKNIFTY")
            return {"status": "success", "message": "जी सर, बैंकनिफ्टी का लाइव ट्रेडिंगव्यू चार्ट खोल दिया गया है।"}
        elif "btc" in cmd or "bitcoin" in cmd or "बिटकॉइन" in cmd:
            webbrowser.open("https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT")
            return {"status": "success", "message": "जी सर, बिटकॉइन का लाइव चार्ट खोल दिया गया है।"}
        else:
            webbrowser.open("https://www.tradingview.com")
            return {"status": "success", "message": "जी सर, ट्रेडिंगव्यू खोल दिया गया है।"}

    # Check against URL_MAP (Websites)
    for key, url in URL_MAP.items():
        if key == target or f" {key} " in f" {target} " or (len(key) >= 4 and key in target):
            webbrowser.open(url)
            return {"status": "success", "message": f"जी सर, {key.title()} खोल दिया गया है।"}

    # Check against APP_MAP (Desktop Applications)
    for app_key, run_cmd in APP_MAP.items():
        if app_key == target or f" {app_key} " in f" {target} " or (len(app_key) >= 4 and app_key in target):
            try:
                if app_key in ["vscode", "code", "editor"]:
                    if not shutil.which("code"):
                        webbrowser.open("https://vscode.dev")
                        return {"status": "success", "message": "जी सर, VS Code Web एडिटर खोल दिया गया है।"}
                
                subprocess.Popen(run_cmd, shell=True)
                return {"status": "success", "message": f"जी सर, {app_key.title()} लॉन्च कर दिया गया है।"}
            except Exception as e:
                return {"status": "error", "message": f"{app_key.title()} शुरू करने में समस्या आई: {str(e)}"}

    # Check if target looks like a domain
    domain_match = re.search(r'([a-zA-Z0-9-]+\.(?:com|in|org|net|co|io|ai|tv|app))', cmd)
    if domain_match:
        domain = domain_match.group(1)
        full_url = f"https://{domain}"
        webbrowser.open(full_url)
        return {"status": "success", "message": f"जी सर, {domain} खोल दिया गया है।"}

    # Generic website fallback if user explicitly said 'kholo' or 'open'
    if has_action_verb and target and len(target) >= 3:
        clean_target = re.sub(r'[^a-zA-Z0-9]', '', target)
        if clean_target:
            webbrowser.open(f"https://www.{clean_target}.com")
            return {"status": "success", "message": f"जी सर, {clean_target.title()} वेबसाइट खोल दी गई है।"}

    return {"status": "not_handled", "message": "Command not recognized as a desktop action."}
