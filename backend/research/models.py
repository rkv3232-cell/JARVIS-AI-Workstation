"""
Data models and typed definitions for J.A.R.V.I.S. Deep Research & Fact Verification Pipeline.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time

class SourceRecord(BaseModel):
    source_id: int
    title: str
    publisher: str = "Web"
    author: Optional[str] = None
    url: str
    publication_date: Optional[str] = None
    source_type: str = "web"  # "official", "academic", "news", "encyclopedia", "web"
    tier: str = "TIER_3_SECONDARY"  # "TIER_1_PRIMARY", "TIER_2_REPUTABLE", "TIER_3_SECONDARY"
    reliability_score: float = 0.7  # 0.0 to 1.0
    snippet: str = ""
    full_text: Optional[str] = None

class ClaimRecord(BaseModel):
    claim_id: str
    claim_text: str
    claim_category: str = "factual"  # "biographical", "financial", "technical", "chronological", "statistical"
    supporting_sources: List[int] = Field(default_factory=list)
    contradicting_sources: List[int] = Field(default_factory=list)
    publication_dates: List[str] = Field(default_factory=list)
    verification_status: str = "UNVERIFIED"  # "VERIFIED", "PARTIALLY_VERIFIED", "DISPUTED", "UNVERIFIED", "OUTDATED"
    confidence_level: float = 0.5  # 0.0 to 1.0
    decision: str = "ACCEPT"  # "ACCEPT", "ACCEPT_WITH_QUALIFICATION", "REJECT", "FLAG_ESTIMATE", "FLAG_PREDICTION"
    notes: str = ""

class ResearchPlan(BaseModel):
    topic: str
    clean_subject: str
    category: str
    depth: str  # "QUICK", "STANDARD", "DEEP"
    research_objectives: List[str] = Field(default_factory=list)
    research_questions: List[str] = Field(default_factory=list)
    verification_targets: List[str] = Field(default_factory=list)
    search_queries: List[str] = Field(default_factory=list)

class ReportChapter(BaseModel):
    chapter_num: int
    title: str
    subtitle: str
    meta_badges: List[str] = Field(default_factory=list)
    executive_brief: str = ""
    paragraphs: List[str] = Field(default_factory=list)
    table: Optional[Dict[str, Any]] = None  # {"headers": [...], "rows": [[...], ...]}
    callout_box: Optional[Dict[str, Any]] = None  # {"title": "...", "content": "...", "type": "..."}
    key_terms_or_findings: List[str] = Field(default_factory=list)
    citations_used: List[int] = Field(default_factory=list)

class ResearchDossier(BaseModel):
    topic: str
    subject: str
    category: str
    mode: str
    cover_title: str
    subtitle: str
    date_str: str
    executive_summary: str
    key_findings: List[str] = Field(default_factory=list)
    limitations_and_uncertainties: List[str] = Field(default_factory=list)
    chapters: List[ReportChapter] = Field(default_factory=list)
    verified_claims: List[ClaimRecord] = Field(default_factory=list)
    sources: List[SourceRecord] = Field(default_factory=list)
    spoken_answer: str = ""
    pdf_path: str = ""
    pdf_filename: str = ""
    pdf_pages: int = 0
    actual_pages: int = 0
    verification_summary: Dict[str, Any] = Field(default_factory=dict)
    quality_check: Dict[str, Any] = Field(default_factory=dict)

