"""
Multi-Source Research & Source Validation Engine for J.A.R.V.I.S.
Fetches intelligence from Wikipedia API, Google News RSS, DuckDuckGo, and directly scraped articles.
Performs source provenance tracking, tier classification, and reliability scoring.
"""
import asyncio
import re
import time
import email.utils
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, unquote, urlparse
import httpx
import lxml.html

from .models import SourceRecord, ResearchPlan

WIKI_USER_AGENT = "JarvisUniversalResearch/2.0 (DeepResearchBot; contact: jarvis@apex.internal)"
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

TIER_1_DOMAINS = [
    "wikipedia.org", "gov.in", "gov", "nic.in", "who.int", "nasa.gov", "isro.gov.in", 
    "un.org", "worldbank.org", "nature.com", "science.org", "arxiv.org", "nih.gov", "loc.gov"
]

TIER_2_DOMAINS = [
    "reuters.com", "bbc.com", "thehindu.com", "indianexpress.com", "hindustantimes.com",
    "bloomberg.com", "wsj.com", "ft.com", "nytimes.com", "forbes.com", "techcrunch.com",
    "theverge.com", "wired.com", "apnews.com", "aljazeera.com", "ndtv.com", "indiatoday.in"
]

def assess_source_tier(url: str, publisher: str = "") -> tuple[str, float]:
    """Evaluates the credibility tier and reliability score based on domain and publisher."""
    try:
        domain = urlparse(url).netloc.lower()
        # Clean port or subdomains
        if ":" in domain:
            domain = domain.split(":")[0]
    except Exception:
        domain = ""

    pub_low = (publisher or "").lower()

    # Tier 1 checks
    for d in TIER_1_DOMAINS:
        if d in domain or d in pub_low:
            return "TIER_1_PRIMARY", 0.95

    # Tier 2 checks
    for d in TIER_2_DOMAINS:
        if d in domain or d in pub_low:
            return "TIER_2_REPUTABLE", 0.88

    # General web
    if domain.endswith(".edu") or domain.endswith(".org"):
        return "TIER_2_REPUTABLE", 0.82
    elif domain.endswith(".gov"):
        return "TIER_1_PRIMARY", 0.96

    return "TIER_3_SECONDARY", 0.70

def extract_article_text(html: str, max_chars: int = 3000) -> str:
    """Extracts clean readable article text from raw HTML, stripping scripts, styles, nav, ads."""
    if not html:
        return ""
    try:
        doc = lxml.html.fromstring(html)
        for tag in doc.xpath('//script | //style | //nav | //footer | //header | //form | //svg | //noscript | //aside | //iframe'):
            tag.drop_tree()
        paragraphs = doc.xpath('//p | //h2 | //h3 | //li')
        texts = []
        for p in paragraphs:
            t = p.text_content().strip()
            if len(t) > 30 and not any(bad in t.lower() for bad in ["cookie policy", "all rights reserved", "terms of use", "subscribe now"]):
                texts.append(t)
        body = "\n\n".join(texts)
        clean = re.sub(r'[ \t]+', ' ', body).strip()
        return clean[:max_chars]
    except Exception:
        return ""

async def fetch_wikipedia_extract(query: str, lang: str = "en") -> Optional[SourceRecord]:
    """Fetches high-authority encyclopedia extract from Wikipedia MediaWiki API."""
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    headers = {'User-Agent': WIKI_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": 1
            }
            s_resp = await client.get(base_url, params=search_params)
            if s_resp.status_code != 200:
                return None
            search_data = s_resp.json()
            items = search_data.get("query", {}).get("search", [])
            if not items:
                return None
            
            page_id = items[0]["pageid"]
            page_title = items[0]["title"]

            detail_params = {
                "action": "query",
                "prop": "extracts|info",
                "pageids": page_id,
                "explaintext": 1,
                "inprop": "url",
                "format": "json"
            }
            d_resp = await client.get(base_url, params=detail_params)
            if d_resp.status_code != 200:
                return None
            pages = d_resp.json().get("query", {}).get("pages", {})
            page_info = pages.get(str(page_id), {})
            
            full_text = page_info.get("extract", "")
            if not full_text:
                return None
            
            paragraphs = [p.strip() for p in full_text.split("\n\n") if len(p.strip()) > 60]
            summary_snippet = " ".join(paragraphs[:4]) if paragraphs else full_text[:1800]
            canonical_url = page_info.get("fullurl", f"https://{lang}.wikipedia.org/wiki/{quote_plus(page_title)}")

            return SourceRecord(
                source_id=0,  # Will be assigned during collation
                title=f"{page_title} — Wikipedia ({lang.upper()})",
                publisher=f"Wikipedia ({lang.upper()})",
                author="Wikipedia Contributors",
                url=canonical_url,
                publication_date=time.strftime("%Y-%m-%d"),
                source_type="encyclopedia",
                tier="TIER_1_PRIMARY",
                reliability_score=0.94,
                snippet=summary_snippet[:1500],
                full_text=full_text[:6000]
            )
    except Exception as e:
        print(f"[MultiSourceFetcher] Wikipedia ({lang}) notice: {e}")
        return None

async def fetch_google_news_rss(query: str, lang: str = "en-IN", max_results: int = 5) -> List[SourceRecord]:
    """Fetches real-time verified news coverage from Google News RSS feed."""
    encoded_q = quote_plus(query.strip())
    hl = "hi" if "hi" in lang else "en-IN"
    gl = "IN"
    ceid = "IN:hi" if "hi" in lang else "IN:en"
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl={gl}&ceid={ceid}"
    headers = {"User-Agent": BROWSER_USER_AGENT}
    
    results: List[SourceRecord] = []
    try:
        import xml.etree.ElementTree as ET
        async with httpx.AsyncClient(timeout=8.0, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return results
            
            root = ET.fromstring(resp.text)
            channel = root.find("channel")
            if channel is None:
                return results
            
            items = channel.findall("item")
            for item in items[:max_results]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                pub_elem = item.find("pubDate")
                src_elem = item.find("source")

                raw_title = title_elem.text if title_elem is not None else ""
                article_url = link_elem.text if link_elem is not None else ""
                pub_str = pub_elem.text if pub_elem is not None else ""
                publisher = src_elem.text if src_elem is not None else "Google News"

                clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                if not clean_title or not article_url:
                    continue

                tier, score = assess_source_tier(article_url, publisher)
                results.append(SourceRecord(
                    source_id=0,
                    title=clean_title,
                    publisher=publisher,
                    url=article_url,
                    publication_date=pub_str[:25] if pub_str else time.strftime("%Y-%m-%d"),
                    source_type="news",
                    tier=tier,
                    reliability_score=score,
                    snippet=f"Reported by {publisher}: {clean_title}",
                    full_text=clean_title
                ))
    except Exception as e:
        print(f"[MultiSourceFetcher] Google News RSS notice: {e}")
    return results

async def fetch_duckduckgo_web(query: str, max_results: int = 5) -> List[SourceRecord]:
    """Performs search via DuckDuckGo HTML endpoint with fallback to Lite."""
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    results: List[SourceRecord] = []
    
    # Try DDG HTML
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                html = resp.text
                snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
                titles_and_urls = re.findall(r'<h2 class="result__title">.*?<a class="result__url"[^>]*href="([^"]*)".*?>(.*?)</a>', html, re.DOTALL)
                
                count = min(len(snippets), len(titles_and_urls), max_results)
                for i in range(count):
                    raw_url = titles_and_urls[i][0]
                    if "uddg=" in raw_url:
                        m = re.search(r'uddg=([^&]+)', raw_url)
                        actual_url = unquote(m.group(1)) if m else raw_url
                    else:
                        actual_url = raw_url

                    clean_title = re.sub(r'<[^>]+>', '', titles_and_urls[i][1]).strip()
                    clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                    
                    if clean_title and clean_snippet:
                        tier, score = assess_source_tier(actual_url)
                        results.append(SourceRecord(
                            source_id=0,
                            title=clean_title,
                            publisher=urlparse(actual_url).netloc or "Open Web",
                            url=actual_url,
                            publication_date=time.strftime("%Y-%m-%d"),
                            source_type="web",
                            tier=tier,
                            reliability_score=score,
                            snippet=clean_snippet,
                            full_text=clean_snippet
                        ))
    except Exception as e:
        print(f"[MultiSourceFetcher] DDG HTML notice: {e}")

    # Fallback to DDG Lite if HTML gave 0 results
    if not results:
        try:
            lite_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
                resp = await client.get(lite_url)
                if resp.status_code == 200:
                    html = resp.text
                    links = re.findall(r'<a class="result-link" href="([^"]+)">(.*?)</a>', html, re.DOTALL)
                    snippets = re.findall(r'<td class="result-snippet">(.*?)</td>', html, re.DOTALL)
                    count = min(len(links), len(snippets), max_results)
                    for i in range(count):
                        actual_url = links[i][0]
                        clean_title = re.sub(r'<[^>]+>', '', links[i][1]).strip()
                        clean_snip = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                        if clean_title and clean_snip:
                            tier, score = assess_source_tier(actual_url)
                            results.append(SourceRecord(
                                source_id=0,
                                title=clean_title,
                                publisher=urlparse(actual_url).netloc or "Open Web",
                                url=actual_url,
                                publication_date=time.strftime("%Y-%m-%d"),
                                source_type="web",
                                tier=tier,
                                reliability_score=score,
                                snippet=clean_snip,
                                full_text=clean_snip
                            ))
        except Exception as e:
            print(f"[MultiSourceFetcher] DDG Lite notice: {e}")

    return results

async def scrape_source_content(source: SourceRecord) -> SourceRecord:
    """Optionally scrapes the real article body for top sources to enrich fact extraction."""
    # Don't re-scrape if already enriched or from wikipedia
    if source.full_text and len(source.full_text) > 1000:
        return source
    if not source.url or not source.url.startswith("http"):
        return source

    headers = {"User-Agent": BROWSER_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(source.url)
            if resp.status_code == 200:
                body = extract_article_text(resp.text, max_chars=3500)
                if body and len(body) > 200:
                    source.full_text = body
    except Exception:
        pass
    return source

async def execute_multi_source_research(plan: ResearchPlan) -> List[SourceRecord]:
    """
    Executes concurrent multi-source research across Tier 1, Tier 2, and Tier 3 sources.
    Deduplicates, validates provenance, and assigns unique source IDs.
    """
    subject = plan.clean_subject
    tasks = []

    # 1. Tier 1: Wikipedia MediaWiki API (English & Hindi)
    tasks.append(fetch_wikipedia_extract(subject, lang="en"))
    tasks.append(fetch_wikipedia_extract(subject, lang="hi"))

    # 2. Tier 2: Google News RSS (English & Hindi)
    news_q = subject if plan.category in ["PERSON", "COMPANY"] else f"{subject} news report"
    tasks.append(fetch_google_news_rss(news_q, lang="en-IN", max_results=5))
    tasks.append(fetch_google_news_rss(news_q, lang="hi-IN", max_results=4))

    # 3. Tier 3: DuckDuckGo targeted searches
    for sq in plan.search_queries[:3]:
        tasks.append(fetch_duckduckgo_web(sq, max_results=4))

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    raw_sources: List[SourceRecord] = []
    for item in gathered:
        if isinstance(item, SourceRecord):
            raw_sources.append(item)
        elif isinstance(item, list):
            for sub in item:
                if isinstance(sub, SourceRecord):
                    raw_sources.append(sub)

    # Deduplicate sources by URL and normalized title
    seen_urls = set()
    seen_titles = set()
    unique_sources: List[SourceRecord] = []

    for s in raw_sources:
        url_key = s.url.strip().lower()
        title_key = re.sub(r'[^a-zA-Z0-9\u0900-\u097F]', '', s.title.lower())

        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue

        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        unique_sources.append(s)

    # Sort sources: Tier 1 first, then Tier 2, then Tier 3, ordered by reliability_score descending
    def sort_key(s: SourceRecord):
        tier_weight = 3 if s.tier == "TIER_1_PRIMARY" else (2 if s.tier == "TIER_2_REPUTABLE" else 1)
        return (tier_weight, s.reliability_score)

    unique_sources.sort(key=sort_key, reverse=True)

    # Assign sequential 1-based source IDs
    for idx, s in enumerate(unique_sources, 1):
        s.source_id = idx

    # Enrich top 3 non-wiki sources with full article content in parallel
    enrich_tasks = []
    for s in unique_sources[:4]:
        if "wikipedia.org" not in s.url.lower():
            enrich_tasks.append(scrape_source_content(s))
    if enrich_tasks:
        await asyncio.gather(*enrich_tasks, return_exceptions=True)

    return unique_sources

