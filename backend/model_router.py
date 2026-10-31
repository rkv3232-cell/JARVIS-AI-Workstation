"""
J.A.R.V.I.S. Specialized Free AI Model Router & Multi-Key Pool Manager
======================================================================
Routes every distinct workstation task to the absolute best 100% FREE AI model.
Features automatic multi-key probing for Gemini 3.8 and intelligent load-balancing.

Task-to-Model Specialization Architecture:
------------------------------------------
1. Voice Chat & Conversational Hindi -> Groq LPU: qwen/qwen3.8-27b (~300ms, best Indic/Hindi fluency)
2. Coding, Python & Scripting         -> Gemini 3.8 Flash (if active on any key) -> Else Default: Groq 120B
3. Deep Logic, Math & Reasoning      -> Groq LPU: openai/gpt-oss-120b (Chain of thought reasoning tokens)
4. Multimodal Screen Vision & OCR    -> Google Gemini: gemini-3.5-flash-lite across 3-key pool
5. Fact Verification & Anti-Hallucination -> Groq LPU: openai/gpt-oss-120b + Google Gemini
6. Deep Research Monograph Writing    -> Google Gemini across 3-key pool (Structured JSON)
7. Voice Research Summary Synthesis  -> Groq LPU: qwen/qwen3.8-27b (Natural spoken cadence for TTS)
8. Speech-to-Text (STT)               -> Groq: whisper-large-v3-turbo (Sub-second audio transcription)
9. Text-to-Speech (TTS)               -> Sarvam AI: bulbul:v3 / Edge-TTS hi-IN-MadhurNeural
"""

import json
import re
import time
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from .config import settings

# ---------------------------------------------------------------------------
# Task-to-Model Catalog
# ---------------------------------------------------------------------------
TASK_MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "voice_chat": {
        "task_name": "Ultra-Fast Conversational Voice Chat & Hindi Interaction",
        "primary_model": "qwen/qwen3.8-27b",
        "provider": "Groq LPU",
        "is_free": True,
        "description": "Sub-300ms latency, native Devanagari Hindi fluency, polite and natural cadence for TTS audio.",
        "fallbacks": ["gemini-3.5-flash-lite", "sarvam-2b"]
    },
    "coding": {
        "task_name": "Software Engineering, Python, Scripting & Code Debugging",
        "primary_model": "Google Gemini (gemini-3.8-flash / gemini-3.5-flash-lite / gemini-3-flash)",
        "provider": "Google Gemini Multi-Key Pool (Dedicated)",
        "is_free": True,
        "description": "Dedicated Google Gemini coding engine running across all 3 API keys with auto-failover (Gemini 3.8 -> Gemini 3.5 Flash Lite -> Gemini 3 Flash).",
        "fallbacks": ["openai/gpt-oss-120b (Emergency Backup)"]
    },
    "deep_reasoning": {
        "task_name": "Complex Mathematical Proofs, Logic & Multi-Step Reasoning",
        "primary_model": "openai/gpt-oss-120b",
        "provider": "Groq LPU",
        "is_free": True,
        "description": "Generates explicit chain-of-thought ('reasoning') tokens for step-by-step mathematical and logical deductions.",
        "fallbacks": ["openai/gpt-oss-20b"]
    },
    "screen_vision": {
        "task_name": "Multimodal Desktop Vision, TradingView Charts & Screen OCR",
        "primary_model": "gemini-3.5-flash-lite (Multi-Key Pool)",
        "provider": "Google Gemini (Free Tier)",
        "is_free": True,
        "description": "High-resolution multimodal visual spatial comprehension across 3 auto-rotating keys, chart candlestick analysis, and screen text extraction.",
        "fallbacks": ["nvidia/nemotron-3.5-super-vl:free"]
    },
    "fact_verification": {
        "task_name": "Cross-Source Fact Checking & Consensus Anti-Hallucination",
        "primary_model": "openai/gpt-oss-120b",
        "provider": "Groq LPU + Google Gemini",
        "is_free": True,
        "description": "Strict truth-table comparison against independent source snippets with zero-hallucination confidence scoring.",
        "fallbacks": ["gemini-3.5-flash-lite"]
    },
    "research_monograph": {
        "task_name": "Long-Form Academic Monograph Writing & Structured Tables",
        "primary_model": "gemini-3.5-flash-lite (Multi-Key Pool)",
        "provider": "Google Gemini (Free Tier)",
        "is_free": True,
        "description": "Massive context window across 3 keys, structured JSON schema output, formal academic synthesis with citations [1], [2].",
        "fallbacks": ["openai/gpt-oss-120b"]
    },
    "research_voice_summary": {
        "task_name": "Executive Spoken Research Brief for Voice TTS",
        "primary_model": "qwen/qwen3.8-27b",
        "provider": "Groq LPU",
        "is_free": True,
        "description": "Condenses 5-page research findings into a natural, respectful 60-90 word spoken brief for instant audio playback.",
        "fallbacks": ["gemini-3.5-flash-lite"]
    },
    "speech_to_text": {
        "task_name": "Speech Recognition & Voice Input Transcription (STT)",
        "primary_model": "whisper-large-v3-turbo",
        "provider": "Groq LPU",
        "is_free": True,
        "description": "Fastest Whisper architecture for Hindi and English voice recognition.",
        "fallbacks": ["saaras:v4"]
    },
    "text_to_speech": {
        "task_name": "Spoken Voice Synthesis (TTS)",
        "primary_model": "bulbul:v3 / Edge-TTS",
        "provider": "Sarvam AI / Microsoft Edge",
        "is_free": True,
        "description": "Lifelike natural Indian Hindi voice (hi-IN-MadhurNeural / Shubh).",
        "fallbacks": ["gtts"]
    }
}

# ---------------------------------------------------------------------------
# Circuit Breaker & Provider Health Telemetry
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """
    Prevents cascading failures and high latencies by temporarily opening
    the circuit after repeated provider errors (429 rate limit or timeouts).
    """
    def __init__(self, name: str, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.total_requests = 0
        self.successful_requests = 0
        self.total_latency_ms = 0.0

    def can_attempt(self) -> bool:
        now = time.time()
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if now - self.last_failure_time >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return True

    def record_success(self, latency_ms: float):
        self.failure_count = 0
        self.state = "CLOSED"
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency_ms += latency_ms

    def record_failure(self, error: Any = None):
        self.total_requests += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            print(f"[CircuitBreaker] Provider '{self.name}' tripped OPEN for {self.cooldown_seconds}s due to repeated errors ({error}).")

    def get_metrics(self) -> Dict[str, Any]:
        avg_latency = round(self.total_latency_ms / self.successful_requests, 1) if self.successful_requests > 0 else 0
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "avg_latency_ms": avg_latency,
            "last_failure_time": self.last_failure_time
        }

CIRCUITS = {
    "gemini": CircuitBreaker("Google Gemini Pool", failure_threshold=3, cooldown_seconds=60.0),
    "groq": CircuitBreaker("Groq LPU", failure_threshold=3, cooldown_seconds=60.0),
    "openrouter": CircuitBreaker("OpenRouter", failure_threshold=3, cooldown_seconds=60.0),
    "sarvam": CircuitBreaker("Sarvam AI", failure_threshold=3, cooldown_seconds=60.0),
    "ollama": CircuitBreaker("Ollama Local", failure_threshold=2, cooldown_seconds=30.0)
}

def get_model_telemetry() -> Dict[str, Any]:
    """Returns telemetry for all AI provider circuit breakers and model routing."""
    return {
        "circuits": {k: cb.get_metrics() for k, cb in CIRCUITS.items()},
        "gemini_38_status": get_gemini_38_probe_status(),
        "catalog": TASK_MODEL_REGISTRY
    }

async def route_ollama_fallback(
    messages: List[Dict[str, str]],
    system_prompt: str,
    max_tokens: int = 250
) -> Optional[str]:
    """
    Offline/Emergency Fallback: Queries local Ollama instance if available.
    Ensures J.A.R.V.I.S. remains responsive even during complete internet or cloud outages.
    """
    cb = CIRCUITS["ollama"]
    if not cb.can_attempt():
        return None

    t0 = time.perf_counter()
    try:
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "options": {"num_predict": max_tokens, "temperature": 0.3},
            "stream": False
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                txt = res.json().get("message", {}).get("content", "").strip()
                if txt:
                    cb.record_success((time.perf_counter() - t0) * 1000)
                    return f"*(Ollama Local Private LLM)* {txt}"
            cb.record_failure(f"HTTP_{res.status_code}")
    except Exception as e:
        cb.record_failure(e)
    return None

def get_model_catalog() -> Dict[str, Dict[str, Any]]:
    """Returns the complete task-to-model specialization catalog."""
    return TASK_MODEL_REGISTRY

def clean_json_str(text: str) -> Optional[Dict[str, Any]]:
    """Robustly extracts and parses JSON dictionary from LLM response."""
    if not text:
        return None
    text = re.sub(r'^```json\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'^```\s*', '', text.strip(), flags=re.MULTILINE)
    text = text.rstrip('`').strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    s = text.find('{')
    e = text.rfind('}')
    if s != -1 and e != -1 and e > s:
        try:
            data = json.loads(text[s:e+1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None

# ---------------------------------------------------------------------------
# Dynamic Gemini 3.8 Probing & Multi-Key Pool Manager
# ---------------------------------------------------------------------------
_gemini_38_cache = {
    "active_key": None,
    "key_label": None,
    "last_checked": 0.0,
    "is_available": False,
    "details": {}
}

async def probe_gemini_38_active_key(force_refresh: bool = False) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Checks all 3 Gemini API keys concurrently to determine if 'gemini-3.8-flash'
    is accessible and has active quota.
    Caches the status for 90 seconds to eliminate per-turn query latency.
    Returns: (is_available, active_key, key_label)
    """
    now = time.time()
    if not force_refresh and (now - _gemini_38_cache["last_checked"] < 90.0):
        return _gemini_38_cache["is_available"], _gemini_38_cache["active_key"], _gemini_38_cache["key_label"]

    key_candidates = []
    if settings.GEMINI_API_KEY:
        key_candidates.append(("Key 0 (Primary)", settings.GEMINI_API_KEY))
    if settings.GEMINI_API_KEY_1:
        key_candidates.append(("Key 1 (Secondary)", settings.GEMINI_API_KEY_1))
    if settings.GEMINI_API_KEY_2:
        key_candidates.append(("Key 2 (Tertiary)", settings.GEMINI_API_KEY_2))

    if not key_candidates:
        _gemini_38_cache.update({"active_key": None, "key_label": None, "last_checked": now, "is_available": False})
        return False, None, None

    async def _probe_single(lbl: str, k: str):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={k}"
        try:
            async with httpx.AsyncClient(timeout=3.8) as client:
                res = await client.post(url, json={"contents": [{"parts": [{"text": "1"}]}]})
                if res.status_code == 200:
                    return lbl, k, True, "200 OK (Active)"
                err = res.json().get("error", {}).get("message", f"Status {res.status_code}")[:60]
                return lbl, k, False, f"{res.status_code}: {err}"
        except Exception as e:
            return lbl, k, False, f"Error: {type(e).__name__}"

    results = await asyncio.gather(*[_probe_single(lbl, k) for lbl, k in key_candidates])
    details = {}
    active_key = None
    active_label = None

    for lbl, k, ok, msg in results:
        details[lbl] = msg
        if ok and not active_key:
            active_key = k
            active_label = lbl

    is_avail = bool(active_key)
    if is_avail:
        print(f"[ModelRouter] Gemini 3.8 Model DETECTED & ACTIVE on {active_label}! Coding routed to Gemini 3.8 Flash.")
    else:
        print(f"[ModelRouter] Gemini 3.8 check across 3 keys: {details}. Falling back to default coding engine.")

    _gemini_38_cache.update({
        "active_key": active_key,
        "key_label": active_label,
        "last_checked": now,
        "is_available": is_avail,
        "details": details
    })
    return is_avail, active_key, active_label

def get_gemini_38_probe_status() -> Dict[str, Any]:
    """Returns the latest status of Gemini 3.8 across the 3 API keys."""
    return {
        "is_available": _gemini_38_cache["is_available"],
        "active_key_label": _gemini_38_cache["key_label"],
        "key_details": _gemini_38_cache.get("details", {}),
        "last_checked_seconds_ago": int(time.time() - _gemini_38_cache["last_checked"]) if _gemini_38_cache["last_checked"] else None
    }

# ---------------------------------------------------------------------------
# Specialized Asynchronous Task Callers
# ---------------------------------------------------------------------------

async def route_chat_voice(
    messages: List[Dict[str, str]],
    system_prompt: str,
    max_tokens: int = 150
) -> Optional[str]:
    """
    Task 1: Ultra-Fast Conversational Voice Chat.
    Uses Groq qwen/qwen3.8-27b for ~300ms response with world-class Hindi voice tone.
    Protected by CircuitBreakers with automated fallback down to local private Ollama.
    """
    t0 = time.perf_counter()

    # 1. Primary: Groq Qwen 27B
    cb_groq = CIRCUITS["groq"]
    if settings.GROQ_API_KEY and cb_groq.can_attempt():
        try:
            async with httpx.AsyncClient(timeout=3.5) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    json={
                        "model": settings.MODEL_CHAT,
                        "messages": [{"role": "system", "content": system_prompt}, *messages],
                        "max_tokens": max_tokens,
                        "temperature": 0.25
                    }
                )
                if res.status_code == 200:
                    cnt = res.json()["choices"][0]["message"]["content"]
                    if cnt and cnt.strip():
                        cb_groq.record_success((time.perf_counter() - t0) * 1000)
                        return cnt.strip()
                else:
                    cb_groq.record_failure(f"HTTP_{res.status_code}")
        except Exception as e:
            cb_groq.record_failure(e)
            print(f"[ModelRouter] Chat Groq notice: {e}")

    # 2. Fallback: Google Gemini across Key Pool
    cb_gemini = CIRCUITS["gemini"]
    if cb_gemini.can_attempt():
        for k in settings.gemini_keys_pool:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={k}"
                history_text = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages])
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{history_text}"}]}],
                    "generationConfig": {"temperature": 0.25, "maxOutputTokens": max_tokens}
                }
                async with httpx.AsyncClient(timeout=4.5) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        cb_gemini.record_success((time.perf_counter() - t0) * 1000)
                        return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    else:
                        cb_gemini.record_failure(f"HTTP_{res.status_code}")
            except Exception as e:
                cb_gemini.record_failure(e)

    # 3. Fallback: Sarvam Indic LLM
    cb_sarvam = CIRCUITS["sarvam"]
    if settings.SARVAM_API_KEY and cb_sarvam.can_attempt():
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.post(
                    "https://api.sarvam.ai/v1/chat/completions",
                    headers={
                        "api-subscription-key": settings.SARVAM_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sarvam-2b",
                        "messages": [{"role": "system", "content": system_prompt}, *messages],
                        "max_tokens": max_tokens
                    }
                )
                if res.status_code == 200:
                    cnt = res.json()["choices"][0]["message"]["content"]
                    if cnt and cnt.strip():
                        cb_sarvam.record_success((time.perf_counter() - t0) * 1000)
                        return cnt.strip()
                else:
                    cb_sarvam.record_failure(f"HTTP_{res.status_code}")
        except Exception as e:
            cb_sarvam.record_failure(e)
            print(f"[ModelRouter] Chat Sarvam notice: {e}")

    # 4. Final Offline Fallback: Local Private Ollama
    local_reply = await route_ollama_fallback(messages, system_prompt, max_tokens)
    if local_reply:
        return local_reply

    return None

async def route_coding(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 850
) -> Optional[str]:
    """
    Task 2: Coding, Software Engineering & Scripting.
    First dynamically probes the 3 Gemini API keys for 'gemini-3.8-flash'.
    If active on any key -> Executes via Gemini 3.8 Flash!
    If inactive or rate-limited on all 3 -> Seamlessly falls back to Default:
      1) Groq LPU: openai/gpt-oss-120b (120B reasoning open model)
      2) Groq LPU: qwen/qwen3.8-27b
      3) Google Gemini: gemini-3.5-flash-lite across the 3 keys
    """
    sys = system_prompt or (
        "आप J.A.R.V.I.S. सीनियर सॉफ्टवेयर इंजीनियर और पायथन/कोडिंग विशेषज्ञ हैं।\n"
        "यूजर के कोडिंग सवाल का सबसे स्वच्छ, सटीक और कुशल कोड समाधान प्रदान करें।\n"
        "नियम:\n"
        "1. उत्तर में मुख्य कोड ब्लॉक स्पष्ट रूप से ``` भाषा टैग के साथ दें।\n"
        "2. संक्षिप्त स्पष्टीकरण हिंदी (देवनागरी) में 2-3 वाक्यों में दें।\n"
        "3. कोड में कोई सिंटैक्स त्रुटि या अपूर्ण भाग न छोड़ें।"
    )
    history = history or []

    # -------------------------------------------------------------------------
    # STEP 1: DYNAMIC PROBE — Check which of the 3 keys has Gemini 3.8 active
    # -------------------------------------------------------------------------
    is_38_active, g38_key, g38_label = await probe_gemini_38_active_key()
    if is_38_active and g38_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={g38_key}"
            payload = {
                "contents": [{"parts": [{"text": f"{sys}\n\nयूजर का प्रश्न:\n{user_query}"}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}
            }
            async with httpx.AsyncClient(timeout=14.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    code_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if code_text:
                        return f"*(Gemini 3.8 Flash सक्रिय — {g38_label})*\n\n{code_text}"
        except Exception as e:
            print(f"[ModelRouter] Gemini 3.8 run notice on {g38_label}: {e}")

    # -------------------------------------------------------------------------
    # STEP 2: DEFAULT CODING ENGINE — Groq 120B Reasoning Model
    # -------------------------------------------------------------------------
    if settings.GROQ_API_KEY:
        for m in [settings.MODEL_CODING, "qwen/qwen3.8-27b"]:
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        json={
                            "model": m,
                            "messages": [{"role": "system", "content": sys}, *history, {"role": "user", "content": user_query}],
                            "max_tokens": max_tokens,
                            "temperature": 0.1
                        }
                    )
                    if res.status_code == 200:
                        choice = res.json()["choices"][0]["message"]
                        cnt = choice.get("content")
                        if cnt and cnt.strip():
                            return cnt.strip()
            except Exception as e:
                print(f"[ModelRouter] Coding {m} notice: {e}")

    # -------------------------------------------------------------------------
    # STEP 3: FALLBACK — Gemini 3.5 Flash Lite across Key Pool
    # -------------------------------------------------------------------------
    for k in settings.gemini_keys_pool:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={k}"
            payload = {
                "contents": [{"parts": [{"text": f"{sys}\n\nयूजर का प्रश्न:\n{user_query}"}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens}
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            pass

    return None

async def route_reasoning(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 650
) -> Dict[str, Any]:
    """
    Task 3: Deep Logic, Math & Reasoning.
    Uses Groq openai/gpt-oss-120b for step-by-step chain of thought.
    """
    sys = system_prompt or "You are J.A.R.V.I.S. Logic & Mathematical Reasoning Engine. Solve problems step-by-step with zero assumptions."
    
    if settings.GROQ_API_KEY:
        for m in [settings.MODEL_REASONING, "openai/gpt-oss-20b"]:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        json={
                            "model": m,
                            "messages": [{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "temperature": 0.1
                        }
                    )
                    if res.status_code == 200:
                        msg = res.json()["choices"][0]["message"]
                        return {
                            "content": msg.get("content", "").strip(),
                            "reasoning": msg.get("reasoning", "").strip(),
                            "model": m
                        }
            except Exception as e:
                print(f"[ModelRouter] Reasoning {m} notice: {e}")

    return {"content": "", "reasoning": "", "model": "none"}

async def route_vision(
    prompt: str,
    image_base64: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 350
) -> Optional[str]:
    """
    Task 4: Multimodal Screen Vision, OCR & Chart Pattern Recognition.
    Auto-rotates across the 3 Gemini API keys for zero downtime and quota distribution.
    """
    sys = system_prompt or (
        "आप J.A.R.V.I.S. हैं — रियल-टाइम लाइव विज़न और चार्ट एनालाइज़र।\n"
        "यूजर के लाइव स्क्रीन को देखकर उत्तर हमेशा अत्यंत सटीक, पेशेवर और शुद्ध हिंदी (देवनागरी) में दें।\n"
        "यूजर को 'सर' कहकर संबोधित करें। 2 से 3 वाक्यों में मुख्य निष्कर्ष बताएं।"
    )

    # 1. Primary: Google Gemini 3.5 Flash Lite across the 3-key pool
    if image_base64:
        for k in settings.gemini_keys_pool:
            for g_model in [settings.MODEL_VISION, "gemini-flash-latest"]:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={k}"
                    payload = {
                        "contents": [{
                            "parts": [
                                {"text": f"{sys}\n\nयूजर का निर्देश: {prompt}"},
                                {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
                            ]
                        }],
                        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}
                    }
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        res = await client.post(url, json=payload)
                        if res.status_code == 200:
                            txt = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                            if txt:
                                return txt
                except Exception as e:
                    pass

    # 2. Fallback: OpenRouter Free Vision Model
    if settings.OPENROUTER_API_KEY and image_base64:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "JARVIS-APEX"
            }
            payload = {
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{sys}\n\n{prompt}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                        ]
                    }
                ],
                "max_tokens": max_tokens
            }
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    txt = res.json()["choices"][0]["message"].get("content", "").strip()
                    if txt:
                        return txt
        except Exception as e:
            print(f"[ModelRouter] Vision OpenRouter fallback notice: {e}")

    return None

async def route_json_resilient(
    prompt: str,
    system_prompt: str,
    temperature: float = 0.15
) -> Dict[str, Any]:
    """
    Tasks 5 & 6: Fact Verification & Deep Research Monograph Chapter Generation.
    Uses Google Gemini across the 3 API keys primary (native structured JSON mode),
    and Groq openai/gpt-oss-120b secondary (reasoning JSON).
    """
    # 1. Primary: Google Gemini across 3 Keys
    for k in settings.gemini_keys_pool:
        for model in [settings.MODEL_RESEARCH_WRITER, "gemini-flash-latest"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={k}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                        "maxOutputTokens": 4096
                    }
                }
                async with httpx.AsyncClient(timeout=16.0) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = clean_json_str(raw)
                        if parsed:
                            return parsed
            except Exception as e:
                pass

    # 2. Secondary: Groq openai/gpt-oss-120b (120B Parameter Reasoning JSON)
    if settings.GROQ_API_KEY:
        for g_model in [settings.MODEL_FACT_CHECK, "qwen/qwen3.8-27b"]:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": g_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": temperature,
                    "max_tokens": 4096
                }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    res = await client.post(url, headers=headers, json=payload)
                    if res.status_code == 200:
                        raw = res.json()["choices"][0]["message"]["content"]
                        parsed = clean_json_str(raw)
                        if parsed:
                            return parsed
            except Exception as e:
                print(f"[ModelRouter] JSON Groq {g_model} notice: {e}")

    return {}
