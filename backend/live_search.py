import httpx
import time
import re
import asyncio
import urllib.parse
import email.utils
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
WIKI_USER_AGENT = "JarvisApexBot/2.0 (workstation-assistant; admin@jarvis.local)"

# In-memory search & breaking news cache (90s TTL to always serve freshest breaking news)
_SEARCH_CACHE: Dict[str, Any] = {}
_NEWS_CACHE: Dict[str, Any] = {}

def clean_html_tags(text: str) -> str:
    """Removes HTML markup and cleans up whitespace."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', clean).strip()

def parse_pubdate(pub_date_str: str) -> tuple[float, str]:
    """
    Parses RFC 2822 date string into epoch timestamp and localized relative Hindi time.
    e.g. '12 मिनट पहले', '1 घंटा पहले', 'आज सुबह'
    """
    if not pub_date_str:
        return time.time(), "ताज़ा"
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        epoch = dt.timestamp()
        now_epoch = datetime.now(timezone.utc).timestamp()
        diff_sec = max(0, now_epoch - epoch)
        diff_min = int(diff_sec / 60)

        if diff_min < 2:
            rel = "अभी-अभी"
        elif diff_min < 60:
            rel = f"{diff_min} मिनट पहले"
        elif diff_min < 1440:
            rel = f"{int(diff_min / 60)} घंटे पहले"
        else:
            rel = f"{int(diff_min / 1440)} दिन पहले"
        return epoch, rel
    except Exception:
        return time.time(), "ताज़ा"

async def _fetch_rss_feed_items(url: str, lang: str = "en", max_results: int = 8) -> List[Dict[str, Any]]:
    """
    Fetches and parses any Google News RSS feed, extracting timestamps and sorting by newest first.
    """
    headers = {"User-Agent": USER_AGENT}
    results = []

    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                items = root.findall(".//item")
                for it in items[:max_results]:
                    title = (it.find("title").text or "").strip()
                    link = (it.find("link").text or "").strip()
                    source_el = it.find("source")
                    source = (source_el.text or "News Source").strip() if source_el is not None else "Google News"
                    pub_date = (it.find("pubDate").text or "").strip()
                    
                    clean_title = re.sub(r' - [^-]+$', '', title).strip()
                    epoch, rel_time = parse_pubdate(pub_date)

                    results.append({
                        "title": clean_title,
                        "snippet": f"[{source}] ({rel_time}) {clean_title}",
                        "source": source,
                        "url": link,
                        "type": "news",
                        "lang": lang,
                        "published_epoch": epoch,
                        "relative_time": rel_time,
                        "pub_date": pub_date
                    })
    except Exception as e:
        print(f"[LiveSearch] RSS error for {url}: {e}")

    return results

async def _fetch_google_news_rss(query: str, lang: str = "en", max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Searches Google News RSS for a specific query in English or Hindi.
    """
    clean_q = urllib.parse.quote_plus(query.strip())
    if lang == "hi":
        url = f"https://news.google.com/rss/search?q={clean_q}&hl=hi&gl=IN&ceid=IN:hi"
    else:
        url = f"https://news.google.com/rss/search?q={clean_q}&hl=en-IN&gl=IN&ceid=IN:en"
        
    return await _fetch_rss_feed_items(url, lang=lang, max_results=max_results)

async def _fetch_wikipedia_knowledge(query: str, lang: str = "en") -> Optional[Dict[str, Any]]:
    """
    Fetches authoritative factual extracts and verified entity bios via Wikipedia API & REST API (<250ms).
    """
    domain = f"{lang}.wikipedia.org"
    search_url = f"https://{domain}/w/api.php"
    headers = {"User-Agent": WIKI_USER_AGENT}
    
    clean_q = query.strip()
    entity_q = re.sub(r'^(who is|what is|search|google|kya hai|kaun hai|batao|सर्च|खोजो|कौन है|क्या है)\s+', '', clean_q, flags=re.I).strip()
    if not entity_q:
        entity_q = clean_q

    params = {
        "action": "query",
        "list": "search",
        "srsearch": entity_q,
        "format": "json",
        "utf8": "1",
        "srlimit": 1
    }

    try:
        async with httpx.AsyncClient(timeout=2.8) as client:
            s_resp = await client.get(search_url, params=params, headers=headers)
            if s_resp.status_code == 200:
                s_data = s_resp.json()
                search_hits = s_data.get("query", {}).get("search", [])
                if not search_hits:
                    return None
                
                top_hit = search_hits[0]
                matched_title = top_hit.get("title", "")
                if not matched_title:
                    return None
                
                encoded_title = urllib.parse.quote(matched_title.replace(" ", "_"))
                summary_url = f"https://{domain}/api/rest_v1/page/summary/{encoded_title}"
                sum_resp = await client.get(summary_url, headers=headers)
                if sum_resp.status_code == 200:
                    sum_data = sum_resp.json()
                    extract = sum_data.get("extract", "").strip()
                    page_url = sum_data.get("content_urls", {}).get("desktop", {}).get("page", f"https://{domain}/wiki/{encoded_title}")
                    
                    if extract:
                        return {
                            "title": matched_title,
                            "snippet": extract,
                            "source": "Wikipedia",
                            "url": page_url,
                            "type": "encyclopedia",
                            "lang": lang,
                            "published_epoch": time.time(),
                            "relative_time": "तथ्य"
                        }
    except Exception as e:
        print(f"[LiveSearch] Wikipedia ({lang}) error: {e}")

    return None

async def fetch_breaking_news(category: str = "top", max_results: int = 12) -> Dict[str, Any]:
    """
    Retrieves the absolute freshest, newest breaking news from top national & international wire feeds.
    Strictly sorted descending by timestamp (newest first).
    Categories: 'top', 'markets', 'tech', 'sports'
    """
    cat = category.lower().strip()
    cache_key = f"news_{cat}"
    now = time.time()

    if cache_key in _NEWS_CACHE:
        entry = _NEWS_CACHE[cache_key]
        if (now - entry.get("cached_at", 0)) < 90:
            return entry["data"]

    t0 = time.time()
    tasks = []

    if cat in ["markets", "market", "business", "finance", "शेयर", "बाजार"]:
        cat_name = "मार्केट & बिजनेस"
        urls = [
            ("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en", "en"),
            ("https://news.google.com/rss/search?q=शेयर+बाजार+मार्केट+Nifty+Sensex&hl=hi&gl=IN&ceid=IN:hi", "hi")
        ]
    elif cat in ["tech", "technology", "ai", "तकनीक", "साइंस"]:
        cat_name = "टेक्नोलॉजी & AI"
        urls = [
            ("https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en", "en"),
            ("https://news.google.com/rss/search?q=तकनीक+AI+आर्टिफिशियल+इंटेलिजेंस&hl=hi&gl=IN&ceid=IN:hi", "hi")
        ]
    elif cat in ["sports", "cricket", "खेल", "क्रिकेट"]:
        cat_name = "खेल & क्रिकेट"
        urls = [
            ("https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en", "en"),
            ("https://news.google.com/rss/search?q=क्रिकेट+मैच+भारत+खेल&hl=hi&gl=IN&ceid=IN:hi", "hi")
        ]
    else:
        cat_name = "शीर्ष ब्रेकिंग न्यूज़"
        urls = [
            ("https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi", "hi"),
            ("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en", "en")
        ]

    for u, lang in urls:
        tasks.append(asyncio.create_task(_fetch_rss_feed_items(u, lang=lang, max_results=8)))

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    all_news = []
    for sublist in gathered:
        if isinstance(sublist, list):
            all_news.extend(sublist)

    # Deduplicate by title
    seen = set()
    unique_news = []
    for item in all_news:
        t_key = item["title"].lower().strip()
        if t_key not in seen:
            seen.add(t_key)
            unique_news.append(item)

    # CRITICAL: Sort by publication timestamp descending (freshest, newest first!)
    unique_news.sort(key=lambda x: x.get("published_epoch", 0), reverse=True)
    final_news = unique_news[:max_results]
    elapsed = time.time() - t0

    # Build grounding text for LLM
    snippets = []
    for i, it in enumerate(final_news[:6], 1):
        snippets.append(f"[{i}] ({it['relative_time']}) {it['title']} - {it['source']}")

    res_data = {
        "category": cat_name,
        "category_key": cat,
        "results": final_news,
        "grounding_text": "\n".join(snippets),
        "count": len(final_news),
        "fetch_time_ms": round(elapsed * 1000, 1),
        "timestamp": now
    }

    _NEWS_CACHE[cache_key] = {"data": res_data, "cached_at": now}
    return res_data

async def search_internet_live(query: str, max_results: int = 6) -> Dict[str, Any]:
    """
    Performs ultra-fast parallel background internet search across verified sources.
    News items are parsed for publication date and sorted freshest-first.
    """
    clean_q = query.strip()
    cache_key = clean_q.lower()
    now = time.time()

    if cache_key in _SEARCH_CACHE:
        entry = _SEARCH_CACHE[cache_key]
        if (now - entry.get("cached_at", 0)) < 120:
            return entry["data"]

    t0 = time.time()

    tasks = [
        asyncio.create_task(_fetch_google_news_rss(clean_q, lang="hi", max_results=4)),
        asyncio.create_task(_fetch_google_news_rss(clean_q, lang="en", max_results=4)),
        asyncio.create_task(_fetch_wikipedia_knowledge(clean_q, lang="hi")),
        asyncio.create_task(_fetch_wikipedia_knowledge(clean_q, lang="en"))
    ]

    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: List[Dict[str, Any]] = []
    
    # Process Google News (English & Hindi)
    news_items = []
    if isinstance(gathered[0], list):
        news_items.extend(gathered[0])
    if isinstance(gathered[1], list):
        news_items.extend(gathered[1])
        
    # Sort news items newest first!
    news_items.sort(key=lambda x: x.get("published_epoch", 0), reverse=True)
    all_results.extend(news_items)

    # Process Wikipedia facts
    if isinstance(gathered[2], dict) and gathered[2]:
        all_results.insert(0, gathered[2])
    if isinstance(gathered[3], dict) and gathered[3]:
        all_results.insert(0, gathered[3])

    # Deduplicate results by title
    seen_titles = set()
    unique_results = []
    for r in all_results:
        t_key = r["title"].lower().strip()
        if t_key not in seen_titles:
            seen_titles.add(t_key)
            unique_results.append(r)

    final_results = unique_results[:max_results]
    elapsed = time.time() - t0

    # Build coherent grounding context for LLM with timestamps
    grounding_snippets = []
    for i, r in enumerate(final_results, 1):
        rel = f" ({r.get('relative_time')})" if r.get('relative_time') else ""
        grounding_snippets.append(f"[{i}]{rel} {r['title']} ({r['source']}): {r['snippet']}")

    grounding_text = "\n".join(grounding_snippets)

    res_data = {
        "query": clean_q,
        "results": final_results,
        "grounding_text": grounding_text,
        "sources_count": len(final_results),
        "search_time_ms": round(elapsed * 1000, 1),
        "timestamp": now
    }

    _SEARCH_CACHE[cache_key] = {"data": res_data, "cached_at": now}
    return res_data
