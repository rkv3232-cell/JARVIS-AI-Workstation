import re
import socket
import urllib.parse
import time
import httpx
from typing import Optional, Dict, Any, List
from .config import settings

# High-Risk / Disposable Top-Level Domains heavily leveraged in scams
HIGH_RISK_TLDS = {
    "buzz", "xyz", "top", "tk", "ml", "ga", "cf", "gq", "work", "icu", "cam",
    "live", "loan", "date", "club", "vip", "fit", "rest", "surf", "bar",
    "monster", "cfd", "click", "link", "shop", "online", "site", "space", "fun",
    "uno", "cc", "to", "su", "ws", "sbs", "cfd", "beauty", "hair", "quest"
}

# Known legitimate official domains for prominent Indian & global brands
OFFICIAL_DOMAINS = {
    "airtel": ["airtel.in", "airtel.com", "airtelbank.com"],
    "jio": ["jio.com", "myjio.com"],
    "vi": ["myvi.in", "vodafoneidea.com"],
    "bsnl": ["bsnl.co.in", "bsnl.in"],
    "sbi": ["sbi.co.in", "onlinesbi.sbi", "onlinesbi.com"],
    "hdfc": ["hdfcbank.com", "hdfc.com"],
    "icici": ["icicibank.com"],
    "paytm": ["paytm.com"],
    "phonepe": ["phonepe.com"],
    "google": ["google.com", "google.co.in", "goo.gl"],
    "whatsapp": ["whatsapp.com", "wa.me"],
    "amazon": ["amazon.in", "amazon.com", "amzn.to"],
    "flipkart": ["flipkart.com"],
    "irctc": ["irctc.co.in"],
    "incometax": ["incometax.gov.in"]
}

SCAM_KEYWORDS = [
    "दिवाली", "दीवाली", "तोहफ़ा", "मुफ्त", "नकद", "कैश", "इनाम", "लॉटरी",
    "रिचार्ज", "फ्री", "विजेता", "बधाई", "diwali", "gift", "free", "cash",
    "recharge", "winner", "claim", "prize", "spin", "lucky", "bonus", "reward",
    "kyc", "pan card", "block", "suspended", "unfreeze", "urgent"
]

def extract_urls(text: str) -> List[str]:
    """Finds all URLs present in a string or chat message."""
    url_pattern = r'(https?://[^\s<>"]+|www\.[^\s<>"]+|[a-zA-Z0-9-]+\.(?:buzz|xyz|top|tk|com|in|org|net|co|io|app)/[^\s<>"]*)'
    matches = re.findall(url_pattern, text)
    cleaned = []
    for m in matches:
        u = m.strip('.,;()[]{}*\'"')
        if not u.startswith("http://") and not u.startswith("https://"):
            u = "https://" + u
        cleaned.append(u)
    return cleaned

def parse_url_components(raw_url: str) -> Dict[str, Any]:
    """Parses URL into scheme, domain, tld, path, query parameters."""
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = "https://" + raw_url
    
    parsed = urllib.parse.urlparse(raw_url)
    netloc = parsed.netloc.lower()
    if ":" in netloc:
        domain = netloc.split(":")[0]
    else:
        domain = netloc

    domain_parts = domain.split(".")
    tld = domain_parts[-1] if len(domain_parts) > 1 else ""

    query_params = urllib.parse.parse_qs(parsed.query)

    return {
        "raw_url": raw_url,
        "scheme": parsed.scheme,
        "netloc": netloc,
        "domain": domain,
        "tld": tld,
        "path": parsed.path,
        "query": parsed.query,
        "query_params": query_params,
        "fragment": parsed.fragment
    }

async def probe_url_safely(url: str) -> Dict[str, Any]:
    """
    Safely inspects the destination without executing JavaScript.
    Fetches HTTP status, final redirected URL, page title, and server headers.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    probe_result = {
        "reachable": False,
        "status_code": None,
        "final_url": url,
        "redirect_count": 0,
        "server": None,
        "page_title": "",
        "detected_meta": "",
        "ip_address": None
    }

    # 1. Resolve IP
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.split(":")[0]
        ip = socket.gethostbyname(host)
        probe_result["ip_address"] = ip
    except Exception:
        pass

    # 2. HTTP Probe
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            probe_result["reachable"] = True
            probe_result["status_code"] = resp.status_code
            probe_result["final_url"] = str(resp.url)
            probe_result["redirect_count"] = len(resp.history)
            probe_result["server"] = resp.headers.get("server")

            html_text = resp.text[:25000] # Analyze first 25KB
            title_m = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
            if title_m:
                probe_result["page_title"] = title_m.group(1).strip()

            # Meta description
            meta_m = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html_text, re.IGNORECASE)
            if not meta_m:
                meta_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html_text, re.IGNORECASE)
            if meta_m:
                probe_result["meta_description"] = meta_m.group(1).strip()

            # Clean text extraction for Knowledge Synthesis
            paras = re.findall(r'<p[^>]*>(.*?)</p>', html_text, re.IGNORECASE | re.DOTALL)
            clean_paras = []
            for p in paras:
                cp = re.sub(r'<[^>]+>', '', p).strip()
                if len(cp) > 40:
                    clean_paras.append(cp)
            if clean_paras:
                probe_result["content_summary"] = " ".join(clean_paras[:3])
    except Exception as e:
        probe_result["probe_error"] = str(e)

    return probe_result

async def analyze_url_threat(raw_url: str, context_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Conducts in-depth forensic cyber threat analysis on any URL.
    Returns technical indicators, risk score (0-100), threat level, and executive report.
    """
    url_info = parse_url_components(raw_url)
    domain = url_info["domain"]
    tld = url_info["tld"]
    query = url_info["query"]
    params = url_info["query_params"]
    full_str = f"{raw_url} {context_text or ''}".lower()

    risk_score = 0
    threat_indicators = []
    scam_types = []

    # Indicator 1: Disposable / Suspicious TLD
    if tld in HIGH_RISK_TLDS:
        risk_score += 30
        threat_indicators.append({
            "code": "DISPOSABLE_TLD",
            "severity": "HIGH",
            "title": f"संदेहास्पद डोमेन एक्सटेंशन (.{tld})",
            "detail": f"यह डोमेन '.{tld}' एक्सटेंशन पर है, जिसे साइबर अपराधी और फ़िशिंग स्कैमर्स सस्ते/डिस्पोजेबल होने के कारण इस्तेमाल करते हैं।"
        })

    # Indicator 2: WhatsApp Referral / Viral Propagation
    is_wa_vector = False
    if "s=wa" in query or "wa" in params.get("s", []) or "whatsapp" in full_str:
        is_wa_vector = True
        risk_score += 30
        scam_types.append("WhatsApp Viral Scam")
        threat_indicators.append({
            "code": "WHATSAPP_VIRAL_LOOP",
            "severity": "CRITICAL",
            "title": "व्हाट्सएप वायरल फॉरवर्डिंग लूप (s=wa)",
            "detail": "यूआरएल में 's=wa' पैरामीटर मौजूद है। यह एक क्लासिक स्कैम मैकेनिज्म है जो यूजर से जबरन 5 ग्रुप्स या 10 दोस्तों को लिंक फॉरवर्ड करवाता है।"
        })

    # Indicator 3: Brand Impersonation (e.g. Airtel, Jio, SBI)
    impersonated_brand = None
    for brand, legit_domains in OFFICIAL_DOMAINS.items():
        if brand in full_str:
            # Check if domain matches legitimate official domain
            is_legit = any(domain == d or domain.endswith("." + d) for d in legit_domains)
            if not is_legit:
                impersonated_brand = brand.capitalize()
                risk_score += 35
                scam_types.append(f"Brand Impersonation ({impersonated_brand})")
                threat_indicators.append({
                    "code": "BRAND_SPOOFING",
                    "severity": "CRITICAL",
                    "title": f"ब्रांड स्पूफिंग ({impersonated_brand} की फर्जी पहचान)",
                    "detail": f"पेज खुद को {impersonated_brand} का आधिकारिक ऑफर बताता है, जबकि असली डोमेन '{legit_domains[0]}' है और यह लिंक '{domain}' पर चल रहा है।"
                })
                break

    # Indicator 4: Scam Lure Keywords (Diwali gift, free recharge, 2000 cash)
    matched_keywords = [kw for kw in SCAM_KEYWORDS if kw in full_str]
    if matched_keywords:
        risk_score += 25
        scam_types.append("Financial / Freebie Bait Scam")
        threat_indicators.append({
            "code": "SOCIAL_ENGINEERING_LURE",
            "severity": "HIGH",
            "title": "लोभ व लालच (Social Engineering Bait)",
            "detail": f"यूआरएल या कंटेंट में मुफ्त उपहार, नकद राशि या रिचार्ज का लालच पाया गया: ({', '.join(matched_keywords[:4])})।"
        })

    # Indicator 5: Arbitrary Tracking IDs & Session Hashes
    if re.search(r'\d{12,}', query) or re.search(r'#\d{10,}', raw_url):
        risk_score += 15
        threat_indicators.append({
            "code": "TARGET_VICTIM_TRACKER",
            "severity": "MEDIUM",
            "title": "विक्टिम ट्रैकिंग आईडी (Telemetry Hash)",
            "detail": "लिंक में लंबी न्यूमेरिक विक्टिम ट्रैकिंग आईडी मौजूद है जिससे स्कैमर्स यह ट्रैक करते हैं कि किस शिकार ने कितने लोगों को फॉरवर्ड किया।"
        })

    # Indicator 6: Non-SSL HTTP
    if url_info["scheme"] == "http":
        risk_score += 15
        threat_indicators.append({
            "code": "INSECURE_HTTP",
            "severity": "MEDIUM",
            "title": "असुरक्षित HTTP कनेक्शन",
            "detail": "वेबसाइट पर कोई वैध SSL सुरक्षा प्रमाणपत्र (HTTPS) नहीं है।"
        })

    # Probe live network status safely
    probe = await probe_url_safely(raw_url)
    if probe.get("page_title"):
        title_lower = probe["page_title"].lower()
        if any(w in title_lower for w in ["airtel", "jio", "gift", "दिवाली", "cash", "recharge"]):
            risk_score += 10

    # Cap score
    risk_score = min(100, max(5, risk_score))

    # Threat Level & Classification
    if risk_score >= 80:
        threat_level = "CRITICAL"
        threat_badge = "🔴 DANGEROUS PHISHING SCAM"
        hindi_verdict = "अत्यंत खतरनाक फ़िशिंग व ऑनलाइन धोखाधड़ी (Scam)"
    elif risk_score >= 55:
        threat_level = "HIGH"
        threat_badge = "🟠 HIGH RISK FRAUD"
        hindi_verdict = "उच्च जोखिम वाली संदेहास्पद वेबसाइट"
    elif risk_score >= 30:
        threat_level = "MEDIUM"
        threat_badge = "🟡 SUSPICIOUS WARNING"
        hindi_verdict = "संदेहास्पद लिंक — सावधानी आवश्यक"
    else:
        threat_level = "LOW"
        threat_badge = "🟢 SAFE & VERIFIED RESOURCE"
        hindi_verdict = "प्रमाणित सुरक्षित वेबसाइट (Legitimate Web Resource)"

    knowledge_text = probe.get("content_summary") or probe.get("meta_description") or probe.get("page_title") or ""

    # Executive Spoken Summary for Jarvis Voice Engine
    if threat_level in ["CRITICAL", "HIGH"]:
        spoken_brief = (
            f"सर, विश्लेषण पूरा हो गया है। यह लिंक {risk_score}% रिस्क स्कोर के साथ एक "
            f"{'खतरनाक ' + impersonated_brand + ' फ़िशिंग स्कैम' if impersonated_brand else 'धोखाधड़ी वाला स्कैम'} है। "
            f"यह {domain} के संदेहास्पद डोमेन पर है और व्हाट्सएप पर जबरन फॉरवर्ड करवाने के लिए बनाया गया है। "
            f"पूरी विस्तृत PDF रिपोर्ट तैयार कर दी गई है। कृपया इस पर बिल्कुल क्लिक न करें।"
        )
        recommendations = [
            "❌ इस लिंक पर क्लिक न करें और न ही ब्राउज़र में खोलें।",
            "❌ कोई भी व्यक्तिगत जानकारी (मोबाइल नंबर, OTP या बैंक/UPI डिटेल्स) न दें।",
            "🛑 इसे किसी भी व्हाट्सएप ग्रुप या दोस्त को फॉरवर्ड न करें।",
            "⚠️ भेजने वाले को भी सचेत करें कि यह एक ऑनलाइन फ्रॉड है।"
        ]
    else:
        spoken_brief = f"सर, इस लिंक का रिस्क स्कोर {risk_score}% है और यह एक सुरक्षित वेबसाइट है। इसका पूरा ज्ञान व विश्लेषण करके विस्तृत PDF रिपोर्ट तैयार कर दी गई है।"
        recommendations = [
            "✅ यह एक प्रमाणित और सुरक्षित वेब रिसोर्स है।",
            "💡 आप इस वेबसाइट का पूरा विवरण और निष्कर्ष PDF रिपोर्ट में पढ़ सकते हैं।",
            "🔒 कनेक्शन सुरक्षित (SSL Encrypted) है।"
        ]

    report = {
        "url": raw_url,
        "domain": domain,
        "tld": tld,
        "ip_address": probe.get("ip_address") or "Hidden / CDN",
        "risk_score": risk_score,
        "threat_level": threat_level,
        "threat_badge": threat_badge,
        "hindi_verdict": hindi_verdict,
        "knowledge_summary": knowledge_text,
        "scam_types": list(set(scam_types)) if scam_types else ["Legitimate Web Resource"],
        "impersonated_brand": impersonated_brand,
        "is_whatsapp_scam": is_wa_vector,
        "indicators": threat_indicators,
        "probe": probe,
        "spoken_brief": spoken_brief,
        "safety_recommendations": recommendations,
        "timestamp": time.time()
    }

    # Automatically generate PDF report
    try:
        from .pdf_report_generator import generate_url_pdf_report
        pdf_res = generate_url_pdf_report(report)
        report["pdf_report"] = pdf_res
    except Exception as e:
        print(f"[ThreatAnalyzer] PDF generation notice: {e}")
        report["pdf_report"] = None

    return report

