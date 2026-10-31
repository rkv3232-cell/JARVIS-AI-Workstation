"""
Execution script for pdf_generator skill.
Builds compact, publication-ready research PDF reports with zero unnecessary whitespace.
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path

def find_browser():
    possible = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")
    ]
    for p in possible:
        if os.path.exists(p):
            return p
    return None

def build_compact_html(title: str, subtitle: str, sections: list, author: str = "JARVIS APEX"):
    now_str = time.strftime("%d %b %Y, %H:%M IST")
    
    sec_html = ""
    for sec in sections:
        heading = sec.get("heading", "Analysis Section")
        content = sec.get("content", "")
        table = sec.get("table_data")
        
        tbl_html = ""
        if table and isinstance(table, list) and len(table) > 0:
            headers = table[0].keys() if isinstance(table[0], dict) else [f"Col {i+1}" for i in range(len(table[0]))]
            tbl_html += "<table class='dense-table'><thead><tr>"
            for h in headers:
                tbl_html += f"<th>{h}</th>"
            tbl_html += "</tr></thead><tbody>"
            for row in table:
                tbl_html += "<tr>"
                if isinstance(row, dict):
                    for h in headers:
                        tbl_html += f"<td>{row.get(h, '')}</td>"
                else:
                    for cell in row:
                        tbl_html += f"<td>{cell}</td>"
                tbl_html += "</tr>"
            tbl_html += "</tbody></table>"

        sec_html += f"""
        <div class="compact-section">
          <h3 class="sec-title">{heading}</h3>
          <p class="sec-body">{content}</p>
          {tbl_html}
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 12mm 15mm;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    background: #fff;
    margin: 0;
    padding: 0;
    font-size: 9.5pt;
    line-height: 1.35;
  }}
  .doc-header {{
    border-bottom: 2px solid #0284c7;
    padding-bottom: 6px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .doc-title {{
    font-size: 16pt;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
  }}
  .doc-subtitle {{
    font-size: 10pt;
    font-weight: 500;
    color: #475569;
    margin: 2px 0 0 0;
  }}
  .doc-meta {{
    font-size: 8pt;
    color: #64748b;
    text-align: right;
  }}
  .compact-section {{
    margin-bottom: 8px;
    page-break-inside: avoid;
  }}
  .sec-title {{
    font-size: 11pt;
    font-weight: 700;
    color: #0369a1;
    margin: 6px 0 3px 0;
    border-left: 3px solid #0284c7;
    padding-left: 6px;
  }}
  .sec-body {{
    margin: 0 0 4px 0;
    color: #334155;
    text-align: justify;
  }}
  .dense-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4px 0 8px 0;
    font-size: 8.5pt;
  }}
  .dense-table th, .dense-table td {{
    border: 1px solid #cbd5e1;
    padding: 3px 6px;
    text-align: left;
  }}
  .dense-table th {{
    background: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
  }}
  .dense-table tr:nth-child(even) {{
    background: #f8fafc;
  }}
  .doc-footer {{
    margin-top: 15px;
    border-top: 1px solid #e2e8f0;
    padding-top: 4px;
    font-size: 7.5pt;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>
  <div class="doc-header">
    <div>
      <h1 class="doc-title">{title}</h1>
      <p class="doc-subtitle">{subtitle}</p>
    </div>
    <div class="doc-meta">
      <div><strong>Author:</strong> {author}</div>
      <div><strong>Date:</strong> {now_str}</div>
    </div>
  </div>

  <main>
    {sec_html}
  </main>

  <div class="doc-footer">
    <span>J.A.R.V.I.S. APEX Sovereign Intelligence Report</span>
    <span>CONFIDENTIAL & PROPRIETARY</span>
  </div>
</body>
</html>
"""
    return html

def main():
    try:
        raw = sys.stdin.read()
        params = json.loads(raw) if raw.strip() else {}
    except Exception:
        params = {}

    title = params.get("title", "J.A.R.V.I.S. Executive Intelligence Dossier")
    subtitle = params.get("subtitle", "Strategic Research & Execution Synthesis")
    sections = params.get("sections", [
        {
            "heading": "1. Executive Summary",
            "content": "This report synthesizes critical strategic objectives with real-time quantitative validation. All parameters are verified against active data streams.",
            "table_data": [
                {"Metric": "Asset Turnover", "Current": "2.4x", "Benchmark": "1.8x", "Status": "Optimal"},
                {"Metric": "Operating Margin", "Current": "28.5%", "Benchmark": "22.0%", "Status": "Outperform"}
            ]
        },
        {
            "heading": "2. Risk Mitigation & Execution Protocol",
            "content": "Defensive protocols require automated stop-loss thresholds and multi-signature approvals on privileged transactions.",
            "table_data": None
        }
    ])
    author = params.get("author", "J.A.R.V.I.S. Core")

    # Target output path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    reports_dir = base_dir / "frontend" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = int(time.time())
    safe_name = "".join(c for c in title if c.isalnum() or c in ("-", "_")).lower()[:30]
    filename = f"report_{safe_name}_{timestamp_str}.pdf"
    pdf_out = reports_dir / filename
    html_temp = reports_dir / f"temp_{safe_name}_{timestamp_str}.html"

    html_content = build_compact_html(title, subtitle, sections, author)
    html_temp.write_text(html_content, encoding="utf-8")

    browser_exe = find_browser()
    if not browser_exe:
        print(json.dumps({"status": "ERROR", "error": "No compatible browser executable (Edge/Chrome) found for PDF generation."}))
        sys.exit(1)

    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={str(pdf_out)}",
        str(html_temp)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    try:
        if html_temp.exists():
            html_temp.unlink()
    except Exception:
        pass

    if res.returncode != 0 or not pdf_out.exists():
        print(json.dumps({"status": "ERROR", "error": f"Browser compilation failed: {res.stderr}"}))
        sys.exit(1)

    size_kb = round(pdf_out.stat().st_size / 1024, 1)

    output = {
        "status": "SUCCESS",
        "pdf_filename": filename,
        "pdf_path": str(pdf_out),
        "pdf_url": f"/reports/{filename}",
        "size_kb": size_kb,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    main()
