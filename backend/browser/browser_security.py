"""
Browser Security Guardrails for JARVIS-APEX AI Browser Operator.
Enforces SSRF prevention, prompt injection containment, and sensitive action gating.
"""

import re
from typing import Tuple, Dict, Any, Optional
from urllib.parse import urlparse

from ..url_threat_analyzer import validate_url_for_ssrf
from ..permissions import CentralPermissionManager, PermissionLevel

# Sensitive keyword patterns for interactive approval
SENSITIVE_DOM_PATTERNS = [
    re.compile(r'\b(pay|payment|checkout|buy now|transfer|credit card|cvv|password|pin|authenticate)\b', re.IGNORECASE),
    re.compile(r'\b(delete account|erase data|wire funds)\b', re.IGNORECASE)
]

# Prompt injection markers to sanitize from untrusted web pages
INJECTION_PATTERNS = [
    re.compile(r'(ignore|disregard|forget)\s+(all\s+)?(previous|prior)\s+instructions', re.IGNORECASE),
    re.compile(r'system\s+prompt\s*:', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+in\s+developer\s+mode', re.IGNORECASE),
    re.compile(r'output\s+all\s+(api\s+keys|passwords|tokens)', re.IGNORECASE)
]

class BrowserSecurityGuard:
    """Enforces strict safety boundaries on all browser automation tasks."""

    @classmethod
    def validate_navigation(cls, url: str) -> Tuple[bool, str]:
        """
        Validates target URL against SSRF vulnerabilities and protocol restrictions.
        Allows about:blank and http/https schemes.
        """
        clean = url.strip()
        if clean.lower() in ("about:blank", "about:home"):
            return True, "Safe internal page"

        parsed = urlparse(clean)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Disallowed URI scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted."

        # SSRF validation
        is_safe, resolved_ip, msg = validate_url_for_ssrf(clean)
        if not is_safe:
            return False, f"SSRF Security Violation: {msg}"

        return True, "Valid and safe"

    @classmethod
    def sanitize_web_content(cls, raw_text: str) -> str:
        """
        Strips dangerous prompt injection attempts and exploits from scraped web DOM.
        """
        sanitized = raw_text
        for pat in INJECTION_PATTERNS:
            sanitized = pat.sub("[SANITIZED_INJECTION_ATTEMPT]", sanitized)
        return sanitized

    @classmethod
    def check_sensitive_action(
        cls,
        url: str,
        action_type: str,
        element_text: str = "",
        element_tag: str = ""
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Evaluates whether a DOM action (click, form submission, input) involves
        sensitive financial, credential, or destructive operations.
        """
        is_sensitive = False
        sample = f"{action_type} {element_tag} {element_text}".lower()

        for pat in SENSITIVE_DOM_PATTERNS:
            if pat.search(sample):
                is_sensitive = True
                break

        if not is_sensitive:
            return True, "Standard non-sensitive DOM action auto-approved.", None

        # Requires two-step confirmation
        return CentralPermissionManager.check_permission(
            component="browser",
            resource=url,
            level=PermissionLevel.SENSITIVE,
            description=f"Sensitive browser action ({action_type}) on: '{element_text[:40]}'",
            context={"url": url, "action": action_type, "element": element_text}
        )
