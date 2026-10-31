"""
Playwright-powered Multi-Tab Browser Engine for JARVIS-APEX AI Browser Operator.
Uses persistent profile in data/browser_profile with Microsoft Edge or Chromium.
"""

import os
import json
import time
import uuid
import base64
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

from ..config import settings
from .browser_security import BrowserSecurityGuard
from ..activity import ActivityLogger
from ..websocket_manager import ws_manager

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
PROFILE_DIR = settings.DATA_DIR / "browser_profile"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

class BrowserEngine:
    """
    Manages Playwright browser lifecycle, persistent multi-tab state,
    and native desktop browser automation.
    """
    _playwright: Optional[Playwright] = None
    _context: Optional[BrowserContext] = None
    _pages: Dict[str, Page] = {}
    _active_tab_id: Optional[str] = None
    _lock = asyncio.Lock()
    _emergency_stop: bool = False
    _loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    async def get_context(cls) -> BrowserContext:
        """Initializes or returns the active Playwright persistent browser context."""
        current_loop = asyncio.get_running_loop()
        async with cls._lock:
            # Check if active context belongs to current running loop and has valid pages
            if cls._context and cls._loop == current_loop:
                try:
                    if cls._context.pages and not cls._context.pages[0].is_closed():
                        return cls._context
                except Exception:
                    pass

            # Close previous resources if loop changed
            if cls._context:
                try:
                    await cls._context.close()
                except Exception:
                    pass
                cls._context = None
            if cls._playwright:
                try:
                    await cls._playwright.stop()
                except Exception:
                    pass
                cls._playwright = None

            cls._pages.clear()
            cls._loop = current_loop
            cls._playwright = await async_playwright().start()

            # Launch persistent context with MS Edge or fallback to Chromium
            try:
                cls._context = await cls._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    channel="msedge",
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception as e:
                print(f"[BrowserEngine Warning]: Edge launch failed ({e}), falling back to bundled Chromium.")
                cls._context = await cls._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE_DIR),
                    headless=True
                )

            # Initialize initial page if empty
            if not cls._context.pages:
                page = await cls._context.new_page()
                await page.goto("about:blank")
            else:
                page = cls._context.pages[0]

            tab_id = f"tab_{uuid.uuid4().hex[:8]}"
            cls._pages[tab_id] = page
            cls._active_tab_id = tab_id

            return cls._context
            cls._active_tab_id = tab_id

            return cls._context

    @classmethod
    async def new_tab(cls, url: Optional[str] = None) -> Dict[str, Any]:
        """Opens a new browser tab with optional initial URL."""
        ctx = await cls.get_context()
        target_url = url or "about:blank"

        # Validate URL
        is_safe, msg = BrowserSecurityGuard.validate_navigation(target_url)
        if not is_safe:
            return {"status": "ERROR", "error": msg}

        page = await ctx.new_page()
        tab_id = f"tab_{uuid.uuid4().hex[:8]}"
        cls._pages[tab_id] = page
        cls._active_tab_id = tab_id

        if target_url != "about:blank":
            try:
                await page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
                await cls._record_history(tab_id, await page.title(), page.url)
            except Exception as e:
                return {"status": "ERROR", "tab_id": tab_id, "error": str(e)}

        title = await page.title() or "New Tab"
        ActivityLogger.log(
            component="browser",
            action="new_tab",
            target_resource=target_url,
            approval_status="AUTO_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Opened tab {tab_id} ({title})"
        )

        return {
            "status": "SUCCESS",
            "tab_id": tab_id,
            "title": title,
            "url": page.url,
            "is_active": True
        }

    @classmethod
    async def list_tabs(cls) -> List[Dict[str, Any]]:
        """Lists all open tabs and their current navigation states."""
        await cls.get_context()
        tabs = []
        closed_tab_ids = []

        for tid, page in list(cls._pages.items()):
            if page.is_closed():
                closed_tab_ids.append(tid)
                continue

            try:
                title = await page.title()
                url = page.url
                tabs.append({
                    "tab_id": tid,
                    "title": title or "Blank Tab",
                    "url": url,
                    "is_active": (tid == cls._active_tab_id)
                })
            except Exception:
                closed_tab_ids.append(tid)

        for tid in closed_tab_ids:
            cls._pages.pop(tid, None)

        return tabs

    @classmethod
    async def switch_tab(cls, tab_id: str) -> Dict[str, Any]:
        """Switches active tab context."""
        if tab_id not in cls._pages or cls._pages[tab_id].is_closed():
            return {"status": "ERROR", "error": f"Tab '{tab_id}' does not exist."}

        cls._active_tab_id = tab_id
        page = cls._pages[tab_id]
        await page.bring_to_front()

        return {
            "status": "SUCCESS",
            "tab_id": tab_id,
            "title": await page.title(),
            "url": page.url
        }

    @classmethod
    async def close_tab(cls, tab_id: str) -> Dict[str, Any]:
        """Closes a specific tab and updates active tab."""
        if tab_id not in cls._pages:
            return {"status": "ERROR", "error": "Tab not found."}

        page = cls._pages.pop(tab_id)
        try:
            if not page.is_closed():
                await page.close()
        except Exception:
            pass

        if cls._active_tab_id == tab_id:
            cls._active_tab_id = next(iter(cls._pages.keys())) if cls._pages else None

        return {"status": "SUCCESS", "message": f"Tab {tab_id} closed."}

    @classmethod
    async def navigate(cls, tab_id: Optional[str], url: str) -> Dict[str, Any]:
        """Navigates target tab to URL with SSRF checks and history logging."""
        await cls.get_context()
        tid = tab_id or cls._active_tab_id
        if not tid or tid not in cls._pages:
            res = await cls.new_tab(url)
            return res

        # 1. SSRF and Protocol Guard
        is_safe, msg = BrowserSecurityGuard.validate_navigation(url)
        if not is_safe:
            ActivityLogger.log(
                component="browser",
                action="navigate_blocked",
                target_resource=url,
                approval_status="DENIED",
                execution_status="FAILED",
                error_info=msg
            )
            return {"status": "ERROR", "error": msg}

        page = cls._pages[tid]
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = await page.title()
            final_url = page.url

            await cls._record_history(tid, title, final_url)
            ActivityLogger.log(
                component="browser",
                action="navigate",
                target_resource=final_url,
                approval_status="AUTO_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Navigated to: {title}"
            )

            return {
                "status": "SUCCESS",
                "tab_id": tid,
                "title": title,
                "url": final_url
            }
        except Exception as e:
            return {"status": "ERROR", "tab_id": tid, "error": str(e)}

    @classmethod
    async def perform_action(cls, tab_id: Optional[str], action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Controls browser actions: back, forward, reload, search, click, type."""
        tid = tab_id or cls._active_tab_id
        if not tid or tid not in cls._pages:
            return {"status": "ERROR", "error": "Active tab not found."}

        page = cls._pages[tid]
        params = params or {}

        try:
            if action == "back":
                await page.go_back()
            elif action == "forward":
                await page.go_forward()
            elif action == "reload":
                await page.reload()
            elif action == "home":
                await page.goto("about:blank")
            elif action == "search":
                term = params.get("query", "")
                count = await page.evaluate(f"window.find ? (window.find('{term}') ? 1 : 0) : 0")
                return {"status": "SUCCESS", "matches_found": count}
            elif action == "click":
                selector = params.get("selector")
                if selector:
                    await page.click(selector, timeout=5000)
            elif action == "type":
                selector = params.get("selector")
                text = params.get("text", "")
                if selector:
                    await page.fill(selector, text, timeout=5000)
            else:
                return {"status": "ERROR", "error": f"Unsupported browser action: {action}"}

            return {
                "status": "SUCCESS",
                "tab_id": tid,
                "action": action,
                "title": await page.title(),
                "url": page.url
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    @classmethod
    async def get_snapshot(cls, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Extracts title, URL, clean text content, and base64 screenshot."""
        await cls.get_context()
        tid = tab_id or cls._active_tab_id
        if not tid or tid not in cls._pages:
            return {"status": "ERROR", "error": "No active tab."}

        page = cls._pages[tid]
        title = await page.title()
        url = page.url

        # Extract visible text safely
        try:
            raw_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            clean_text = BrowserSecurityGuard.sanitize_web_content(raw_text or "")
        except Exception:
            clean_text = ""

        # Capture screenshot
        try:
            shot_bytes = await page.screenshot(type="jpeg", quality=60)
            shot_b64 = base64.b64encode(shot_bytes).decode("utf-8")
        except Exception:
            shot_b64 = ""

        return {
            "status": "SUCCESS",
            "tab_id": tid,
            "title": title or "Blank Page",
            "url": url,
            "text": clean_text[:15000], # Bounded 15k characters
            "screenshot_b64": shot_b64
        }

    @classmethod
    def stop_automation(cls) -> bool:
        """Emergency Stop control: Immediately signals browser routines to abort."""
        cls._emergency_stop = True
        ActivityLogger.log(
            component="browser",
            action="emergency_stop",
            target_resource="browser_engine",
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary="Emergency stop automation signal triggered."
        )
        return True

    @classmethod
    async def _record_history(cls, tab_id: str, title: str, url: str):
        """Appends visited URL to browser_history in SQLite."""
        if url in ("about:blank", "about:home"):
            return
        now = time.time()
        hid = f"hist_{uuid.uuid4().hex[:10]}"
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO browser_history (id, tab_id, title, url, visited_at, transition_type)
                    VALUES (?, ?, ?, ?, ?, 'navigate');
                """, (hid, tab_id, title or url, url, now))
                conn.commit()
        except Exception:
            pass

    # -------------------------------------------------------------
    # Bookmarks, History & Downloads Management
    # -------------------------------------------------------------
    @classmethod
    def add_bookmark(cls, title: str, url: str, folder: str = "default", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        bid = f"bm_{uuid.uuid4().hex[:10]}"
        now = time.time()
        tags_str = json.dumps(tags or [])
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO browser_bookmarks (id, title, url, folder, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (bid, title, url, folder, tags_str, now))
            conn.commit()
        return {"id": bid, "title": title, "url": url, "folder": folder, "created_at": now}

    @classmethod
    def list_bookmarks(cls) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM browser_bookmarks ORDER BY created_at DESC;")
            return [dict(r) for r in cursor.fetchall()]

    @classmethod
    def delete_bookmark(cls, bookmark_id: str) -> bool:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM browser_bookmarks WHERE id = ?;", (bookmark_id,))
            affected = cursor.rowcount > 0
            conn.commit()
        return affected

    @classmethod
    def get_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM browser_history ORDER BY visited_at DESC LIMIT ?;", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    @classmethod
    def clear_history(cls) -> int:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM browser_history;")
            count = cursor.rowcount
            conn.commit()
        return count
