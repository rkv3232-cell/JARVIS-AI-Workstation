import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional
import fitz  # PyMuPDF

REPORTS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

HINDI_FONT_PATH = r"C:\Windows\Fonts\mangal.ttf"
HAS_HINDI_FONT = os.path.exists(HINDI_FONT_PATH)

def sanitize_filename(name: str) -> str:
    """Removes invalid filename characters."""
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)

def wrap_text(text: str, max_chars: int = 80) -> list[str]:
    """Simple text wrapping utility for clean PDF rendering."""
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        words = paragraph.split(" ")
        current_line = []
        current_len = 0
        for w in words:
            if current_len + len(w) + 1 > max_chars:
                lines.append(" ".join(current_line))
                current_line = [w]
                current_len = len(w)
            else:
                current_line.append(w)
                current_len += len(w) + 1
        if current_line:
            lines.append(" ".join(current_line))
    return lines

def generate_url_pdf_report(report_data: Dict[str, Any], custom_filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates an executive, professional Cyber & Web Intelligence PDF report.
    Returns file metadata including local path and web accessible URL.
    """
    domain = report_data.get("domain", "web_analysis")
    clean_domain = sanitize_filename(domain)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    report_id = f"JARVIS-REP-{int(time.time()) % 1000000:06d}"
    
    filename = custom_filename or f"Report_{clean_domain}_{timestamp_str}.pdf"
    filepath = REPORTS_DIR / filename

    doc = fitz.open()
    page = doc.new_page(width=595.3, height=841.9) # A4 size

    # Register Hindi Font if present
    font_name = "helv"
    hindi_font_name = "mangal" if HAS_HINDI_FONT else "helv"
    if HAS_HINDI_FONT:
        page.insert_font(fontname="mangal", fontfile=HINDI_FONT_PATH)

    # Palette
    c_dark_navy = (9/255, 13/255, 22/255)
    c_cyan = (0/255, 242/255, 254/255)
    c_sky = (56/255, 189/255, 248/255)
    c_white = (1.0, 1.0, 1.0)
    c_muted = (148/255, 163/255, 184/255)
    c_border = (30/255, 41/255, 59/255)

    risk_score = report_data.get("risk_score", 0)
    if risk_score >= 80:
        c_accent = (244/255, 63/255, 94/255)   # Red
        c_accent_bg = (38/255, 15/255, 23/255)
        risk_label = "CRITICAL / DANGEROUS PHISHING"
    elif risk_score >= 55:
        c_accent = (249/255, 115/255, 22/255)  # Orange
        c_accent_bg = (38/255, 22/255, 15/255)
        risk_label = "HIGH RISK FRAUD"
    elif risk_score >= 30:
        c_accent = (234/255, 179/255, 8/255)   # Yellow
        c_accent_bg = (38/255, 32/255, 15/255)
        risk_label = "SUSPICIOUS / UNVERIFIED"
    else:
        c_accent = (16/255, 185/255, 129/255)  # Emerald
        c_accent_bg = (15/255, 38/255, 28/255)
        risk_label = "SAFE / VERIFIED RESOURCE"

    # =========================================================================
    # 1. HEADER BANNER
    # =========================================================================
    page.draw_rect(fitz.Rect(0, 0, 595.3, 85), color=c_dark_navy, fill=c_dark_navy)
    page.draw_rect(fitz.Rect(0, 85, 595.3, 88), color=c_cyan, fill=c_cyan)

    page.insert_text((40, 36), "J.A.R.V.I.S. INTELLIGENCE & FORENSICS LAB", fontsize=15, fontname="helv", color=c_white)
    page.insert_text((40, 52), "UNIVERSAL WEB & CYBER THREAT ASSESSMENT REPORT", fontsize=8.5, fontname="helv", color=c_sky)
    page.insert_text((40, 68), "Sovereign Autonomous Workstation Engine // Multi-Modal Truth Discovery", fontsize=7.5, fontname="helv", color=c_muted)

    page.insert_text((440, 34), f"REF ID: {report_id}", fontsize=8, fontname="helv", color=c_white)
    page.insert_text((440, 48), f"DATE: {time.strftime('%d-%b-%Y')}", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((440, 62), f"TIME: {time.strftime('%H:%M:%S IST')}", fontsize=8, fontname="helv", color=c_muted)

    # =========================================================================
    # 2. TARGET OVERVIEW & THREAT SCORE CARD
    # =========================================================================
    y = 105
    page.draw_rect(fitz.Rect(40, y, 555.3, y + 80), color=c_border, fill=c_accent_bg)
    page.draw_rect(fitz.Rect(40, y, 46, y + 80), color=c_accent, fill=c_accent)

    # Risk Meter Badge
    page.draw_rect(fitz.Rect(54, y + 14, 150, y + 66), color=c_accent, fill=c_accent)
    page.insert_text((64, y + 42), f"{risk_score}%", fontsize=24, fontname="helv", color=c_white)
    page.insert_text((64, y + 58), "RISK SCORE", fontsize=8, fontname="helv", color=c_white)

    # Target Metadata
    page.insert_text((165, y + 25), "TARGET DOMAIN:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((245, y + 25), domain, fontsize=9.5, fontname="helv", color=c_white)

    page.insert_text((165, y + 42), "ASSESSMENT:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((245, y + 42), risk_label, fontsize=9, fontname="helv", color=c_accent)

    page.insert_text((165, y + 59), "SERVER / IP:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((245, y + 59), f"{report_data.get('ip_address', 'Unknown')} ({report_data.get('probe', {}).get('server', 'CDN')})", fontsize=8.5, fontname="helv", color=c_sky)

    page.insert_text((420, y + 25), "TLD EXTENSION:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((495, y + 25), f".{report_data.get('tld', 'N/A')}", fontsize=9, fontname="helv", color=c_white)

    page.insert_text((420, y + 42), "PROPAGATION:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((495, y + 42), "WhatsApp" if report_data.get("is_whatsapp_scam") else "Web Direct", fontsize=8.5, fontname="helv", color=c_white)

    page.insert_text((420, y + 59), "BRAND SPOOF:", fontsize=8, fontname="helv", color=c_muted)
    page.insert_text((495, y + 59), str(report_data.get("impersonated_brand") or "None"), fontsize=8.5, fontname="helv", color=c_accent if report_data.get("impersonated_brand") else c_muted)

    # Target URL box
    y += 92
    raw_url = report_data.get("url", "")
    page.draw_rect(fitz.Rect(40, y, 555.3, y + 24), color=c_border, fill=(15/255, 23/255, 42/255))
    page.insert_text((48, y + 16), f"URL: {raw_url[:92]}..." if len(raw_url) > 92 else f"URL: {raw_url}", fontsize=7.5, fontname="helv", color=c_sky)

    # =========================================================================
    # 3. EXECUTIVE SUMMARY & FORENSIC VERDICT
    # =========================================================================
    y += 38
    page.insert_text((40, y), "1. EXECUTIVE SUMMARY & VERDICT (मुख्य निष्कर्ष)", fontsize=11, fontname="helv", color=c_white)
    page.draw_line(fitz.Point(40, y + 4), fitz.Point(555.3, y + 4), color=c_sky, width=1)
    y += 18

    # Hindi verdict
    hindi_verdict = report_data.get("hindi_verdict", "")
    if hindi_verdict:
        page.insert_text((45, y), f"निष्कर्ष: {hindi_verdict}", fontsize=9.5, fontname=hindi_font_name, color=c_accent)
        y += 16

    spoken_brief = report_data.get("spoken_brief", "")
    for line in wrap_text(spoken_brief, max_chars=82):
        page.insert_text((45, y), line, fontsize=8.5, fontname=hindi_font_name, color=(0.85, 0.9, 0.95))
        y += 14

    y += 10
    # =========================================================================
    # 4. FORENSIC THREAT INDICATORS
    # =========================================================================
    page.insert_text((40, y), "2. FORENSIC THREAT INDICATORS (पहचाने गए तकनीकी खतरे)", fontsize=11, fontname="helv", color=c_white)
    page.draw_line(fitz.Point(40, y + 4), fitz.Point(555.3, y + 4), color=c_sky, width=1)
    y += 18

    indicators = report_data.get("indicators", [])
    if not indicators:
        page.insert_text((45, y), "कोई प्रत्यक्ष मैलवेयर, फ़िशिंग या अनधिकृत स्क्रिप्ट्स नहीं पाई गईं। डोमेन सुरक्षित प्रतीत होता है।", fontsize=8.5, fontname=hindi_font_name, color=c_muted)
        y += 20
    else:
        for ind in indicators[:5]: # Up to top 5 indicators
            # Draw indicator box
            page.draw_rect(fitz.Rect(40, y, 555.3, y + 38), color=c_border, fill=(15/255, 23/255, 42/255))
            
            # Severity tag
            sev = ind.get("severity", "HIGH")
            tag_color = c_accent if sev == "CRITICAL" else (c_accent if sev == "HIGH" else c_sky)
            page.draw_rect(fitz.Rect(46, y + 6, 102, y + 18), color=tag_color, fill=tag_color)
            page.insert_text((50, y + 15), sev, fontsize=7, fontname="helv", color=c_white)

            # Title
            title = ind.get("title", "")
            page.insert_text((110, y + 15), title, fontsize=8.5, fontname=hindi_font_name, color=c_white)

            # Detail
            detail = ind.get("detail", "")
            detail_lines = wrap_text(detail, max_chars=95)
            detail_y = y + 28
            for dl in detail_lines[:1]:
                page.insert_text((46, detail_y), dl, fontsize=7.5, fontname=hindi_font_name, color=c_muted)
            y += 44

    # Knowledge Highlights if available
    knowledge = report_data.get("knowledge_summary", "")
    if knowledge and len(indicators) <= 2:
        page.insert_text((40, y), "2.5 WEBPAGE KNOWLEDGE & HIGHLIGHTS (वेबसाइट का मुख्य विवरण)", fontsize=10, fontname="helv", color=c_white)
        page.draw_line(fitz.Point(40, y + 4), fitz.Point(555.3, y + 4), color=c_sky, width=1)
        y += 16
        for kl in wrap_text(knowledge, max_chars=90)[:3]:
            page.insert_text((45, y), kl, fontsize=7.5, fontname="helv", color=(0.8, 0.9, 0.95))
            y += 12
        y += 6

    y += 10
    # =========================================================================
    # 5. SAFETY PROTOCOL & RECOMMENDED ACTIONS
    # =========================================================================
    page.insert_text((40, y), "3. SAFETY PROTOCOL & ADVISORY (सुरक्षा सलाह)", fontsize=11, fontname="helv", color=c_white)
    page.draw_line(fitz.Point(40, y + 4), fitz.Point(555.3, y + 4), color=c_sky, width=1)
    y += 18

    page.draw_rect(fitz.Rect(40, y, 555.3, y + 80), color=(245/255, 158/255, 11/255), fill=(30/255, 20/255, 10/255))
    recs = report_data.get("safety_recommendations", [])
    rec_y = y + 18
    for r in recs[:4]:
        page.insert_text((50, rec_y), r, fontsize=8.5, fontname=hindi_font_name, color=(0.95, 0.95, 0.95))
        rec_y += 15

    # Helpline banner
    page.insert_text((50, rec_y), "राष्ट्रीय साइबर क्राइम हेल्पलाइन: डायल 1930 | पोर्टल: cybercrime.gov.in", fontsize=8, fontname=hindi_font_name, color=c_sky)

    # =========================================================================
    # 6. FOOTER
    # =========================================================================
    page.draw_rect(fitz.Rect(0, 815, 595.3, 841.9), color=c_dark_navy, fill=c_dark_navy)
    page.insert_text((40, 831), "J.A.R.V.I.S. APEX 2.0 // AUTONOMOUS SECURITY LAB // OFFICIAL DIGITAL AUDIT", fontsize=7.5, fontname="helv", color=c_muted)
    page.insert_text((490, 831), "PAGE 1 OF 1", fontsize=7.5, fontname="helv", color=c_white)

    doc.save(str(filepath))
    doc.close()

    web_url = f"/reports/{filename}"
    return {
        "success": True,
        "filename": filename,
        "filepath": str(filepath),
        "web_url": web_url,
        "report_id": report_id,
        "timestamp": time.time()
    }
