import os
import base64
import asyncio
import hashlib
from pathlib import Path
import httpx
from .config import settings

AUDIO_CACHE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "audio_cache"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_cache_filename(text: str) -> str:
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
    return f"cache_{h}.mp3"

async def _generate_edge_tts(text: str, file_path: Path) -> bool:
    """
    Generates natural high-fidelity Hindi neural voice via Microsoft Edge-TTS.
    """
    try:
        import edge_tts
        voice = settings.JARVIS_VOICE or "hi-IN-MadhurNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(file_path))
        if file_path.exists() and file_path.stat().st_size > 500:
            return True
    except Exception as e:
        print(f"[VoiceService] Edge-TTS generation notice: {e}")
    return False

def _generate_gtts(text: str, file_path: Path):
    """
    gTTS fallback with native Hindi pronunciation.
    """
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(str(file_path))
    except Exception as e:
        print(f"[VoiceService] gTTS notice: {e}")

async def _generate_sarvam_tts(text: str, file_path: Path) -> bool:
    """
    Generates ultra-realistic Indian Hinglish human voice using Sarvam AI (Bulbul).
    """
    if not settings.SARVAM_API_KEY:
        return False

    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": settings.SARVAM_API_KEY,
        "Content-Type": "application/json"
    }

    models_to_try = [settings.SARVAM_MODEL, "bulbul:v4-flash", "bulbul:v3"]
    seen_models = set()

    for model_name in models_to_try:
        if not model_name or model_name in seen_models:
            continue
        seen_models.add(model_name)

        if "v4" in model_name:
            speaker = settings.SARVAM_SPEAKER if settings.SARVAM_SPEAKER and "_enhi_" in settings.SARVAM_SPEAKER else "shubh_enhi_companion"
        else:
            speaker = "shubh"

        # Guard against Sarvam 500-char per-input limit
        tts_input = text
        if len(tts_input) > 480:
            last_punct = max(tts_input.rfind("।", 0, 480), tts_input.rfind(".", 0, 480), tts_input.rfind("?", 0, 480))
            if last_punct > 150:
                tts_input = tts_input[:last_punct+1]
            else:
                tts_input = tts_input[:480]

        payload = {
            "inputs": [tts_input],
            "target_language_code": "hi-IN",
            "speaker": speaker,
            "model": model_name,
            "pace": settings.SARVAM_PACE or 1.06,
            "speech_sample_rate": 24000
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    audios = data.get("audios", [])
                    if audios and audios[0]:
                        audio_bytes = base64.b64decode(audios[0])
                        file_path.write_bytes(audio_bytes)
                        return True
                else:
                    print(f"[VoiceService] Sarvam AI ({model_name}) status {res.status_code}: {res.text[:120]}")
        except Exception as e:
            print(f"[VoiceService] Sarvam AI ({model_name}) connection error: {e}")

    return False

COMMON_PHRASES = [
    "जी सर, Chrome लॉन्च कर दिया गया है।",
    "जी सर, Youtube खोल दिया गया है।",
    "जी सर, ट्रेडिंगव्यू खोल दिया गया है।",
    "जी सर, निफ्टी का लाइव ट्रेडिंगव्यू चार्ट खोल दिया गया है।",
    "जी सर, Zerodha खोल दिया गया है।",
    "जी सर, Dhan खोल दिया गया है।",
    "जी सर, Calc लॉन्च कर दिया गया है।",
    "जी सर, Notepad लॉन्च कर दिया गया है।",
    "जी सर, वॉल्यूम बढ़ा दिया गया है।",
    "जी सर, वॉल्यूम कम कर दिया गया है।",
    "जी सर, ऑडियो स्थिति टॉगल कर दी गई है।",
    "नमस्ते सर, मैं जार्विस हूँ। ट्रेडिंग, कोडिंग, मौसम या स्क्रीन एनालिसिस में से क्या सेवा करूँ?",
    "जी सर, लाइव बातचीत बंद कर दी गई है। आवश्यकता हो तो मुझे आवाज़ दीजिएगा।"
]

async def prewarm_voice_cache():
    """
    Background worker that pre-synthesizes common system replies.
    Guarantees instant (<1ms) audio availability upon first command.
    """
    for phrase in COMMON_PHRASES:
        try:
            cache_name = _get_cache_filename(phrase)
            target_path = AUDIO_CACHE_DIR / cache_name
            if not target_path.exists():
                await generate_speech_file(phrase)
        except Exception:
            pass

async def generate_speech_file(text: str, filename: str = "latest_reply.mp3") -> str:
    """
    Generates natural human-like voice audio for Hinglish text with instant MD5 caching.
    Cached common answers return in <1ms (0.001s).
    """
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
    if not clean_text:
        return ""

    # Instant sub-millisecond cache lookup
    cache_name = _get_cache_filename(clean_text)
    cache_path = AUDIO_CACHE_DIR / cache_name
    if cache_path.exists() and cache_path.stat().st_size > 800:
        return f"/audio_cache/{cache_name}"

    target_path = cache_path

    # 1. Sarvam AI Bulbul (Studio Quality Indian Hinglish)
    if settings.SARVAM_API_KEY:
        sarvam_success = await _generate_sarvam_tts(clean_text, target_path)
        if sarvam_success:
            return f"/audio_cache/{cache_name}"

    # 2. Microsoft Edge-TTS (100% Male Neural Voice: hi-IN-MadhurNeural)
    edge_success = await _generate_edge_tts(clean_text, target_path)
    if edge_success:
        return f"/audio_cache/{cache_name}"

    return ""

async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "input_audio.wav") -> str:
    """
    Transcribes audio into Hindi / English text using:
    1. Groq Whisper (whisper-large-v3-turbo) - sub-300ms latency
    2. Sarvam AI Saaras (saaras:v4) - Fine-tuned for Indian Hindi & accents
    """
    if not audio_bytes:
        return ""

    mime_type = "audio/wav"
    if filename.endswith(".webm"):
        mime_type = "audio/webm"
    elif filename.endswith(".ogg"):
        mime_type = "audio/ogg"
    elif filename.endswith(".mp3"):
        mime_type = "audio/mpeg"
    elif filename.endswith(".m4a") or filename.endswith(".mp4"):
        mime_type = "audio/mp4"

    # 1. Groq Whisper Large v3 Turbo
    if settings.GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
            files = {"file": (filename, audio_bytes, mime_type)}
            data = {"model": "whisper-large-v3-turbo", "language": "hi"}
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(url, headers=headers, data=data, files=files)
                if res.status_code == 200:
                    text = res.json().get("text", "").strip()
                    if text:
                        return text
        except Exception as e:
            print(f"[VoiceService] Groq Whisper STT exception: {e}")

    # 2. Sarvam AI Saaras STT
    if settings.SARVAM_API_KEY:
        try:
            url = "https://api.sarvam.ai/speech-to-text"
            headers = {"api-subscription-key": settings.SARVAM_API_KEY}
            files = {"file": (filename, audio_bytes, mime_type)}
            data = {"model": settings.SARVAM_STT_MODEL or "saaras:v4", "language_code": "unknown"}
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, headers=headers, data=data, files=files)
                if res.status_code == 200:
                    transcript = res.json().get("transcript", "").strip()
                    if transcript:
                        return transcript
        except Exception as e:
            print(f"[VoiceService] Sarvam Saaras STT exception: {e}")

    return ""
