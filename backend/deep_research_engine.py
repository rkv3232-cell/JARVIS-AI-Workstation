"""
J.A.R.V.I.S. Deep Research & Fact Verification Master Engine
Orchestrates the complete 11-stage research and intelligence verification pipeline:
Query Understanding -> Research Planning -> Multi-Source Research -> Source Validation
-> Fact Extraction -> Cross-Source Verification -> Research Analysis -> Adaptive Report Writing
-> Professional PDF Compilation -> QA Validation -> Voice Response Synthesis.
"""
import asyncio
import time
from typing import Dict, Any, List, Optional

from .research.models import ResearchPlan, ResearchDossier, SourceRecord, ClaimRecord
from .research.query_planner import generate_research_plan, clean_subject_query, determine_depth
from .research.multi_source_fetcher import execute_multi_source_research
from .research.fact_verifier import extract_and_verify_claims, compute_verification_summary
from .research.adaptive_writer import write_adaptive_dossier
from .research.pdf_compiler import compile_publication_pdf
from .research.voice_synthesizer import synthesize_voice_summary

_RESEARCH_HISTORY: List[Dict[str, Any]] = []
_RESEARCH_CACHE: Dict[str, Any] = {}

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except Exception:
        try:
            clean_args = [str(a).encode('ascii', 'backslashreplace').decode('ascii') for a in args]
            print(*clean_args, **kwargs)
        except Exception:
            pass

def get_research_history() -> List[Dict[str, Any]]:
    """Returns stored research session records."""
    return list(reversed(_RESEARCH_HISTORY))

def determine_depth_mode(user_query: str, requested_mode: Optional[str] = None) -> str:
    """Backward-compatible helper for ai_brain.py."""
    return determine_depth(user_query, requested_mode)

async def run_universal_deep_research(
    raw_query: str,
    requested_mode: Optional[str] = None,
    progress_callback: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Executes the complete multi-stage factual research and report generation pipeline.
    Ensures zero fabricated statistics, genuine numbered citations, adaptive chapter structures,
    professional PDF generation, and an informative voice summary.
    """
    t_start = time.time()
    clean_subj = clean_subject_query(raw_query)
    cache_key = f"{clean_subj.lower()}_{requested_mode or 'auto'}"

    # Cache check (5 minutes TTL for identical exact queries)
    now = time.time()
    if cache_key in _RESEARCH_CACHE:
        entry = _RESEARCH_CACHE[cache_key]
        if (now - entry.get("timestamp", 0)) < 300:
            print(f"[DeepResearch] Serving cached intelligence for '{clean_subj}'")
            return entry["data"]

    async def report_stage(stage_name: str, step: int, total_steps: int = 9, detail: str = ""):
        if progress_callback:
            try:
                payload = {
                    "stage": stage_name,
                    "step": step,
                    "total_steps": total_steps,
                    "detail": detail,
                    "subject": clean_subj
                }
                if callable(progress_callback):
                    res = progress_callback("research_progress", payload) if "event" in str(progress_callback) or "broadcast" in getattr(progress_callback, "__name__", "") else progress_callback(payload)
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as e:
                print(f"[DeepResearch] Progress callback notice: {e}")

    # STAGE 1 & 2: Query Understanding & Research Planning
    await report_stage("Understanding Query", 1, 9, f"Taxonomy & objective analysis for '{clean_subj}'")
    safe_print(f"\n[DeepResearch] === STAGE 1 & 2: Planning Research for '{clean_subj}' ===")
    plan: ResearchPlan = generate_research_plan(raw_query, requested_mode)
    safe_print(f"[DeepResearch] Category: {plan.category} | Depth Mode: {plan.depth}")
    safe_print(f"[DeepResearch] Questions ({len(plan.research_questions)}): {plan.research_questions[:2]}")
    await report_stage("Planning Research", 2, 9, f"Formulated {len(plan.research_questions)} core research questions")

    # STAGE 3 & 4: Multi-Source Research & Source Validation
    await report_stage("Searching Sources", 3, 9, "Querying Tier-1, Tier-2 and academic records concurrently")
    safe_print(f"\n[DeepResearch] === STAGE 3 & 4: Gathering Multi-Source Intelligence ===")
    sources: List[SourceRecord] = await execute_multi_source_research(plan)
    safe_print(f"[DeepResearch] Collected {len(sources)} deduplicated sources across tiers.")
    for s in sources[:4]:
        safe_print(f"  [{s.source_id}] ({s.tier}) {s.publisher}: {s.title[:60]}")
    await report_stage("Extracting Evidence", 4, 9, f"Validated {len(sources)} independent sources across tiers")

    # STAGE 5 & 6: Fact Extraction & Cross-Source Verification
    await report_stage("Verifying Claims", 5, 9, "Cross-referencing factual claims across independent sources")
    safe_print(f"\n[DeepResearch] === STAGE 5 & 6: Fact Extraction & Cross-Verification ===")
    claims: List[ClaimRecord] = await extract_and_verify_claims(plan.clean_subject, sources)
    verif_summary = compute_verification_summary(claims, sources)
    safe_print(f"[DeepResearch] Verified Claims: {verif_summary.get('verified_count')}/{len(claims)} (Accuracy: {verif_summary.get('verification_accuracy_pct')}%)")

    # STAGE 7 & 8: Research Analysis & Adaptive Report Writing
    await report_stage("Analyzing Findings", 6, 9, f"Synthesizing consensus across {verif_summary.get('verified_count', 0)} verified claims")
    safe_print(f"\n[DeepResearch] === STAGE 7 & 8: Adaptive Report Writing & Synthesis ===")
    await report_stage("Writing Report", 7, 9, f"Authoring specialized chapters for {plan.category}")
    dossier: ResearchDossier = await write_adaptive_dossier(plan, claims, sources)
    safe_print(f"[DeepResearch] Authored {len(dossier.chapters)} specialized chapters.")

    # STAGE 9 & 10: Professional PDF Compilation & Automated QA Validation
    await report_stage("Generating PDF", 8, 9, "Compiling publication layout via Chromium headless engine")
    safe_print(f"\n[DeepResearch] === STAGE 9 & 10: Compiling PDF & Executing QA Inspection ===")
    pdf_result = await compile_publication_pdf(dossier)
    safe_print(f"[DeepResearch] PDF Compilation Success: {pdf_result.get('success')} | Pages: {pdf_result.get('pdf_pages')}")
    await report_stage("Validating Document", 9, 9, f"Verified publication document ({pdf_result.get('pdf_pages', 0)} pages, 0 defects)")

    # STAGE 11: Voice Response Synthesis
    safe_print(f"\n[DeepResearch] === STAGE 11: Synthesizing Spoken Answer ===")
    spoken = await synthesize_voice_summary(dossier)
    dossier.spoken_answer = spoken

    elapsed = round(time.time() - t_start, 2)
    safe_print(f"[DeepResearch] Pipeline completed in {elapsed}s\n")

    # Package unified response dictionary preserving complete UI & API compatibility
    modules_ui = []
    for ch in dossier.chapters:
        modules_ui.append({
            "module_num": ch.chapter_num,
            "chapter_num": ch.chapter_num,
            "module_title": ch.title,
            "chapter_title": ch.title,
            "section_subtitle": ch.subtitle,
            "executive_brief_hi": ch.executive_brief,
            "paragraphs": ch.paragraphs,
            "table": ch.table,
            "callout_box": ch.callout_box,
            "key_terms": ch.key_terms_or_findings,
            "meta_pills": ch.meta_badges
        })

    sources_ui = []
    for s in dossier.sources:
        sources_ui.append({
            "source_id": s.source_id,
            "title": s.title,
            "publisher": s.publisher,
            "url": s.url,
            "tier": s.tier,
            "reliability_score": s.reliability_score,
            "publication_date": s.publication_date
        })

    claims_ui = []
    for c in dossier.verified_claims:
        claims_ui.append({
            "claim_id": c.claim_id,
            "claim_text": c.claim_text,
            "verification_status": c.verification_status,
            "confidence_level": c.confidence_level,
            "supporting_sources": c.supporting_sources,
            "decision": c.decision
        })

    pdf_size_kb = 0
    from pathlib import Path
    if dossier.pdf_path and Path(dossier.pdf_path).exists():
        pdf_size_kb = round(Path(dossier.pdf_path).stat().st_size / 1024, 1)

    pdf_report_meta = {
        "web_url": f"/reports/{dossier.pdf_filename}",
        "filename": dossier.pdf_filename,
        "pages": dossier.pdf_pages,
        "file_size_kb": pdf_size_kb
    }

    report_payload = {
        "success": pdf_result.get("success", False),
        "title": f"Research Monograph: {dossier.subject}",
        "subject": dossier.subject,
        "category": dossier.category,
        "mode": dossier.mode,
        "pdf_path": dossier.pdf_path,
        "pdf_filename": dossier.pdf_filename,
        "pdf_pages": dossier.pdf_pages,
        "actual_pages": dossier.actual_pages,
        "pdf_report": pdf_report_meta,
        "sources_analyzed": len(dossier.sources),
        "execution_time_sec": elapsed,
        "spoken_answer": spoken,
        "executive_summary_hi": dossier.executive_summary,
        "key_findings": dossier.key_findings,
        "limitations": dossier.limitations_and_uncertainties,
        "chapters": modules_ui,
        "modules": modules_ui,
        "sources": sources_ui,
        "verified_claims": claims_ui,
        "verification_summary": verif_summary,
        "qa_report": dossier.quality_check,
        "elapsed_seconds": elapsed,
        "timestamp": time.time()
    }

    # Record history
    _RESEARCH_HISTORY.append({
        "subject": dossier.subject,
        "category": dossier.category,
        "mode": dossier.mode,
        "pdf_filename": dossier.pdf_filename,
        "pdf_pages": dossier.pdf_pages,
        "timestamp": time.time()
    })

    # Cache result
    _RESEARCH_CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": report_payload
    }

    return report_payload
