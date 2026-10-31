import io
import time
import base64
import asyncio
import json
import pyperclip
import httpx
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image
from .config import settings
from .database import log_conversation

SCREENSHOT_CACHE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "audio_cache"
SCREENSHOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Latest analyzed state cache
_latest_screen_analysis: Dict[str, Any] = {
    "timestamp": 0,
    "text": "लाइव स्क्रीन विज़न मॉनिटर सक्रिय है। आपका स्क्रीन रियल-टाइम में स्ट्रीम हो रहा है।",
    "summary": "Live Screen Vision Stream Active",
    "image_base64": "",
    "trend": "NEUTRAL",
    "active_app": "Trading Dashboard",
    "is_live_stream": True
}

def capture_desktop_image() -> Optional[Image.Image]:
    """
    Captures live desktop image natively on Windows.
    Used as an automatic fallback when WebRTC browser stream is initializing.
    Enforces privacy kill-switch: returns None immediately if screen privacy is engaged.
    """
    from .security import privacy_guard
    if privacy_guard.screen_kill_switch or not settings.ENABLE_SCREEN_VISION:
        return None

    # 1. Try PyAutoGUI
    try:
        import pyautogui
        img = pyautogui.screenshot()
        if img:
            return img
    except Exception:
        pass

    # 2. Try PIL ImageGrab
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if img:
            return img
    except Exception:
        pass

    return None

def image_to_base64_jpeg(image: Image.Image, max_dim: int = 1280) -> str:
    """
    Resizes image preserving aspect ratio and encodes to compressed JPEG base64.
    """
    w, h = image.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        new_w = int(w * scale)
        new_h = int(h * scale)
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Convert RGBA to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")
        
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

async def analyze_screen_with_ai(custom_query: Optional[str] = None, image_base64: Optional[str] = None) -> dict:
    """
    Analyzes live screen video frames in real time.
    Accepts instantaneous WebRTC video frame from the frontend,
    or falls back to high-speed local desktop capture.
    Processes via Gemini 2.5 Flash Multimodal Vision in ~1.2s.
    """
    global _latest_screen_analysis
    from .security import privacy_guard
    if privacy_guard.screen_kill_switch:
        return {
            "success": False,
            "error": "Screen vision is blocked by privacy kill switch.",
            "text": "सर, स्क्रीन विज़न वर्तमान में प्राइवेसी किल स्विच द्वारा अक्षम है।",
            "trend": "BLOCKED"
        }
    
    b64_img = image_base64 or ""
    
    # If frontend didn't supply an active video frame, capture local desktop
    if not b64_img:
        img = capture_desktop_image()
        if img:
            b64_img = image_to_base64_jpeg(img)
    
    # Clean up base64 prefix if passed as data URL
    if b64_img and "," in b64_img:
        b64_img = b64_img.split(",", 1)[1]

    user_prompt = custom_query or "यह ट्रेडर का लाइव स्क्रीन है। स्क्रीन को ध्यान से देखकर 2-3 वाक्यों में शुद्ध, स्पष्ट और संक्षिप्त हिंदी में बताएं कि क्या दिख रहा है। यदि चार्ट है, तो वर्तमान ट्रेंड, प्रमुख सपोर्ट/रेजिस्टेंस और प्राइस एक्शन की स्थिति बताएं।"

    system_instruction = (
        "आप J.A.R.V.I.S. हैं — रियल-टाइम लाइव विज़न और चार्ट एनालाइज़र।\n"
        "यूजर के लाइव स्क्रीन को देखकर उत्तर हमेशा अत्यंत सटीक, पेशेवर और शुद्ध हिंदी (देवनागरी) में दें।\n"
        "यूजर को 'सर' कहकर संबोधित करें। 2 से 3 वाक्यों में स्थिति स्पष्ट करें।"
    )

    # 1. Primary Multimodal Vision: Google Gemini across 3-key pool (Free Tier)
    if settings.gemini_keys_pool and b64_img:
        gemini_models = [settings.MODEL_VISION, "gemini-flash-latest"]
        for k in settings.gemini_keys_pool:
            for g_model in gemini_models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={k}"
                    payload = {
                        "contents": [{
                            "parts": [
                                {"text": f"{system_instruction}\n\nयूजर का निर्देश: {user_prompt}"},
                                {
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": b64_img
                                    }
                                }
                            ]
                        }],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": 180
                        }
                    }
                    async with httpx.AsyncClient(timeout=8.0) as client:
                        res = await client.post(url, json=payload)
                        if res.status_code == 200:
                            data = res.json()
                            analysis_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                            
                            # Infer trend tag
                            trend = "NEUTRAL"
                            low_text = analysis_text.lower()
                            if any(w in low_text for w in ["बुलिश", "तेजी", "bullish", "uptrend", "अपट्रेंड", "बाय"]):
                                trend = "BULLISH"
                            elif any(w in low_text for w in ["बेयरिश", "मंदी", "bearish", "downtrend", "डाउनट्रेंड", "सेल"]):
                                trend = "BEARISH"

                            _latest_screen_analysis = {
                                "timestamp": time.time(),
                                "text": analysis_text,
                                "summary": "Gemini Live Vision Radar",
                                "image_base64": b64_img,
                                "trend": trend,
                                "is_live_stream": True
                            }
                            return _latest_screen_analysis
                        else:
                            print(f"[Vision] {g_model} returned status {res.status_code}")
                except Exception as e:
                    print(f"[Vision] {g_model} error: {e}")

    # 2. Fallback: OpenRouter Multimodal Vision
    if settings.OPENROUTER_API_KEY and b64_img:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:8000"
            }
            payload = {
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{system_instruction}\n\n{user_prompt}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                        ]
                    }
                ],
                "max_tokens": 150
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    text = res.json()["choices"][0]["message"]["content"].strip()
                    _latest_screen_analysis = {
                        "timestamp": time.time(),
                        "text": text,
                        "summary": "OpenRouter Vision Radar",
                        "image_base64": b64_img,
                        "trend": "NEUTRAL",
                        "is_live_stream": True
                    }
                    return _latest_screen_analysis
        except Exception as e:
            print(f"[Vision] OpenRouter error: {e}")

    # 3. Honest Error Fallback when providers fail
    fallback_text = "सर, विज़न AI सेवा अनुपलब्ध होने के कारण स्क्रीन का वास्तविक विश्लेषण नहीं हो सका। कृपया अपनी AI API कुंजी या नेटवर्क कनेक्शन की जाँच करें।"
    _latest_screen_analysis = {
        "timestamp": time.time(),
        "text": fallback_text,
        "summary": "Vision Provider Unavailable",
        "image_base64": b64_img,
        "trend": "UNAVAILABLE",
        "is_live_stream": True,
        "is_fallback": True,
        "success": False
    }
    return _latest_screen_analysis

def get_latest_screen_analysis() -> dict:
    return _latest_screen_analysis

async def detect_chart_patterns_and_overlays(image_base64: Optional[str] = None) -> dict:
    """
    Vision 2.0 Chart Pattern Auto-Detection & Visual Overlay Engine.
    Identifies Support/Resistance lines, Fair Value Gaps (FVG), Order Blocks,
    and Chart Patterns (Head & Shoulders, Double Top/Bottom, Channels).
    Returns structured bounding boxes and levels for direct canvas HUD rendering.
    """
    from .security import privacy_guard
    if privacy_guard.screen_kill_switch:
        return {
            "success": False,
            "error": "Screen vision is blocked by privacy kill switch.",
            "trend": "BLOCKED",
            "summary": "सर, प्राइवेसी किल स्विच सक्रिय होने के कारण चार्ट विजन अवरुद्ध है।",
            "patterns_detected": [],
            "overlays": []
        }

    b64_img = image_base64 or ""
    if not b64_img:
        img = capture_desktop_image()
        if img:
            b64_img = image_to_base64_jpeg(img)
    if b64_img and "," in b64_img:
        b64_img = b64_img.split(",", 1)[1]

    if not b64_img or not settings.GEMINI_API_KEY:
        return {
            "success": False,
            "trend": "NEUTRAL",
            "summary": "सर, स्क्रीन कैप्चर उपलब्ध नहीं है। कृपया लाइव वीडियो स्ट्रीम सक्रिय रखें।",
            "patterns_detected": [],
            "overlays": []
        }

    prompt = """
You are Jarvis Vision 2.0 Chart Pattern Auto-Overlay Analyzer.
Analyze the user's live trading chart screen carefully.
Identify key market structures, support & resistance levels, Fair Value Gaps (FVG), order blocks, and patterns (e.g. Head & Shoulders, Double Bottom/Top, Trendlines, Breakouts).

Output STRICT JSON with this schema:
{
  "trend": "BULLISH" | "BEARISH" | "NEUTRAL",
  "summary": "2 concise respectful sentences in pure Hindi (Devanagari) addressing the user as 'सर'",
  "patterns_detected": ["Fair Value Gap (FVG)", "Key Support Level", "Order Block", ...],
  "overlays": [
    {
      "label": "SUPPORT ~22,600",
      "type": "support" | "resistance" | "fvg" | "order_block" | "pattern",
      "color": "#10b981" | "#f43f5e" | "#38bdf8" | "#eab308",
      "box_percent": [ymin, xmin, ymax, xmax],
      "description": "Short explanation of the zone"
    }
  ]
}
Note: box_percent numbers must be between 0 and 100 representing percentage coordinates on the image.
"""
    for k in settings.gemini_keys_pool:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={k}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                    ]
                }],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            async with httpx.AsyncClient(timeout=35.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    raw_json = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(raw_json)
                    data["success"] = True
                    return data
        except Exception as e:
            print(f"[Vision 2.0] Pattern detection error on key: {e}")

    # Fallback response when provider fails
    return {
        "success": False,
        "trend": "UNAVAILABLE",
        "summary": "सर, विज़न मॉडल अनुपलब्ध होने के कारण चार्ट पैटर्न डिटेक्ट नहीं हो सके। कृपया नेटवर्क या API कुंजी सत्यापित करें।",
        "patterns_detected": [],
        "overlays": [],
        "is_fallback": True
    }

async def extract_screen_text_and_clipboard(image_base64: Optional[str] = None) -> dict:
    """
    Vision 2.0 Instant OCR & Windows Clipboard Engine.
    Extracts visible code blocks, stack traces, errors, or commands from the live screen,
    and directly copies them to the host Windows Clipboard via pyperclip.
    """
    from .security import privacy_guard
    if privacy_guard.screen_kill_switch:
        return {
            "success": False,
            "extracted_text": "",
            "preview": "",
            "char_count": 0,
            "clipboard_copied": False,
            "spoken": "सर, प्राइवेसी किल स्विच सक्रिय होने के कारण स्क्रीन से टेक्स्ट कॉपी नहीं किया जा सकता।"
        }

    b64_img = image_base64 or ""
    if not b64_img:
        img = capture_desktop_image()
        if img:
            b64_img = image_to_base64_jpeg(img)
    if b64_img and "," in b64_img:
        b64_img = b64_img.split(",", 1)[1]

    if not b64_img or not settings.GEMINI_API_KEY:
        return {
            "success": False,
            "text": "",
            "spoken": "सर, स्क्रीन पर टेक्स्ट या कोड डिटेक्ट करने के लिए इमेज उपलब्ध नहीं हो सकी।"
        }

    prompt = """
Extract visible code snippets, error traces, terminal commands, or primary text from this live screen.
Return ONLY the clean extracted text or code that the user would want to paste into their editor or terminal.
Do NOT enclose in markdown commentary or conversational greetings. Just the raw extracted text.
"""
    raw_text = ""
    for k in settings.gemini_keys_pool:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={k}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_img}}
                    ]
                }]
            }
            async with httpx.AsyncClient(timeout=35.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    break
        except Exception as e:
            pass

    if raw_text:
        clipboard_ok = False
        try:
            pyperclip.copy(raw_text)
            clipboard_ok = True
        except Exception as e:
            print(f"[Vision OCR] Clipboard write error: {e}")

        preview = (raw_text[:120] + "...") if len(raw_text) > 120 else raw_text
        if clipboard_ok:
            spoken = "सर, स्क्रीन पर दिख रहा कोड सफलतापूर्वक आपके विंडोज़ क्लिपबोर्ड पर कॉपी कर दिया गया है। आप Ctrl+V दबाकर इसे कहीं भी पेस्ट कर सकते हैं।"
        else:
            spoken = "सर, स्क्रीन से टेक्स्ट निकाल लिया गया है, लेकिन विंडोज़ क्लिपबोर्ड पर कॉपी करने में तकनीकी विफलता हुई।"

        return {
            "success": clipboard_ok,
            "extracted_text": raw_text,
            "preview": preview,
            "char_count": len(raw_text),
            "clipboard_copied": clipboard_ok,
            "spoken": spoken
        }

    return {
        "success": False,
        "extracted_text": "",
        "preview": "",
        "char_count": 0,
        "clipboard_copied": False,
        "spoken": "सर, स्क्रीन से टेक्स्ट कॉपी करने में तकनीकी समस्या आई। कृपया पुनः प्रयास करें।"
    }
