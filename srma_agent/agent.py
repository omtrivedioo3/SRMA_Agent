"""ADK entry point. `adk web` and `adk run` both look for `root_agent` here.

WHAT THE AGENT IS RESPONSIBLE FOR, AND WHAT IT IS NOT

The agent handles the conversation: understanding the question, deciding
whether it is answerable by a systematic review, choosing a tool, and
reporting what came back. That is what language models are reliably good at.

It does not perform the review. The review is `pipeline.run_review`, a
deterministic eight-phase function exposed here as a single tool.

WHY ONE BIG TOOL RATHER THAN EIGHT SMALL ONES

The obvious design gives the agent a tool per phase and lets it sequence
them. It is worse in every way that matters here:

  - The phases have a fixed order. There is no decision for the model to
    make, so exposing the choice only creates opportunities to get it wrong.
  - Intermediate state is large. Passing thousands of records through the
    context window between tool calls is slow, expensive, and lossy.
  - PRISMA requires that every record be accounted for. If the model can
    skip a phase, the flow diagram can silently stop adding up.

So the methodology lives in Python where it is enforced, and the agent gets
one button that runs it correctly.

MODEL SELECTION

The orchestrator is a Gemini model served by Google AI Studio. If no
GOOGLE_API_KEY is configured, it falls back to the local MedGemma model via
LiteLLM so the agent still starts and can still be talked to. Tool calling
is noticeably less reliable in that mode, which is why the status tool
reports which mode is active.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent

from . import config, prompts

# ==========================================================================
# Tools
# ==========================================================================


def check_system_status() -> dict:
    """Check which models and literature databases are currently working.

    Run this when the user asks whether the system is ready, when a review
    has just failed for an unclear reason, or before starting a long review.

    Returns:
        A dictionary reporting the configured models, whether the local
        clinical model is responding, and which literature databases loaded
        successfully.
    """
    from . import llm
    from .tools import search as search_mod

    health = llm.health_check()
    sources = search_mod.available_sources()

    return {
        "status": "ok" if health["status"] == "ok" else "degraded",
        "gemini_backend": config.GEMINI_BACKEND,
        "orchestrator_model": config.ORCHESTRATOR_MODEL,
        "clinical_model": config.CLINICAL_MODEL,
        "google_api_key_configured": bool(config.GOOGLE_API_KEY),
        "clinical_model_reachable": health["status"] == "ok",
        "clinical_model_error": health.get("error"),
        "databases_available": sources["available"],
        "databases_unavailable": sources["unavailable"],
        "note": (
            "No GOOGLE_API_KEY is set, so the local model is orchestrating. "
            "Tool calling is less reliable in this mode. Add a key from "
            "https://aistudio.google.com/apikey to .env to improve it."
            if not config.GOOGLE_API_KEY else
            "Orchestration is running on Gemini via Google AI Studio."
        ),
    }


def search_literature(boolean_query: str) -> dict:
    """Search all nine medical literature databases and report the counts.

    Use this when the user wants to know how much evidence exists on a
    topic, or wants to check a search strategy, WITHOUT running a full
    systematic review. It is fast, taking seconds rather than minutes.

    Searches PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex, Crossref,
    Semantic Scholar, medRxiv and bioRxiv preprints, and openFDA at the
    same time, then removes records that appear in more than one database.

    Args:
        boolean_query: A Boolean search string joining concept blocks with
            AND and synonyms within each block with OR. PubMed field tags
            such as [tiab] and [MeSH Terms] are supported and are ignored
            by databases that do not understand them.

    Returns:
        A dictionary with the record count from each database, the number
        of duplicates removed, the unique record count, and a few sample
        titles so the user can sanity-check the search.
    """
    from .tools import search as search_mod
    return search_mod.run_literature_search(boolean_query)


def run_systematic_review(
    clinical_question: str,
    max_abstracts_to_screen: int = 20,
    max_studies_to_extract: int = 10,
) -> dict:
    """Run a complete systematic review and meta-analysis on a question.

    This performs all eight phases: PICO protocol, search strategy,
    multi-database search, deduplication, dual-reviewer screening, data
    extraction with Cochrane RoB 2 risk-of-bias assessment, statistical
    pooling, and a GRADE certainty rating. It produces PRISMA flow counts,
    a forest plot and a funnel plot.

    This is SLOW. Screening and extraction each require a separate model
    call per record. Expect several minutes at the default caps and
    considerably longer if they are raised. Tell the user it is running and
    roughly how long it will take before you call it.

    Only call this for a question that compares an intervention against
    something, in a defined population, with a measurable outcome. If any
    of those three is missing, ask the user for it instead of calling this.

    Args:
        clinical_question: The question in plain English, for example
            "Does aspirin reduce mortality in adults after myocardial
            infarction compared with placebo?"
        max_abstracts_to_screen: How many records to screen. Higher is more
            thorough and much slower. 20 is a reasonable demonstration; a
            publishable review needs several hundred.
        max_studies_to_extract: How many included studies to extract data
            from. Extraction is the slowest step per record.

    Returns:
        A dictionary with the protocol, the search strategy used, PRISMA
        flow counts, screening decisions with reasons, extracted data,
        the full meta-analysis, the GRADE rating, paths to the generated
        figures, and the directory where the full run was saved.
    """
    from . import pipeline

    result = pipeline.run_review(
        clinical_question,
        max_abstracts_to_screen=max_abstracts_to_screen,
        max_studies_to_extract=max_studies_to_extract,
    )

    # The full result is far too large for a context window: it contains
    # every record and every reviewer justification. Return the findings and
    # point at the file for the rest.
    meta = result.get("meta_analysis") or {}
    pooled = meta.get("pooled") or {}
    het = meta.get("heterogeneity") or {}
    grade = result.get("grade") or {}

    # Read back the rendered plain-text and Markdown reports.
    report_text = ""
    markdown_report = ""
    run_dir = result.get("run_dir")
    if run_dir:
        summary_file = Path(run_dir) / "summary.txt"
        if summary_file.exists():
            report_text = summary_file.read_text()
        md_file = Path(run_dir) / "report.md"
        if md_file.exists():
            markdown_report = md_file.read_text()
    if not markdown_report:
        markdown_report = pipeline.render_markdown_report(result)

    screening_info = result.get("screening") or {}
    extraction_info = result.get("extraction") or {}
    search_info = result.get("search") or {}
    dedupe_rep = search_info.get("dedupe_report") or {}

    summary: dict[str, Any] = {
        "status": "success" if result.get("ok") else "incomplete",
        "run_directory": run_dir,
        "phases_completed": result.get("phases_completed"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "protocol": result.get("protocol"),
        "search_query": result.get("query"),
        "prisma_flow": result.get("prisma"),
        "markdown_report": markdown_report,
        "report_text": report_text,
        "included_studies": extraction_info.get("studies", []),
        "screening_included_records": screening_info.get("included_records", []),
        "screening_excluded_records": screening_info.get("excluded_records", []),
        "skipped_due_to_extraction_cap": extraction_info.get("skipped_due_to_cap", []),
        "excluded_from_meta_analysis": meta.get("excluded_studies", []),
        "removed_duplicates": (dedupe_rep.get("removed_duplicates") or [])[:50],
    }

    if meta.get("ok"):
        summary["results"] = {
            "effect_measure": meta.get("effect_measure_label"),
            "pooled_estimate": pooled.get("estimate_transformed"),
            "ci_95": [pooled.get("ci_low_transformed"),
                      pooled.get("ci_high_transformed")],
            "p_value": pooled.get("p_value"),
            "studies_pooled": meta.get("k_included"),
            "participants": meta.get("total_participants"),
            "i_squared": het.get("I2"),
            "tau_squared": het.get("tau2"),
            "interpretation": meta.get("interpretation"),
            "flags": [f["message"] for f in meta.get("flags", [])],
        }
    if grade:
        summary["grade"] = {
            "certainty": grade.get("final_rating"),
            "summary": grade.get("summary"),
        }
    if result.get("plots"):
        summary["figures"] = result["plots"]
    if result.get("errors"):
        summary["issues"] = result["errors"]

    return summary


def get_review_report(run_id: str = "latest") -> dict:
    """Load and render the complete transparent report for a completed review run.

    Use this when the user asks to inspect, explain, or display the full
    study tables, excluded articles with reasons, extracted evidence, or
    bibliography from the latest run or a specific `run-...` directory
    without re-running the entire pipeline.

    Args:
        run_id: Either "latest" (default) or a specific run directory name
            such as "run-20260921-093515".

    Returns:
        A dictionary containing the full `markdown_report`, `report_text`,
        included studies, excluded articles with reasons, and PRISMA flow.
    """
    import json
    from . import pipeline

    runs_root = Path(config.RUNS_DIR)
    if not runs_root.exists():
        return {"status": "error", "error": f"No runs directory found at {runs_root}"}

    if not run_id or run_id.strip().lower() == "latest":
        candidates = sorted(
            [d for d in runs_root.iterdir() if d.is_dir() and (d / "result.json").exists()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {"status": "error", "error": "No completed runs found in runs/"}
        target_dir = candidates[0]
    else:
        clean_id = Path(run_id.strip()).name
        target_dir = runs_root / clean_id
        if not (target_dir / "result.json").exists():
            return {"status": "error", "error": f"Run '{clean_id}' not found in {runs_root}"}

    result_data = json.loads((target_dir / "result.json").read_text())
    md_report = pipeline.render_markdown_report(result_data)
    txt_report = pipeline.render_summary(result_data)

    # Ensure the on-disk report.md and summary.txt are also up to date
    (target_dir / "report.md").write_text(md_report)
    (target_dir / "summary.txt").write_text(txt_report)

    screening_info = result_data.get("screening") or {}
    extraction_info = result_data.get("extraction") or {}
    meta = result_data.get("meta_analysis") or {}

    return {
        "status": "success",
        "run_id": result_data.get("run_id", target_dir.name),
        "run_directory": str(target_dir),
        "question": result_data.get("question"),
        "prisma_flow": result_data.get("prisma"),
        "markdown_report": md_report,
        "report_text": txt_report,
        "included_studies": extraction_info.get("studies", []),
        "screening_included_records": screening_info.get("included_records", []),
        "screening_excluded_records": screening_info.get("excluded_records", []),
        "excluded_from_meta_analysis": meta.get("excluded_studies", []),
        "figures": result_data.get("plots", {}),
    }


def pool_provided_data(
    studies: list[dict],
    effect_measure: str = "auto",
    model: str = "random",
) -> dict:
    """Run a meta-analysis on study data the user supplies directly.

    Use this when the user already has extracted numbers and wants them
    pooled, rather than wanting a literature search. All statistics are
    computed in Python; no value is estimated by a language model.

    Args:
        studies: One dictionary per study. For binary outcomes supply
            label, events_intervention, n_intervention, events_control and
            n_control. For continuous outcomes supply label,
            mean_intervention, sd_intervention, n_intervention,
            mean_control, sd_control and n_control.
        effect_measure: "auto", "RR", "OR", "RD", "MD" or "SMD". With
            "auto" the measure is inferred from the fields supplied.
        model: "fixed", "random" (DerSimonian-Laird, the default),
            "random_reml", "random_hksj" or "random_reml_hksj".

    Returns:
        The pooled estimate with its confidence interval, per-study effects
        and weights, heterogeneity statistics, publication-bias tests,
        leave-one-out sensitivity results, and an explicit list of any
        studies that could not be analysed and why.
    """
    from .tools import meta_analysis as ma
    return ma.run_meta_analysis(studies, effect_measure=effect_measure,
                                model=model)


# ==========================================================================
# Agent
# ==========================================================================


def _resolve_model():
    """Pick the orchestrator model for the configured backend.

    A bare string such as "gemini-3.6-flash" is resolved by ADK against
    Google AI Studio, because config pins GOOGLE_GENAI_USE_VERTEXAI=FALSE.
    Without an API key we hand back a LiteLlm instance pointing at the
    local Ollama model, so the agent still starts rather than raising at
    import time and breaking `adk web` entirely.
    """
    if config.HAS_GEMINI:
        return config.ORCHESTRATOR_MODEL

    from google.adk.models.lite_llm import LiteLlm
    return LiteLlm(model=config.CLINICAL_MODEL,
                   api_base=config.OLLAMA_API_BASE)


root_agent = LlmAgent(
    name="srma_agent",
    model=_resolve_model(),
    description=(
        "Automated systematic review and meta-analysis of clinical "
        "literature, following PRISMA 2020, the Cochrane Handbook and "
        "GRADE."
    ),
    instruction=prompts.ROOT_AGENT_INSTRUCTION,
    tools=[
        check_system_status,
        search_literature,
        run_systematic_review,
        get_review_report,
        pool_provided_data,
    ],
)
