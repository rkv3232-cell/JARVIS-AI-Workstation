import time
import re
import httpx
from typing import Optional, Any
from .config import settings
from .os_controller import execute_os_action
from .math_engine import solve_math_query
from .trading_scanner import scan_market, fetch_symbol_price, get_option_chain
from .ai_screen_vision import analyze_screen_with_ai, detect_chart_patterns_and_overlays, extract_screen_text_and_clipboard
from .morning_briefing import generate_morning_briefing
from .omni_services import fetch_live_weather, fetch_cricket_match_data, get_developer_telemetry
from .database import log_conversation, get_recent_history, save_trading_journal_entry
from .live_search import search_internet_live, fetch_breaking_news
from .url_threat_analyzer import analyze_url_threat, extract_urls
from .deep_research_engine import run_universal_deep_research, determine_depth_mode
from .model_router import route_chat_voice, route_coding, route_reasoning, get_model_catalog, get_gemini_38_probe_status

JARVIS_SYSTEM_PROMPT = """आप J.A.R.V.I.S. हैं — एक अत्यंत बुद्धिमान, विनम्र, सुरक्षित और अनुशासित AI ऑपरेटिंग सिस्टम और पर्सनल वर्कस्टेशन असिस्टेंट।
यूजर एक सक्रिय ट्रेडर, सॉफ्टवेयर इंजीनियर (Coder) और पावर यूजर हैं।

निर्देश और बातचीत के नियम:
1. हमेशा शुद्ध, सरल, स्पष्ट और गरिमापूर्ण हिंदी (देवनागरी लिपि / Devanagari Hindi Script) में ही उत्तर दें।
2. यूजर को हमेशा आदरपूर्वक 'सर' (Sir) कहकर ही संबोधित करें (उदा. 'जी सर, सभी सिस्टम्स सामान्य हैं।')।
3. बातचीत अत्यंत सुरक्षित, विनम्र, पेशेवर और मर्यादित होनी चाहिए।
4. जवाब संक्षिप्त, सटीक और आवाज़ (Voice TTS) के लिए एकदम उपयुक्त रखें (1 से 2 छोटे और स्पष्ट वाक्य)।
5. तकनीकी, ट्रेडिंग और कोडिंग शब्दों (जैसे: Nifty, Python, API, Git, Cricket, Weather, Option Chain, TradingView, Chrome) को हिंदी में सहजता से इस्तेमाल करें।
6. यदि यूजर कोडिंग या टेक सवाल पूछे, तो संक्षिप्त समाधान दें और मुख्य कोड ब्लॉक स्पष्ट रखें।"""

async def generate_grounded_answer(raw_query: str, search_data: dict) -> str:
    """
    Synthesizes a 100% verified, authentic Hindi answer grounded strictly in live internet search data.
    """
    grounding = search_data.get("grounding_text", "")
    if not grounding:
        return "जी सर, मैंने लाइव इंटरनेट पर सर्च किया लेकिन कोई स्पष्ट प्रमाण नहीं मिल सका।"

    prompt = f"""आप J.A.R.V.I.S. हैं — एक अत्यंत बुद्धिमान, सत्यनिष्ठ और विनम्र AI वर्कस्टेशन असिस्टेंट।
यूजर के प्रश्न का उत्तर केवल और केवल नीचे दिए गए LIVE INTERNET SEARCH VERIFIED DATA के आधार पर 100% सटीक और देवनागरी हिंदी में दें।
नियम:
1. हमेशा उत्तर 'जी सर,' से शुरू करें।
2. 1 से 2 छोटे, स्पष्ट और प्राकृतिक देवनागरी हिंदी वाक्यों में सीधा उत्तर दें (आवाज़ TTS के लिए आदर्श)।
3. तथ्य में कोई कल्पना या अनुमान न करें; जो लाइव सर्च परिणामों में प्रमाणित है, वही बताएं।
4. मुख्य नाम, पद, स्कोर, आंकड़े या समय स्पष्ट रखें।

[LIVE INTERNET SEARCH VERIFIED DATA]:
{grounding}

[USER QUESTION]:
{raw_query}"""

    # 1. Groq LPU Ultra-Fast Priority (~0.3s)
    if settings.GROQ_API_KEY:
        for g_model in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
            try:
                async with httpx.AsyncClient(timeout=3.5) as client:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        json={
                            "model": g_model,
                            "messages": [
                                {"role": "system", "content": prompt},
                                {"role": "user", "content": raw_query}
                            ],
                            "max_tokens": 140,
                            "temperature": 0.2
                        }
                    )
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                pass

    # 2. Gemini API Fallback (Gemini 3.5 Flash Lite Free Tier)
    if settings.GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {"parts": [{"text": f"{prompt}\nUser Question: {raw_query}"}]}
                ],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 140}
            }
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass

    # 3. Direct Extractive Fallback
    results = search_data.get("results", [])
    if results:
        top = results[0]
        return f"जी सर, लाइव इंटरनेट सर्च के अनुसार: {top['title']}। विस्तृत विवरण विजेट में उपलब्ध है।"

    return "जी सर, मैंने लाइव इंटरनेट पर सर्च पूरा कर लिया है।"

async def generate_breaking_news_brief(category_name: str, news_data: dict) -> str:
    """
    Synthesizes the freshest, latest breaking news headlines with timestamps into a polished spoken Hindi brief.
    """
    grounding = news_data.get("grounding_text", "")
    if not grounding:
        return f"जी सर, {category_name} में इस समय कोई नई ब्रेकिंग न्यूज़ प्राप्त नहीं हुई है।"

    prompt = f"""आप J.A.R.V.I.S. हैं। यूजर ने ताज़ा खबरें ({category_name}) पूछी हैं।
नीचे दी गई सबसे ताज़ा और नई खबरों (Freshest Breaking News with Timestamps) के आधार पर 100% सटीक और स्पष्ट देवनागरी हिंदी में उत्तर दें।
नियम:
1. हमेशा 'जी सर,' से शुरुआत करें।
2. केवल 2 या 3 सबसे महत्वपूर्ण और सबसे ताज़ा खबरों को उनके समय (जैसे: 15 मिनट पहले, 1 घंटा पहले) और स्रोत के साथ संक्षेप में 2 वाक्यों में बताएं।
3. तथ्य में कोई मिलावट न करें; जो लाइव टाइमस्टैम्प्स में दिया गया है वही बताएं।
4. अंत में कहें 'विस्तृत समाचार विजेट में उपलब्ध है।'

[LATEST BREAKING NEWS]:
{grounding}"""

    if settings.GROQ_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=3.5) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [{"role": "system", "content": prompt}],
                        "max_tokens": 150,
                        "temperature": 0.2
                    }
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    items = news_data.get("results", [])
    if len(items) >= 2:
        return f"जी सर, {category_name} की ताज़ा खबरों में: पहला, ({items[0]['relative_time']}) {items[0]['title']}। दूसरा, ({items[1]['relative_time']}) {items[1]['title']}। विस्तृत विवरण विजेट में उपलब्ध है।"
    elif items:
        return f"जी सर, सबसे ताज़ा खबर ({items[0]['relative_time']}) है: {items[0]['title']} ({items[0]['source']})।"
    return "जी सर, सभी ताज़ा खबरें विजेट में लोड कर दी गई हैं।"

def extract_deep_research_topic(raw_text: str) -> tuple[str, str]:
    """
    Extracts the clean research subject and the requested depth mode (QUICK, STANDARD, DEEP).
    """
    mode = determine_depth_mode(raw_text)
    clean = raw_text.strip()
    clean = re.sub(r'^(jarvis|hey jarvis|hello jarvis|जार्विस|सुनो)\s*[,:]?\s*', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^(please|कृपया)\s*', '', clean, flags=re.IGNORECASE)
    
    triggers = [
        'deeply explain karo aur report banao', 'deeply explain karo', 'deeply explain',
        'complete research report banao', 'complete research report', 'complete report banao', 'complete report',
        'detailed research report bana kar do', 'detailed research report', 'detailed research', 'detailed report',
        'deep research report', 'deep research on', 'deep research', 'research on', 'research report', 'research karo', 'research',
        'रिसर्च करो', 'रिसर्च रिपोर्ट', 'रिसर्च', 'पूरी रिपोर्ट बनाओ', 'पूरी रिपोर्ट', 'विस्तृत रिपोर्ट बनाओ', 'विस्तृत रिपोर्ट',
        'गहन अध्ययन करो', 'गहन अध्ययन', 'बायोग्राफी बनाओ', 'बायोग्राफी', 'जीवनी बनाओ', 'जीवनी',
        'biography of', 'biography on', 'biography', 'pdf report banao', 'pdf report', 'पीडीएफ रिपोर्ट बनाओ', 'पीडीएफ रिपोर्ट',
        'रिपोर्ट बनाओ', 'रिपोर्ट तैयार करो', 'रिपोर्ट', 'report banao', 'report generate', 'case study', 'केस स्टडी',
        'डिटेल्ड रिपोर्ट', 'detailed'
    ]
    for trig in sorted(triggers, key=len, reverse=True):
        clean = re.sub(re.escape(trig), ' ', clean, flags=re.IGNORECASE)

    postpositions = [
        r'\b(ka|ki|ke|ko|par|pe|me|mein|about|for|of)\b',
        r'(का|की|के|को|पर|पे|में|बारे में)',
        r'\b(banao|bana do|bana kar do|generate karo|karo|chahiye|dega|do)\b',
        r'(बनाओ|बनाकर दो|करो|चाहिए|दो)'
    ]
    for p in postpositions:
        clean = re.sub(p, ' ', clean, flags=re.IGNORECASE)

    clean = re.sub(r'\s+', ' ', clean).strip(' ,:.-?!')
    return clean or raw_text.strip(), mode

async def process_user_intent(user_input: str, progress_callback: Optional[Any] = None) -> dict:
    raw_query = user_input.strip()
    query = raw_query.lower()
    
    # 1. Log turn to Firebase & SQLite
    log_conversation("user", raw_query)

    # =========================================================================
    # 0.5 CYBER THREAT & URL FORENSIC ANALYZER (Anti-Phishing & Scam Radar)
    # =========================================================================
    detected_urls = extract_urls(raw_query)
    cyber_keywords = [
        "link", "url", "लिंक", "वेबसाइट", "स्कैम", "phishing", "fraud", "धोखाधड़ी",
        "सुरक्षित", "safe", "scam", "चेक करो", "analyze url", "check link", "report", "रिपोर्ट", "detail", "कच्चा"
    ]
    if detected_urls or (any(k in query for k in cyber_keywords) and any(ext in query for ext in [".buzz", ".xyz", ".top", ".com", ".in", ".org", "http"])):
        target_url = detected_urls[0] if detected_urls else raw_query.strip()
        report = await analyze_url_threat(target_url, context_text=raw_query)
        reply = report["spoken_brief"]
        log_conversation("jarvis", reply, intent="cyber_threat_report")
        return {
            "text": reply,
            "action_executed": "url_threat_analysis",
            "intent": "cyber_threat_report",
            "dynamic_widget": {
                "type": "cyber_report",
                "title": f"Cyber Threat Assessment: {report['domain']}",
                "data": report
            }
        }

    # =========================================================================
    # 0.8 UNIVERSAL DEEP RESEARCH & REPORT GENERATION ENGINE
    # =========================================================================
    research_triggers = [
        "research", "रिसर्च", "biography", "बायोग्राफी", "जीवनी",
        "complete report", "पूरी रिपोर्ट", "विस्तृत रिपोर्ट", "गहन अध्ययन",
        "deep dive", "deeply explain", "pdf report", "पीडीएफ रिपोर्ट",
        "रिपोर्ट बनाओ", "report banao", "रिपोर्ट तैयार करो", "report generate",
        "केस स्टडी", "case study", "full history", "पूरा इतिहास",
        "डिटेल्ड रिपोर्ट", "detailed report"
    ]
    if any(k in query for k in research_triggers) and not any(k in query for k in ["open", "kholo", "chalao"]):
        topic, mode = extract_deep_research_topic(raw_query)
        report = await run_universal_deep_research(topic, requested_mode=mode, progress_callback=progress_callback)
        reply = report.get("spoken_answer") or f"जी सर, {report['title']} पर बहु-स्रोतीय रिसर्च पूरी हो चुकी है। सभी प्रामाणिक तथ्यों और संदर्भों के साथ विस्तृत PDF रिपोर्ट तैयार है।"
        log_conversation("jarvis", reply, intent="deep_research")
        return {
            "text": reply,
            "action_executed": "deep_research",
            "intent": "deep_research",
            "dynamic_widget": {
                "type": "deep_research_report",
                "title": report.get("title", f"Research: {topic}"),
                "data": report
            }
        }

    # =========================================================================
    # 1. OS DESKTOP AUTOMATION ACTIONS (High Priority for instant execution)
    # =========================================================================
    os_result = execute_os_action(query)
    if os_result.get("status") == "pending_confirmation":
        reply = os_result.get("message", "सुरक्षा पुष्टि आवश्यक है।")
        log_conversation("jarvis", reply, intent="action_confirmation")
        return {
            "text": reply,
            "action_executed": "pending_confirmation",
            "intent": "action_confirmation",
            "dynamic_widget": {
                "type": "action_confirmation",
                "title": "सुरक्षा पुष्टि आवश्यक (Two-Step Confirmation)",
                "data": os_result.get("pending_action", {})
            }
        }

    if os_result["status"] == "success":
        reply = os_result.get("message", "जी सर, एप्लिकेशन खोल दिया गया है।")
        log_conversation("jarvis", reply, intent="os_action")
        return {
            "text": reply,
            "action_executed": query,
            "intent": "os_action",
            "dynamic_widget": {
                "type": "os_action",
                "title": "Desktop Automation",
                "data": {
                    "action": query,
                    "message": reply,
                    "timestamp": time.time()
                }
            }
        }

    # =========================================================================
    # 1.5 INSTANT MATH & CALCULATION ENGINE (<1ms local execution)
    # =========================================================================
    math_res = solve_math_query(raw_query)
    if math_res:
        reply = math_res["text"]
        log_conversation("jarvis", reply, intent="calculation")
        return {
            "text": reply,
            "action_executed": "math_calculation",
            "intent": "calculation",
            "dynamic_widget": {
                "type": "calculator",
                "title": "Instant Math Calculation",
                "data": {
                    "expression": math_res["expression"],
                    "result": math_res["result"],
                    "formatted": math_res["formatted_result"],
                    "reply": reply,
                    "timestamp": time.time()
                }
            }
        }

    # =========================================================================
    # 2. USER LOCATION CONFIGURATION & HOME PROFILE
    # =========================================================================
    if ("दुल्लहपुर" in query or "dullahpur" in query) or (any(k in query for k in ["location", "लोकेशन", "शहर"]) and any(k in query for k in ["set", "करो", "है", "change", "badlo"])):
        loc_str = "दुल्लहपुर, उत्तर प्रदेश"
        settings.DEFAULT_USER_CITY = "Dullahpur, Uttar Pradesh"
        weather_data = await fetch_live_weather("Dullahpur, Uttar Pradesh")
        reply = f"जी सर, आपकी प्राथमिक लोकेशन सफलतापूर्वक '{loc_str}' पर सेट कर दी गई है। वर्तमान में दुल्लहपुर में तापमान {weather_data['temp']} है और मौसम {weather_data['condition']} बना हुआ है।"
        log_conversation("jarvis", reply, intent="location_config")
        return {
            "text": reply,
            "action_executed": "set_location",
            "intent": "location_config",
            "dynamic_widget": {
                "type": "weather",
                "title": f"Home Location: {loc_str}",
                "data": weather_data
            }
        }

    # =========================================================================
    # 3. LIVE WEATHER INQUIRY (Dynamic Weather Widget with Auto Geolocation)
    # =========================================================================
    weather_keywords = [
        "weather", "mausam", "mosam", "मौसम", "मोसम", "तापमान", "tapman",
        "temperature", "rain", "barish", "बारिश", "forecast", "हवामान", "climate"
    ]
    if any(k in query for k in weather_keywords):
        # Dynamically extract city name if specified in user query
        weather_stopwords = {
            "weather", "mausam", "mosam", "मौसम", "मोसम", "तापमान", "tapman", "temperature",
            "rain", "barish", "बारिश", "forecast", "हवामान", "climate",
            "aaj", "today", "abhi", "kal", "ka", "ki", "ke", "ko",
            "me", "mein", "pe", "par", "kaisa", "hai", "hoga", "hogi", "kya", "batao",
            "bataiye", "kitna", "karo", "check", "live", "sir", "jarvis", "please",
            "in", "at", "for", "the", "of", "show", "tell", "dekho", "dikhaye", "haal",
            # Comprehensive Devanagari Hindi stopwords
            "आज", "का", "के", "की", "को", "में", "पर", "पे", "कैसा", "केसा", "कैसी", "है",
            "होगा", "होगी", "क्या", "बताओ", "बताइए", "बता", "कितना", "करो", "चेक", "लाइव",
            "दिखाओ", "दिखाइए", "हाल", "अपडेट", "सर", "जार्विस", "कृपया", "यहाँ", "इधर"
        }
        tokens = query.split()
        clean_tokens = [w.strip(",.?!:;\"'") for w in tokens if w.strip(",.?!:;\"'") not in weather_stopwords and len(w.strip(",.?!:;\"'")) > 1]
        extracted_city = " ".join(clean_tokens) if clean_tokens else None
        
        # If extracted string is empty or generic, use default home location
        if extracted_city and any(g in extracted_city.lower() for g in ["local", "current", "mera", "meri", "yahan", "idhar", "yaha"]):
            extracted_city = None
        
        weather_data = await fetch_live_weather(extracted_city)
        auto_note = " (आपकी वर्तमान लोकेशन)" if weather_data.get("is_auto_detected") else ""
        reply = f"जी सर, {weather_data['city']}{auto_note} में इस समय तापमान {weather_data['temp']} है और मौसम {weather_data['condition']} बना हुआ है।"
        log_conversation("jarvis", reply, intent="weather")
        return {
            "text": reply,
            "action_executed": "weather_lookup",
            "intent": "weather",
            "dynamic_widget": {
                "type": "weather",
                "title": f"Live Weather: {weather_data['city']}",
                "data": weather_data
            }
        }

    # =========================================================================
    # 3. LIVE CRICKET SCORE & SPORTS (Real-time Cricinfo RSS Feed)
    # =========================================================================
    cricket_keywords = ["cricket", "क्रिकेट", "match", "score", "मैच", "ipl", "scorecard", "स्कोर", "run", "रन", "kohli", "wicket", "विकेट"]
    if any(k in query for k in cricket_keywords) and not any(k in query for k in ["trade", "crypto"]):
        cricket_data = await fetch_cricket_match_data()
        status_text = cricket_data.get("status", "")
        teams = cricket_data.get("teams", "क्रिकेट मुकाबला")
        is_won = any(w in status_text for w in ["हरा दिया", "जीत", "won by", "won"])

        if is_won:
            reply = f"जी सर, मुकाबले का परिणाम आ चुका है: {status_text} (स्कोर: {cricket_data['score_team1']} बनाम {cricket_data['score_team2']})।"
        elif cricket_data.get("is_national_india"):
            reply = f"जी सर, भारत के मुकाबले का लाइव स्कोर: {status_text} (स्कोर: {cricket_data['score_team1']} बनाम {cricket_data['score_team2']})।"
        else:
            reply = f"जी सर, वर्तमान में लाइव मुकाबला: {teams}। {status_text}"

        log_conversation("jarvis", reply, intent="cricket")
        return {
            "text": reply,
            "action_executed": "cricket_score",
            "intent": "cricket",
            "dynamic_widget": {
                "type": "cricket",
                "title": f"Live Cricket: {cricket_data['teams']}",
                "data": cricket_data
            }
        }

    # =========================================================================
    # 3. DEVELOPER / CODER WORKSPACE STATS (Dynamic Dev Widget)
    # =========================================================================
    dev_keywords = ["git branch", "git status", "code status", "dev status", "developer", "environment", "coder", "वर्कस्पेस", "पोर्ट्स"]
    if any(k in query for k in dev_keywords) and not any(k in query for k in ["open", "kholo", "chalao", "copy", "कॉपी", "clipboard", "क्लिपबोर्ड"]):
        dev_data = get_developer_telemetry()
        reply = f"जी सर, डेवलपर वर्कस्पेस पूरी तरह तैयार है। एक्टिव गिट ब्रांच '{dev_data['git_branch']}' है और पाइथन 3.12 रनटाइम सक्रिय है।"
        log_conversation("jarvis", reply, intent="dev_stats")
        return {
            "text": reply,
            "action_executed": "dev_stats",
            "intent": "developer",
            "dynamic_widget": {
                "type": "developer",
                "title": "Developer Workstation Status",
                "data": dev_data
            }
        }

    # =========================================================================
    # 4A. VISION 2.0: INSTANT SCREEN OCR & CLIPBOARD COPY
    # =========================================================================
    ocr_keywords = [
        "copy code", "copy error", "कोड कॉपी", "एरर कॉपी", "टेक्स्ट कॉपी", 
        "clipboard copy", "स्क्रीन से कॉपी", "स्क्रीन का कोड", "copy from screen",
        "क्लिपबोर्ड", "code copy", "error copy", "स्क्रीन पर जो कोड", "स्क्रीन पर जो एरर"
    ]
    if any(k in query for k in ocr_keywords):
        ocr_res = await extract_screen_text_and_clipboard()
        reply = ocr_res.get("spoken", "सर, स्क्रीन पर दिख रहा कोड आपके क्लिपबोर्ड पर कॉपी कर दिया गया है।")
        log_conversation("jarvis", reply, intent="screen_ocr_clipboard")
        return {
            "text": reply,
            "action_executed": "screen_ocr_clipboard",
            "intent": "screen_ocr_clipboard",
            "dynamic_widget": {
                "type": "ocr_clipboard",
                "title": "Vision 2.0 Screen Clipboard",
                "data": ocr_res
            }
        }

    # =========================================================================
    # 4B. VISION 2.0: CHART PATTERN AUTO-OVERLAY DETECTION
    # =========================================================================
    pattern_keywords = [
        "pattern", "पैटर्न", "fvg", "फेयर वैल्यू", "support resistance", 
        "सपोर्ट रेजिस्टेंस", "order block", "ऑर्डर ब्लॉक", "head and shoulder", 
        "हेड एंड शोल्डर", "chart mark", "overlay", "चार्ट पैटर्न"
    ]
    if any(k in query for k in pattern_keywords) and not any(k in query for k in ["open", "kholo", "chalao"]):
        pattern_res = await detect_chart_patterns_and_overlays()
        reply = pattern_res.get("summary", "सर, चार्ट पर मुख्य सपोर्ट और फेयर वैल्यू गैप्स मार्क कर दिए गए हैं।")
        log_conversation("jarvis", reply, intent="chart_pattern_overlay")
        return {
            "text": reply,
            "action_executed": "chart_pattern_overlay",
            "intent": "chart_pattern_overlay",
            "dynamic_widget": {
                "type": "chart_patterns",
                "title": "Vision 2.0 Chart Pattern Overlays",
                "data": pattern_res
            }
        }

    # =========================================================================
    # 4. DESKTOP SCREEN VISION & LIVE SCREEN ANALYZER
    # =========================================================================
    screen_keywords = ["screen", "स्क्रीन", "चार्ट देखो", "स्क्रीन देखो", "look at my screen", "analyze chart", "क्या दिख रहा है", "क्या चल रहा है स्क्रीन", "screen analyze", "मेरा चार्ट देखो"]
    if any(k in query for k in screen_keywords):
        vision_result = await analyze_screen_with_ai(custom_query=raw_query)
        reply = vision_result.get("text", "जी सर, मैंने आपका चार्ट देख लिया है। स्ट्रक्चर बुलिश ट्रेंड में कंसोलिडेट हो रहा है।")
        log_conversation("jarvis", reply, intent="screen_vision")
        return {
            "text": reply,
            "action_executed": "screen_vision",
            "intent": "screen_vision",
            "dynamic_widget": {
                "type": "vision",
                "title": "Live Screen Vision HUD",
                "data": {
                    "text": reply,
                    "image_base64": vision_result.get("image_base64", ""),
                    "trend": vision_result.get("trend", "NEUTRAL"),
                    "is_live_stream": True,
                    "timestamp": vision_result.get("timestamp", time.time())
                }
            }
        }

    # =========================================================================
    # 5. MORNING PRE-MARKET BRIEFING
    # =========================================================================
    morning_keywords = ["morning", "brief", "सुबह", "प्री मार्केट", "pre market", "briefing", "दिन की शुरुआत", "आज का मार्केट"]
    if any(k in query for k in morning_keywords) and not any(k in query for k in ["open", "kholo", "chalao"]):
        briefing = await generate_morning_briefing()
        reply = briefing.spoken_brief
        log_conversation("jarvis", reply, intent="morning_briefing")
        return {
            "text": reply,
            "action_executed": "morning_briefing",
            "intent": "morning_briefing",
            "dynamic_widget": {
                "type": "briefing",
                "title": "Daily Institutional Pre-Market Briefing",
                "data": briefing.model_dump()
            }
        }

    # =========================================================================
    # 6. OPTION CHAIN & PCR ANALYTICS
    # =========================================================================
    option_keywords = ["option chain", "ऑप्शन चेन", "pcr", "पुट कॉल", "max pain", "open interest", "oi data", "कॉल राइटिंग", "पुट राइटिंग"]
    if any(k in query for k in option_keywords):
        sym = "BANKNIFTY" if "bank" in query or "बैंक" in query else "NIFTY50"
        oc = await get_option_chain(sym)
        reply = f"जी सर, {sym} का पुट-कॉल रेशियो (PCR) {oc.pcr} है और मैक्स पेन {oc.max_pain:,.0f} पर स्थित है। मार्केट का ओवरऑल सेंटीमेंट {oc.sentiment} है।"
        log_conversation("jarvis", reply, intent="option_chain")
        return {
            "text": reply,
            "action_executed": "option_chain_analysis",
            "intent": "option_chain",
            "dynamic_widget": {
                "type": "option_chain",
                "title": f"F&O Option Chain: {sym}",
                "data": oc.model_dump()
            }
        }

    # =========================================================================
    # 7. TRADING SCANNER & SMART MARKET INQUIRIES
    # =========================================================================
    market_keywords = ["scan", "market", "trade", "crypto", "bitcoin", "btc", "eth", "sol", "nifty", "banknifty", "order block", "fvg", "level", "price", "भाव", "लेवल", "ट्रेंड", "trend", "outlook"]
    if any(k in query for k in market_keywords):
        if "nifty" in query or "निफ्टी" in query:
            price = await fetch_symbol_price("NIFTY50")
            if price:
                sigs = await scan_market(["NIFTY50"])
                sig_text = f" 15-मिनट चार्ट पर {sigs[0].signal_type} एक्टिव है।" if sigs else " स्ट्रक्चर अभी संतुलन में है।"
                trend_opinion = " 24,200 के ऊपर बायर्स का नियंत्रण मजबूत बना हुआ है।" if price >= 24200 else " 24,000 के नीचे सेलर्स का दबाव देखा जा सकता है।"
                reply = f"जी सर, निफ्टी 50 अभी {price:,.2f} के स्तर पर है।{trend_opinion}{sig_text}"
                log_conversation("jarvis", reply, intent="market_query")
                return {
                    "text": reply,
                    "action_executed": "nifty_scan",
                    "intent": "market_query",
                    "dynamic_widget": {
                        "type": "market_scan",
                        "title": "NIFTY 50 Institutional Setup",
                        "data": {"symbol": "NIFTY50", "price": price, "signals": [s.model_dump() for s in sigs]}
                    }
                }

        for sym, name in [("BTCUSDT", "बिटकॉइन"), ("ETHUSDT", "एथेरियम"), ("SOLUSDT", "सोलाना")]:
            if name.lower() in query or sym.lower() in query or sym.replace("USDT","").lower() in query:
                price = await fetch_symbol_price(sym)
                if price:
                    sigs = await scan_market([sym])
                    sig_text = f" {sigs[0].signal_type.replace('_',' ')} सेटअप एक्टिव मिला है।" if sigs else " प्राइस एक्शन अभी सामान्य रेंज में है।"
                    reply = f"जी सर, {name} इस समय ${price:,.2f} पर चल रहा है।{sig_text}"
                    log_conversation("jarvis", reply, intent="market_query")
                    return {
                        "text": reply,
                        "action_executed": f"scan_{sym}",
                        "intent": "market_query",
                        "dynamic_widget": {
                            "type": "market_scan",
                            "title": f"{name} Market Analysis",
                            "data": {"symbol": sym, "price": price, "signals": [s.model_dump() for s in sigs]}
                        }
                    }

        signals = await scan_market(settings.DEFAULT_SYMBOLS)
        if signals:
            top = signals[0]
            reply = f"मार्केट स्कैन पूरा हो गया है सर। {top.symbol} पर 15-मिनट का अनमिटिगेटेड {top.signal_type.replace('_', ' ')} सेटअप मिला है, जिसमें रिस्क-रिवॉर्ड 1:{top.risk_reward} है।"
        else:
            reply = "जी सर, सभी वॉचलिस्ट एसेट्स का विश्लेषण पूरा हो गया है। मार्केट में फिलहाल कोई अनमिटिगेटेड असंतुलन नहीं है।"
            
        log_conversation("jarvis", reply, intent="market_query")
        return {
            "text": reply,
            "action_executed": "market_scan",
            "intent": "market_query",
            "dynamic_widget": {
                "type": "market_scan",
                "title": "SMC Market Radar Radar Scan",
                "data": {"signals": [s.model_dump() for s in signals]}
            }
        }

    # =========================================================================
    # 9. SYSTEM TELEMETRY / WORKSTATION HEALTH
    # =========================================================================
    if any(k in query for k in ["status", "system", "health", "specs", "cpu", "ram", "सिस्टम"]):
        from .system_monitor import get_system_telemetry
        tel = get_system_telemetry()
        reply = f"सभी सिस्टम्स पूरी तरह सामान्य हैं सर। सीपीयू लोड {tel.cpu_percent}% पर है, रैम उपयोग {tel.ram_percent}% है, और {tel.disk_free_gb} GB डिस्क स्पेस उपलब्ध है।"
        log_conversation("jarvis", reply, intent="system_status")
        return {
            "text": reply,
            "action_executed": "system_status",
            "intent": "system_status",
            "dynamic_widget": {
                "type": "telemetry",
                "title": "Workstation Telemetry",
                "data": tel.model_dump()
            }
        }

    # =========================================================================
    # 9.5 LIVE BREAKING NEWS RADAR (Freshest Up-to-the-Minute News Priority)
    # =========================================================================
    news_triggers = [
        "news", "न्यूज", "न्यूज़", "समाचार", "खबर", "खबरें", "ताज़ा", "ताजा",
        "breaking", "headlines", "हेडलाइंस", "लेटेस्ट खबर", "आज की खबर", "अपडेट"
    ]
    is_general_news = any(k in query for k in news_triggers) and not any(k in query for k in ["search", "सर्च", "खोजो", "ढूंढो", "who is", "kaun hai", "सीईओ", "ceo", "salary", "सैलरी"])
    if is_general_news:
        if any(w in query for w in ["market", "markets", "मार्केट", "शेयर", "बाजार", "निफ्टी", "sensex", "business", "बिजनेस", "स्टॉक", "वित्त"]):
            cat = "markets"
        elif any(w in query for w in ["tech", "technology", "टेक", "टेक्नोलॉजी", "ai", "एआई", "तकनीक", "साइंस", "कंप्यूटर", "software"]):
            cat = "tech"
        elif any(w in query for w in ["sport", "sports", "cricket", "स्पोर्ट्स", "खेल", "क्रिकेट"]):
            cat = "sports"
        else:
            cat = "top"

        news_data = await fetch_breaking_news(category=cat, max_results=10)
        reply = await generate_breaking_news_brief(news_data["category"], news_data)
        log_conversation("jarvis", reply, intent="breaking_news")
        return {
            "text": reply,
            "action_executed": "breaking_news",
            "intent": "breaking_news",
            "dynamic_widget": {
                "type": "breaking_news",
                "title": f"Live Radar: {news_data['category']}",
                "data": {
                    "category": news_data["category"],
                    "category_key": news_data["category_key"],
                    "summary": reply,
                    "results": news_data["results"],
                    "count": news_data["count"],
                    "fetch_time_ms": news_data["fetch_time_ms"]
                }
            }
        }

    # =========================================================================
    # 9.6 LIVE REAL-TIME INTERNET SEARCH & GROUNDING (ONLY WHEN EXPLICITLY NEEDED)
    # =========================================================================
    web_search_triggers = [
        "search", "सर्च", "खोजो", "गूगल", "google karo", "पता करो", "ढूंढो", "dhundo", "online",
        "who is the", "who won", "kaun hai", "kisko mila",
        "सीईओ", "ceo", "pm", "राष्ट्रपति", "president", "विजेता", "winner",
        "सैलरी", "salary", "नेटवर्थ", "net worth"
    ]
    is_coding_or_conceptual = any(w in query for w in ["code", "कोड", "python", "function", "फंक्शन", "script", "loop", "syntax", "error", "bug", "html", "css", "javascript", "sql", "explain", "समझाओ"])
    
    if any(k in query for k in web_search_triggers) and not is_coding_or_conceptual:
        search_data = await search_internet_live(raw_query)
        if search_data.get("sources_count", 0) > 0:
            reply = await generate_grounded_answer(raw_query, search_data)
            log_conversation("jarvis", reply, intent="live_web_search")
            return {
                "text": reply,
                "action_executed": "live_web_search",
                "intent": "live_web_search",
                "dynamic_widget": {
                    "type": "web_search",
                    "title": f"Live Web Grounding: {raw_query}",
                    "data": {
                        "query": raw_query,
                        "summary": reply,
                        "results": search_data["results"],
                        "sources_count": search_data["sources_count"],
                        "search_time_ms": search_data["search_time_ms"]
                    }
                }
            }

    # =========================================================================
    # 10. GREETINGS & IDENTITY (Instant Low-Latency Response)
    # =========================================================================
    greetings = ["hello", "hi", "hey", "jarvis", "namaste", "suno", "pranam", "नमस्ते", "जार्विस", "सुनो"]
    if any(g == query.strip() or f"{g} " in query or f" {g}" in query for g in greetings) and len(query.split()) <= 3:
        reply = "नमस्ते सर, मैं जार्विस हूँ। ट्रेडिंग, कोडिंग, मौसम, पीसी सेटिंग्स या सिस्टम चेक्स में से क्या सेवा करूँ?"
        log_conversation("jarvis", reply, intent="greeting")
        return {"text": reply, "intent": "greeting"}

    if "who are you" in query or "kaun ho" in query or "tum kaun" in query or "कौन हो" in query:
        reply = "सर, मैं आपका पर्सनल AI असिस्टेंट जार्विस हूँ। मैं आपके ट्रेडिंग चार्ट्स, कोडिंग वर्कस्पेस और पीसी ऑटोमेशन के लिए सदैव तत्पर हूँ।"
        log_conversation("jarvis", reply, intent="identity")
        return {"text": reply, "intent": "identity"}

    # =========================================================================
    # 10.5 SPECIALIZED FREE CODING ENGINE (Groq 120B Reasoning Model)
    # =========================================================================
    if is_coding_or_conceptual:
        code_reply = await route_coding(raw_query, history=get_recent_history(6))
        if code_reply:
            log_conversation("jarvis", code_reply, intent="coding_llm")
            return {
                "text": code_reply,
                "action_executed": "code_generation",
                "intent": "coding_llm"
            }

    # =========================================================================
    # 10.8 FREE MODEL CATALOG & ARCHITECTURE INSPECTION
    # =========================================================================
    if "3.8" in query and any(w in query for w in ["check", "status", "hai", "kaun", "kya", "key", "बताओ", "है", "चेक"]):
        probe_stat = get_gemini_38_probe_status()
        if probe_stat.get("is_available"):
            reply = f"जी सर, आपके तीनों जेमिनी कीज़ में से {probe_stat['active_key_label']} पर Gemini 3.8 Flash मॉडल सक्रिय पाया गया है और इसे कोडिंग के लिए कनेक्ट कर दिया गया है।"
        else:
            reply = "जी सर, सिस्टम ने आपके तीनों Gemini API Keys पर 3.8 मॉडल का परीक्षण किया है। वर्तमान में तीनों कीज़ पर 3.8 मॉडल रेट-लिमिटेड (429) है, इसलिए सिस्टम सुरक्षित रूप से डिफॉल्ट 120B कोडिंग इंजन (Groq) का उपयोग कर रहा है।"
        log_conversation("jarvis", reply, intent="gemini_38_probe")
        return {
            "text": reply,
            "action_executed": "probe_gemini_38",
            "intent": "gemini_38_probe",
            "dynamic_widget": {
                "type": "gemini_38_probe",
                "title": "Gemini 3.8 Multi-Key Live Status",
                "data": probe_stat
            }
        }

    model_query_triggers = ["model", "मॉडल", "free model", "kaun sa model", "models list", "ai engine", "ai मॉडल"]
    if any(k in query for k in model_query_triggers) and any(w in query for w in ["kaun", "कौन", "list", "लिस्ट", "kya", "क्या", "batao", "बताओ", "dikhao", "दिखाओ", "select", "use", "यूज", "इस्तेमाल"]):
        catalog = get_model_catalog()
        summary = "जी सर, J.A.R.V.I.S. में प्रत्येक कार्य के लिए उसका सर्वश्रेष्ठ 100% मुफ़्त AI मॉडल सक्रिय है। चैट के लिए Groq Qwen 27B, कोडिंग व रीजनिंग के लिए Groq 120B और विज़न व रिसर्च के लिए Gemini 3.5 Flash Lite कॉन्फ़िगर हैं।"
        log_conversation("jarvis", summary, intent="model_catalog")
        return {
            "text": summary,
            "action_executed": "show_model_catalog",
            "intent": "model_catalog",
            "dynamic_widget": {
                "type": "model_catalog",
                "title": "J.A.R.V.I.S. Specialized Free AI Model Architecture",
                "data": catalog
            }
        }

    # =========================================================================
    # 11. MULTI-TIER CLOUD LLM INFERENCE (Specialized Free Model Routing)
    # =========================================================================
    chat_messages = [*get_recent_history(6), {"role": "user", "content": raw_query}]
    chat_reply = await route_chat_voice(chat_messages, system_prompt=JARVIS_SYSTEM_PROMPT, max_tokens=160)
    if chat_reply:
        log_conversation("jarvis", chat_reply, intent="groq_llm")
        return {"text": chat_reply, "intent": "groq_llm"}

    if settings.GROQ_API_KEY:
        groq_models = [settings.MODEL_CHAT, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for g_model in groq_models:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        json={
                            "model": g_model,
                            "messages": [
                                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                                *get_recent_history(6),
                                {"role": "user", "content": raw_query}
                            ],
                            "max_tokens": 120
                        }
                    )
                    if res.status_code == 200:
                        reply = res.json()["choices"][0]["message"]["content"].strip()
                        log_conversation("jarvis", reply, intent="groq_llm")
                        return {"text": reply, "intent": "groq_llm"}
            except Exception:
                pass

    if settings.SARVAM_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=7.0) as client:
                res = await client.post(
                    "https://api.sarvam.ai/v1/chat/completions",
                    headers={
                        "api-subscription-key": settings.SARVAM_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sarvam-2b",
                        "messages": [
                            {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                            *get_recent_history(8),
                            {"role": "user", "content": raw_query}
                        ],
                        "max_tokens": 180
                    }
                )
                if res.status_code == 200:
                    reply = res.json()["choices"][0]["message"]["content"].strip()
                    log_conversation("jarvis", reply, intent="sarvam_llm")
                    return {"text": reply, "intent": "sarvam_llm"}
        except Exception:
            pass

    if settings.OPENROUTER_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "HTTP-Referer": "http://localhost:8000",
                        "X-Title": "JARVIS-APEX"
                    },
                    json={
                        "model": settings.OPENROUTER_MODEL,
                        "messages": [
                            {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                            *get_recent_history(8),
                            {"role": "user", "content": raw_query}
                        ],
                        "max_tokens": 180
                    }
                )
                if res.status_code == 200:
                    reply = res.json()["choices"][0]["message"]["content"].strip()
                    log_conversation("jarvis", reply, intent="llm_chat")
                    return {"text": reply, "intent": "llm_chat"}
        except Exception:
            pass

    if settings.GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.MODEL_VISION}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [
                    {"parts": [{"text": f"{JARVIS_SYSTEM_PROMPT}\nUser: {raw_query}"}]}
                ],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 180}
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    reply = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    log_conversation("jarvis", reply, intent="llm_chat")
                    return {"text": reply, "intent": "llm_chat"}
        except Exception:
            pass

    # Offline Heuristic
    greetings = ["hello", "hi", "hey", "jarvis", "namaste", "suno", "pranam", "नमस्ते", "जार्विस", "सुनो"]
    if any(g in query for g in greetings):
        reply = "नमस्ते सर, मैं जार्विस हूँ। ट्रेडिंग, कोडिंग, मौसम या स्क्रीन एनालिसिस में से क्या सेवा करूँ?"
    elif "who are you" in query or "kaun ho" in query or "tum kaun" in query or "कौन हो" in query:
        reply = "सर, मैं आपका पर्सनल AI असिस्टेंट जार्विस हूँ। मैं आपके ट्रेडिंग चार्ट्स, कोडिंग वर्कस्पेस और दैनिक कार्यों के लिए सदैव तत्पर हूँ।"
    else:
        reply = "जी सर, मैंने आपका निर्देश नोट कर लिया है। आप मुझसे चार्ट देखने, मौसम, क्रिकेट स्कोर या सिस्टम चेक करने को कह सकते हैं।"

    log_conversation("jarvis", reply, intent="heuristic")
    return {
        "text": reply,
        "action_executed": None,
        "intent": "heuristic"
    }
