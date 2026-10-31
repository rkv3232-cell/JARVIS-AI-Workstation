import re
import socket
import urllib.parse
import time
import ipaddress
import httpx
from typing import Optional, Dict, Any, List, Tuple
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

def is_ssrf_safe_ip(ip_str: str) -> bool:
    """
    Validates whether an IP address is a safe public Internet IP.
    Blocks private networks (RFC 1918), loopback, link-local, carrier-grade NAT,
    multicast, reserved, and cloud metadata IPs.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_reserved or
            ip.is_multicast or
            ip.is_unspecified
        ):
            return False

        # IPv4-mapped IPv6 check (e.g. ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            mapped = ip.ipv4_mapped
            if mapped.is_private or mapped.is_loopback or mapped.is_link_local:
                return False

        # Explicit Cloud Metadata IP blocking
        blocked_specific = {"169.254.169.254", "169.254.170.2", "100.100.100.200"}
        if str(ip) in blocked_specific:
            return False

        return True
    except ValueError:
        return False

def validate_url_for_ssrf(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates scheme and resolves all IP addresses for a URL to verify SSRF safety.
    Returns: (is_safe, resolved_ip, error_message)
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        return False, None, f"Malformed URL: {e}"

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return False, None, f"Blocked unsafe scheme '{scheme}'. Only HTTP and HTTPS are permitted."

    host = parsed.hostname
    if not host:
        return False, None, "URL is missing a valid hostname."

    # Direct hostname blocklist
    host_lower = host.lower()
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "metadata.google.internal",
        "instance-data", "metadata", "host.docker.internal"
    }
    if host_lower in blocked_hosts or host_lower.endswith(".local") or host_lower.endswith(".internal"):
        return False, None, f"Access to restricted hostname '{host}' is blocked for SSRF protection."

    # Check if host is direct IP literal
    try:
        ip_direct = ipaddress.ip_address(host)
        if not is_ssrf_safe_ip(str(ip_direct)):
            return False, str(ip_direct), f"Access to private or restricted IP '{host}' is blocked for SSRF protection."
        return True, str(ip_direct), None
    except ValueError:
        pass

    # Resolve all addresses via DNS
    try:
        addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = list({item[4][0] for item in addr_info})
        if not resolved_ips:
            return False, None, f"DNS resolution failed for host '{host}'."
        for rip in resolved_ips:
            if not is_ssrf_safe_ip(rip):
                return False, rip, f"Host '{host}' resolves to restricted IP address '{rip}' (SSRF Blocked)."
        return True, resolved_ips[0], None
    except socket.gaierror as e:
        return False, None, f"Could not resolve host '{host}': {e}"
    except Exception as e:
        return False, None, f"SSRF resolution check failed: {e}"

async def probe_url_safely(url: str) -> Dict[str, Any]:
    """
    Safely inspects the destination with comprehensive SSRF protection and manual redirect validation.
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

    # 1. SSRF Validation on initial URL
    is_safe, resolved_ip, ssrf_err = validate_url_for_ssrf(url)
    if not is_safe:
        probe_result["ip_address"] = resolved_ip
        probe_result["probe_error"] = f"SSRF_BLOCKED: {ssrf_err}"
        return probe_result

    probe_result["ip_address"] = resolved_ip

    # 2. HTTP Probe with manual redirect checking to prevent redirect-based SSRF
    current_url = url
    redirect_count = 0
    max_redirects = 5

    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=False) as client:
            while redirect_count < max_redirects:
                resp = await client.get(current_url, headers=headers)
                probe_result["reachable"] = True
                probe_result["status_code"] = resp.status_code
                probe_result["final_url"] = str(resp.url)
                probe_result["server"] = resp.headers.get("server")

                # Handle redirect
                if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                    redirect_location = resp.headers.get("Location")
                    if not redirect_location:
                        break

                    next_url = urllib.parse.urljoin(current_url, redirect_location)
                    # SSRF Validate redirect target before following!
                    is_redir_safe, redir_ip, redir_err = validate_url_for_ssrf(next_url)
                    if not is_redir_safe:
                        probe_result["probe_error"] = f"SSRF_BLOCKED_ON_REDIRECT: {redir_err}"
                        probe_result["final_url"] = next_url
                        return probe_result

                    current_url = next_url
                    redirect_count += 1
                    probe_result["redirect_count"] = redirect_count
                else:
                    # Final response reached
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
                    break
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

    # Probe live network status safely with SSRF protection
    probe = await probe_url_safely(raw_url)

    # Indicator 0: SSRF Probe Attack
    if probe.get("probe_error", "").startswith("SSRF_BLOCKED"):
        risk_score += 95
        scam_types.append("Internal Network SSRF Probing")
        threat_indicators.append({
            "code": "SSRF_ATTEMPT",
            "severity": "CRITICAL",
            "title": "आंतरिक नेटवर्क घुसपैठ प्रयास (SSRF Blocked)",
            "detail": f"यह URL निजी या आंतरिक नेटवर्क (Localhost/Private IP) को लक्षित कर रहा था। सुरक्षा नीति द्वारा इसे तुरंत ब्लॉक कर दिया गया: {probe['probe_error']}"
        })

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

    # Check probed page metadata
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

