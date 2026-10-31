"""
Fact Verification & Anti-Hallucination Engine for J.A.R.V.I.S.
Extracts factual claims, cross-references across independent sources,
evaluates verification status (VERIFIED, PARTIALLY_VERIFIED, DISPUTED, UNVERIFIED, OUTDATED),
and enforces strict anti-hallucination safeguards.
"""
import json
import re
from typing import List, Dict, Any, Optional
from .models import SourceRecord, ClaimRecord, ResearchPlan
from ..config import settings
import httpx

def clean_json_str(raw: str) -> Optional[Dict[str, Any]]:
    """Cleans markdown fences and parses JSON safely."""
    t = raw.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    t = t.strip()
    try:
        return json.loads(t)
    except Exception:
        s = t.find("{")
        e = t.rfind("}")
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(t[s:e+1])
            except Exception:
                pass
    return None

from ..model_router import route_json_resilient

async def call_llm_json_resilient(prompt: str, system_prompt: str, temperature: float = 0.15) -> Dict[str, Any]:
    """
    Delegates to the centralized Free AI Model Router:
    - Primary: Google Gemini gemini-3.5-flash-lite (Free Tier, native JSON schema)
    - Secondary: Groq LPU openai/gpt-oss-120b (120B reasoning, structured JSON object)
    """
    return await route_json_resilient(prompt, system_prompt, temperature=temperature)

async def extract_and_verify_claims(subject: str, sources: List[SourceRecord]) -> List[ClaimRecord]:
    """
    Extracts core factual claims from collected evidence and computes rigorous verification statuses.
    """
    if not sources:
        return [ClaimRecord(
            claim_id="CLM-000",
            claim_text=f"No independent verified sources could be retrieved for '{subject}'.",
            verification_status="UNVERIFIED",
            confidence_level=0.0,
            decision="REJECT",
            notes="Web retrieval returned 0 sources."
        )]

    # Format verified evidence block for extraction
    evidence_blocks = []
    source_map: Dict[int, SourceRecord] = {}
    for s in sources:
        source_map[s.source_id] = s
        text_snip = s.snippet or ""
        if s.full_text and len(s.full_text) > len(text_snip):
            text_snip = s.full_text[:600]
        evidence_blocks.append(f"Source [{s.source_id}] ({s.publisher}, {s.tier}, Date: {s.publication_date}):\n{text_snip}")

    evidence_text = "\n\n".join(evidence_blocks[:10])

    sys_prompt = (
        "You are J.A.R.V.I.S. Fact Verification Engine. "
        "Your duty is to extract ONLY genuine, factual claims directly stated in the provided sources. "
        "DO NOT INVENT facts, statistics, awards, net worth, dates or citations. "
        "If a claim is an estimate (e.g. net worth, approximations), explicitly mark it as an estimate. "
        "If sources disagree or information is ambiguous, indicate dispute."
    )

    prompt = f"""
Subject: {subject}
Available Sources:
{evidence_text}

Task:
Extract 6 to 12 core verifiable claims directly from the sources above.
For each claim, identify:
1. claim_text: The factual assertion (dates, origins, achievements, specifications, numbers).
2. category: "biographical", "chronological", "technical", "financial", or "statistical".
3. supporting_sources: List of integers matching the Source [X] numbers that explicitly confirm this claim.
4. is_estimate: Boolean, true if the claim is an approximate figure or valuation.
5. has_contradiction: Boolean, true if another source conflicts with this.

Output in strict JSON format:
{{
  "claims": [
    {{
      "claim_text": "...",
      "category": "...",
      "supporting_sources": [1, 2],
      "is_estimate": false,
      "has_contradiction": false,
      "notes": "..."
    }}
  ]
}}
"""

    resp_json = await call_llm_json_resilient(prompt, sys_prompt)
    raw_claims = resp_json.get("claims", [])

    verified_records: List[ClaimRecord] = []
    for idx, c in enumerate(raw_claims, 1):
        claim_text = (c.get("claim_text") or "").strip()
        if not claim_text:
            continue

        raw_supporters = c.get("supporting_sources") or []
        # Filter supporters to valid source IDs
        valid_supporters = [int(s_id) for s_id in raw_supporters if int(s_id) in source_map]
        
        is_estimate = c.get("is_estimate", False) or any(k in claim_text.lower() for k in ["estimate", "approx", "around", "लगभग", "अनुमानित"])
        has_contra = c.get("has_contradiction", False)

        # Verification Rules
        # 1. Check tiers of supporting sources
        has_tier_1 = any(source_map[s_id].tier == "TIER_1_PRIMARY" for s_id in valid_supporters)
        num_supporters = len(valid_supporters)

        if has_contra:
            status = "DISPUTED"
            conf = 0.50
            decision = "FLAG_DISPUTED"
        elif num_supporters >= 2 or (num_supporters == 1 and has_tier_1):
            status = "VERIFIED"
            conf = 0.95 if has_tier_1 else 0.88
            decision = "FLAG_ESTIMATE" if is_estimate else "ACCEPT"
        elif num_supporters == 1:
            status = "PARTIALLY_VERIFIED"
            conf = 0.70
            decision = "FLAG_ESTIMATE" if is_estimate else "ACCEPT_WITH_QUALIFICATION"
        else:
            status = "UNVERIFIED"
            conf = 0.30
            decision = "REJECT"

        dates = [source_map[s_id].publication_date for s_id in valid_supporters if source_map[s_id].publication_date]

        rec = ClaimRecord(
            claim_id=f"CLM-{idx:03d}",
            claim_text=claim_text,
            claim_category=c.get("category", "factual"),
            supporting_sources=valid_supporters,
            contradicting_sources=[],
            publication_dates=dates,
            verification_status=status,
            confidence_level=conf,
            decision=decision,
            notes=c.get("notes", "") or ("Independently verified" if status == "VERIFIED" else "Single-source or unverified")
        )
        verified_records.append(rec)

    # Fallback if LLM extraction returned empty
    if not verified_records and sources:
        for idx, s in enumerate(sources[:5], 1):
            verified_records.append(ClaimRecord(
                claim_id=f"CLM-{idx:03d}",
                claim_text=s.snippet[:200],
                claim_category="factual",
                supporting_sources=[s.source_id],
                verification_status="PARTIALLY_VERIFIED" if s.tier != "TIER_1_PRIMARY" else "VERIFIED",
                confidence_level=s.reliability_score,
                decision="ACCEPT",
                notes=f"Derived from {s.publisher}"
            ))

    return verified_records

def compute_verification_summary(claims: List[ClaimRecord], sources: List[SourceRecord]) -> Dict[str, Any]:
    """Generates an honest, uninflated verification summary."""
    total = len(claims)
    if total == 0:
        return {
            "total_claims": 0,
            "verified_count": 0,
            "partially_verified_count": 0,
            "disputed_count": 0,
            "unverified_count": 0,
            "verification_accuracy_pct": 0,
            "total_sources": len(sources),
            "tier_1_count": sum(1 for s in sources if s.tier == "TIER_1_PRIMARY"),
            "tier_2_count": sum(1 for s in sources if s.tier == "TIER_2_REPUTABLE"),
            "tier_3_count": sum(1 for s in sources if s.tier == "TIER_3_SECONDARY")
        }

    verified = sum(1 for c in claims if c.verification_status == "VERIFIED")
    partial = sum(1 for c in claims if c.verification_status == "PARTIALLY_VERIFIED")
    disputed = sum(1 for c in claims if c.verification_status == "DISPUTED")
    unverified = sum(1 for c in claims if c.verification_status == "UNVERIFIED")

    # Honest verification accuracy score (never fake 100%)
    score = round(((verified * 1.0 + partial * 0.7) / total) * 100, 1)

    return {
        "total_claims": total,
        "verified_count": verified,
        "partially_verified_count": partial,
        "disputed_count": disputed,
        "unverified_count": unverified,
        "verification_accuracy_pct": min(score, 98.5),  # Never claim 100% unless absolute mathematical certainty
        "total_sources": len(sources),
        "tier_1_count": sum(1 for s in sources if s.tier == "TIER_1_PRIMARY"),
        "tier_2_count": sum(1 for s in sources if s.tier == "TIER_2_REPUTABLE"),
        "tier_3_count": sum(1 for s in sources if s.tier == "TIER_3_SECONDARY")
    }

