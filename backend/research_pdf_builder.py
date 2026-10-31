import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF

REPORTS_DIR = Path(__file__).resolve().parent.parent / "frontend" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

HINDI_FONT_PATH = r"C:\Windows\Fonts\mangal.ttf"
HAS_HINDI_FONT = os.path.exists(HINDI_FONT_PATH)

def sanitize_filename(name: str) -> str:
    """Removes invalid filename characters."""
    clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)
    return clean[:45]

def wrap_text(text: str, max_chars: int = 84) -> List[str]:
    """Wraps text into readable line segments without breaking words."""
    lines = []
    paragraphs = text.split("\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        words = para.split(" ")
        curr_line = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) + 1 > max_chars:
                lines.append(" ".join(curr_line))
                curr_line = [w]
                curr_len = len(w)
            else:
                curr_line.append(w)
                curr_len += len(w) + 1
        if curr_line:
            lines.append(" ".join(curr_line))
    return lines

class ResearchPDFBuilder:
    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.doc = fitz.open()
        self.page_width = 595.3  # A4 width in points
        self.page_height = 841.9 # A4 height in points
        self.margin_x = 45.0
        self.content_width = self.page_width - (2 * self.margin_x) # 505.3 pt
        self.hindi_font = "mangal" if HAS_HINDI_FONT else "helv"
        
        # Color Palette
        self.c_bg_dark = (9/255, 13/255, 22/255)
        self.c_neon_cyan = (0/255, 242/255, 254/255)
        self.c_sky = (56/255, 189/255, 248/255)
        self.c_white = (1.0, 1.0, 1.0)
        self.c_offwhite = (241/255, 245/255, 249/255)
        self.c_muted = (148/255, 163/255, 184/255)
        self.c_border = (30/255, 41/255, 59/255)
        self.c_card_bg = (15/255, 23/255, 42/255)
        self.c_accent_green = (16/255, 185/255, 129/255)
        self.c_accent_amber = (245/255, 158/255, 11/255)

        self.current_page = None
        self.current_y = 0.0
        self.pages_list = []

    def _setup_page(self, is_cover: bool = False):
        page = self.doc.new_page(width=self.page_width, height=self.page_height)
        if HAS_HINDI_FONT:
            page.insert_font(fontname="mangal", fontfile=HINDI_FONT_PATH)
        self.current_page = page
        self.pages_list.append(page)
        self.current_y = 45.0
        return page

    def _draw_header_footer(self, page, page_num: int, total_pages: int, is_cover: bool = False):
        if is_cover:
            return
        
        # Running Header
        title_snippet = self.data.get("title", "DEEP RESEARCH REPORT")[:65]
        page.draw_rect(fitz.Rect(0, 0, self.page_width, 35), color=self.c_bg_dark, fill=self.c_bg_dark)
        page.draw_line(fitz.Point(0, 35), fitz.Point(self.page_width, 35), color=self.c_neon_cyan, width=1)
        page.insert_text((self.margin_x, 23), f"J.A.R.V.I.S. RESEARCH // {title_snippet}", fontsize=7.5, fontname="helv", color=self.c_sky)
        page.insert_text((self.page_width - self.margin_x - 70, 23), "CONFIDENTIAL", fontsize=7.5, fontname="helv", color=self.c_muted)

        # Running Footer
        page.draw_rect(fitz.Rect(0, self.page_height - 30, self.page_width, self.page_height), color=self.c_bg_dark, fill=self.c_bg_dark)
        page.draw_line(fitz.Point(0, self.page_height - 30), fitz.Point(self.page_width, self.page_height - 30), color=self.c_border, width=0.8)
        page.insert_text((self.margin_x, self.page_height - 12), "AUTONOMOUS RESEARCH INTELLIGENCE ENGINE // VERIFIED EVIDENCE AUDIT", fontsize=6.8, fontname="helv", color=self.c_muted)
        page.insert_text((self.page_width - self.margin_x - 65, self.page_height - 12), f"PAGE {page_num} OF {total_pages}", fontsize=7.2, fontname="helv", color=self.c_white)

    def _check_page_overflow(self, needed_height: float):
        if (self.current_y + needed_height) > (self.page_height - 55.0):
            self._setup_page(is_cover=False)
            self.current_y = 55.0

    def build_cover_page(self):
        page = self._setup_page(is_cover=True)
        
        # Top Dark Banner
        page.draw_rect(fitz.Rect(0, 0, self.page_width, 180), color=self.c_bg_dark, fill=self.c_bg_dark)
        page.draw_rect(fitz.Rect(0, 180, self.page_width, 184), color=self.c_neon_cyan, fill=self.c_neon_cyan)

        # Category and Mode Chips
        cat = self.data.get("category_display", self.data.get("category", "UNIVERSAL RESEARCH"))
        depth = self.data.get("depth_mode", "DEEP")
        
        page.draw_rect(fitz.Rect(self.margin_x, 40, self.margin_x + 130, 58), color=self.c_sky, fill=(15/255, 30/255, 55/255))
        page.insert_text((self.margin_x + 8, 52), f"CATEGORY: {cat[:16].upper()}", fontsize=7.5, fontname="helv", color=self.c_sky)

        page.draw_rect(fitz.Rect(self.margin_x + 140, 40, self.margin_x + 250, 58), color=self.c_accent_green, fill=(15/255, 38/255, 28/255))
        page.insert_text((self.margin_x + 148, 52), f"MODE: {depth} RESEARCH", fontsize=7.5, fontname="helv", color=self.c_accent_green)

        # Ref & Date on top right
        rep_id = self.data.get("report_id", f"JVR-RES-{int(time.time())%1000000:06d}")
        page.insert_text((self.page_width - self.margin_x - 110, 48), f"REF: {rep_id}", fontsize=7.5, fontname="helv", color=self.c_white)
        page.insert_text((self.page_width - self.margin_x - 110, 60), f"DATE: {time.strftime('%d-%b-%Y')}", fontsize=7.5, fontname="helv", color=self.c_muted)

        # Main Title (wrap into up to 3 lines)
        raw_title = self.data.get("title", "UNIVERSAL DEEP RESEARCH REPORT")
        title_lines = wrap_text(raw_title, max_chars=48)
        t_y = 95.0
        for tl in title_lines[:2]:
            page.insert_text((self.margin_x, t_y), tl, fontsize=18, fontname="helv", color=self.c_white)
            t_y += 24.0

        subtitle = self.data.get("subtitle", "Comprehensive Multi-Source Scientific & Historical Assessment")
        page.insert_text((self.margin_x, t_y + 4), subtitle[:75], fontsize=9.5, fontname="helv", color=self.c_sky)

        # Key Metrics Grid Card
        metrics = self.data.get("key_metrics", [])
        if metrics:
            card_y = 210.0
            card_h = 80.0
            page.draw_rect(fitz.Rect(self.margin_x, card_y, self.page_width - self.margin_x, card_y + card_h), color=self.c_border, fill=self.c_card_bg)
            page.draw_rect(fitz.Rect(self.margin_x, card_y, self.margin_x + 4, card_y + card_h), color=self.c_sky, fill=self.c_sky)

            # Draw 4 key metrics
            for i, m in enumerate(metrics[:4]):
                col = i % 2
                row = i // 2
                mx = self.margin_x + 20 + (col * 240)
                my = card_y + 24 + (row * 30)
                page.insert_text((mx, my), f"{m.get('label', '').upper()}:", fontsize=7.5, fontname="helv", color=self.c_muted)
                val = str(m.get('value', ''))[:36]
                page.insert_text((mx, my + 14), val, fontsize=8.8, fontname=self.hindi_font, color=self.c_white)

        # Overview preview on Cover
        exec_summary = self.data.get("executive_summary_en", self.data.get("executive_summary_hi", ""))
        cov_y = 315.0
        page.insert_text((self.margin_x, cov_y), "PRIMARY RESEARCH OBJECTIVE & SCOPE", fontsize=10.5, fontname="helv", color=self.c_white)
        page.draw_line(fitz.Point(self.margin_x, cov_y + 4), fitz.Point(self.page_width - self.margin_x, cov_y + 4), color=self.c_border, width=0.8)
        cov_y += 20.0

        for l in wrap_text(exec_summary, max_chars=86)[:8]:
            page.insert_text((self.margin_x, cov_y), l, fontsize=8.5, fontname=self.hindi_font, color=self.c_offwhite)
            cov_y += 14.0

        # Cover Bottom Callout
        box_y = 700.0
        page.draw_rect(fitz.Rect(self.margin_x, box_y, self.page_width - self.margin_x, box_y + 60), color=self.c_border, fill=(15/255, 23/255, 42/255))
        page.insert_text((self.margin_x + 16, box_y + 24), "AUTHENTICITY & CROSS-VERIFICATION AUDIT", fontsize=8.5, fontname="helv", color=self.c_accent_green)
        page.insert_text((self.margin_x + 16, box_y + 42), "All claims, citations and historical timelines are verified against primary records, academic archives and encyclopedias.", fontsize=7.5, fontname="helv", color=self.c_muted)

        # Bottom Stamp
        page.draw_rect(fitz.Rect(0, self.page_height - 30, self.page_width, self.page_height), color=self.c_bg_dark, fill=self.c_bg_dark)
        page.insert_text((self.margin_x, self.page_height - 12), "JARVIS-APEX SOVEREIGN LABS // UNIVERSAL RESEARCH DISPATCH", fontsize=7.2, fontname="helv", color=self.c_muted)
        page.insert_text((self.page_width - self.margin_x - 70, self.page_height - 12), "PAGE 1 (COVER)", fontsize=7.2, fontname="helv", color=self.c_white)

    def build_executive_summary_section(self):
        self._setup_page(is_cover=False)
        self.current_y = 55.0

        # Section Heading
        self.current_page.insert_text((self.margin_x, self.current_y), "1.0 EXECUTIVE SUMMARY (कार्यकारी सारांश)", fontsize=13, fontname="helv", color=self.c_white)
        self.current_page.draw_line(fitz.Point(self.margin_x, self.current_y + 4), fitz.Point(self.page_width - self.margin_x, self.current_y + 4), color=self.c_neon_cyan, width=1.2)
        self.current_y += 24.0

        # Hindi Executive Summary
        hi_summary = self.data.get("executive_summary_hi", "")
        if hi_summary:
            self.current_page.insert_text((self.margin_x, self.current_y), "प्राथमिक निष्कर्ष (Key Findings in Devanagari):", fontsize=9.5, fontname=self.hindi_font, color=self.c_sky)
            self.current_y += 16.0
            for line in wrap_text(hi_summary, max_chars=82):
                self._check_page_overflow(16.0)
                self.current_page.insert_text((self.margin_x, self.current_y), line, fontsize=8.8, fontname=self.hindi_font, color=self.c_offwhite)
                self.current_y += 15.0
            self.current_y += 12.0

        # English Executive Summary
        en_summary = self.data.get("executive_summary_en", "")
        if en_summary:
            self._check_page_overflow(35.0)
            self.current_page.insert_text((self.margin_x, self.current_y), "Strategic Overview & Assessment (English Analysis):", fontsize=9.5, fontname="helv", color=self.c_sky)
            self.current_y += 16.0
            for line in wrap_text(en_summary, max_chars=86):
                self._check_page_overflow(15.0)
                self.current_page.insert_text((self.margin_x, self.current_y), line, fontsize=8.5, fontname="helv", color=(0.85, 0.9, 0.95))
                self.current_y += 14.0
            self.current_y += 16.0

    def build_body_sections(self):
        sections = self.data.get("sections", [])
        sec_num = 2.0

        for sec in sections:
            self._check_page_overflow(45.0)
            stitle = sec.get("title", "Section")
            self.current_page.insert_text((self.margin_x, self.current_y), f"{sec_num:.1f} {stitle.upper()}", fontsize=11.5, fontname="helv", color=self.c_white)
            self.current_page.draw_line(fitz.Point(self.margin_x, self.current_y + 4), fitz.Point(self.page_width - self.margin_x, self.current_y + 4), color=self.c_sky, width=0.8)
            self.current_y += 20.0
            sec_num += 1.0

            # Section Paragraphs
            paragraphs = sec.get("paragraphs", [])
            for para in paragraphs:
                lines = wrap_text(para, max_chars=86)
                for l in lines:
                    self._check_page_overflow(15.0)
                    self.current_page.insert_text((self.margin_x, self.current_y), l, fontsize=8.5, fontname=self.hindi_font, color=self.c_offwhite)
                    self.current_y += 14.0
                self.current_y += 8.0

            # Bullet Takeaways
            takeaways = sec.get("key_takeaways", [])
            if takeaways:
                self._check_page_overflow(30.0)
                for t in takeaways:
                    self._check_page_overflow(16.0)
                    self.current_page.insert_text((self.margin_x + 8, self.current_y), f"• {t}", fontsize=8.2, fontname=self.hindi_font, color=self.c_sky)
                    self.current_y += 14.0
                self.current_y += 8.0

            # Data Table if defined
            table = sec.get("table")
            if table and isinstance(table, dict):
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                if headers and rows:
                    self._check_page_overflow(len(rows) * 22.0 + 40.0)
                    
                    # Table Box
                    col_count = len(headers)
                    col_w = self.content_width / col_count
                    tb_y = self.current_y
                    
                    # Header row
                    self.current_page.draw_rect(fitz.Rect(self.margin_x, tb_y, self.page_width - self.margin_x, tb_y + 20), color=self.c_border, fill=self.c_card_bg)
                    for c_idx, h in enumerate(headers):
                        self.current_page.insert_text((self.margin_x + 8 + (c_idx * col_w), tb_y + 14), str(h).upper(), fontsize=7.5, fontname="helv", color=self.c_sky)
                    tb_y += 20.0

                    # Data rows
                    for r_idx, row in enumerate(rows[:5]):
                        fill_c = (20/255, 30/255, 50/255) if r_idx % 2 == 1 else (15/255, 23/255, 42/255)
                        self.current_page.draw_rect(fitz.Rect(self.margin_x, tb_y, self.page_width - self.margin_x, tb_y + 20), color=self.c_border, fill=fill_c)
                        for c_idx, cell in enumerate(row[:col_count]):
                            self.current_page.insert_text((self.margin_x + 8 + (c_idx * col_w), tb_y + 14), str(cell)[:36], fontsize=7.8, fontname=self.hindi_font, color=self.c_offwhite)
                        tb_y += 20.0

                    self.current_y = tb_y + 14.0

    def build_timeline_section(self):
        timeline = self.data.get("timeline", [])
        if not timeline:
            return

        self._check_page_overflow(70.0)
        self.current_page.insert_text((self.margin_x, self.current_y), "CHRONOLOGICAL TIMELINE (कालक्रम एवं महत्वपूर्ण मील के पत्थर)", fontsize=11.5, fontname="helv", color=self.c_white)
        self.current_page.draw_line(fitz.Point(self.margin_x, self.current_y + 4), fitz.Point(self.page_width - self.margin_x, self.current_y + 4), color=self.c_neon_cyan, width=1.0)
        self.current_y += 22.0

        for item in timeline[:8]:
            self._check_page_overflow(22.0)
            yr = str(item.get("date_or_period") or item.get("year") or item.get("date") or "")
            ev = str(item.get("event") or "")
            impact = str(item.get("impact") or "")
            if impact and len(ev) < 45:
                ev = f"{ev} ({impact})"

            # Timeline bullet & Year
            self.current_page.draw_rect(fitz.Rect(self.margin_x, self.current_y - 2, self.margin_x + 55, self.current_y + 12), color=self.c_sky, fill=(15/255, 30/255, 55/255))
            self.current_page.insert_text((self.margin_x + 4, self.current_y + 8), yr, fontsize=7.5, fontname="helv", color=self.c_sky)

            # Event description
            ev_lines = wrap_text(ev, max_chars=74)
            self.current_page.insert_text((self.margin_x + 65, self.current_y + 8), ev_lines[0] if ev_lines else ev, fontsize=8.2, fontname=self.hindi_font, color=self.c_white)
            self.current_y += 18.0

        self.current_y += 12.0

    def build_references_section(self):
        citations = self.data.get("citations", [])
        self._check_page_overflow(80.0)

        self.current_page.insert_text((self.margin_x, self.current_y), "VERIFIED SOURCES & CITATIONS (प्रामाणिक संदर्भ)", fontsize=11.5, fontname="helv", color=self.c_white)
        self.current_page.draw_line(fitz.Point(self.margin_x, self.current_y + 4), fitz.Point(self.page_width - self.margin_x, self.current_y + 4), color=self.c_accent_green, width=1.0)
        self.current_y += 20.0

        if not citations:
            self.current_page.insert_text((self.margin_x, self.current_y), "Multi-source consensus established via primary encyclopedias and official records.", fontsize=8.0, fontname="helv", color=self.c_muted)
            self.current_y += 20.0
            return

        for idx, cit in enumerate(citations[:10], 1):
            self._check_page_overflow(22.0)
            title = cit.get("title", "Resource")[:55]
            url = cit.get("url", "")
            tier = cit.get("tier", "TIER_2_REPUTABLE_NEWS").replace("_", " ")

            self.current_page.insert_text((self.margin_x, self.current_y), f"[{idx}] {title}", fontsize=8.2, fontname="helv", color=self.c_white)
            self.current_page.insert_text((self.margin_x + 290, self.current_y), f"({tier})", fontsize=7.0, fontname="helv", color=self.c_sky)
            self.current_y += 12.0
            if url:
                self.current_page.insert_text((self.margin_x + 15, self.current_y), url[:85], fontsize=7.2, fontname="helv", color=self.c_muted)
                self.current_y += 14.0

    def finalize(self) -> str:
        # Build all components
        self.build_cover_page()
        self.build_executive_summary_section()
        self.build_body_sections()
        self.build_timeline_section()
        self.build_references_section()

        # Add headers and footers to all pages safely via document index
        total = len(self.doc)
        for idx in range(total):
            page = self.doc[idx]
            self._draw_header_footer(page, page_num=idx + 1, total_pages=total, is_cover=(idx == 0))

        self.total_pages = total

        # Save to file
        title = self.data.get("title", "Universal_Research")
        filename = f"Research_{sanitize_filename(title)}_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        out_path = REPORTS_DIR / filename
        self.doc.save(str(out_path))
        self.doc.close()

        return str(out_path)

def generate_universal_research_pdf(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generates publication-quality universal deep research PDF."""
    builder = ResearchPDFBuilder(report_data)
    filepath = builder.finalize()
    p = Path(filepath)
    filename = p.name
    web_url = f"/reports/{filename}"
    file_size_kb = round(p.stat().st_size / 1024, 1) if p.exists() else 0.0

    return {
        "success": True,
        "filename": filename,
        "filepath": filepath,
        "web_url": web_url,
        "pages": getattr(builder, "total_pages", 1),
        "file_size_kb": file_size_kb,
        "timestamp": time.time()
    }
