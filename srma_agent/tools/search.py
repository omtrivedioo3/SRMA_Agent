"""Federated literature search across every configured source.

DESIGN NOTE - why this is one coarse tool rather than nine fine ones.

The obvious design exposes each database as its own ADK tool and lets the
model decide which to call. That fails in practice: small models called via
Ollama are unreliable at multi-step tool selection, and a systematic review
must search EVERY source every time anyway. Letting the model choose adds
failure modes while removing no work.

So the model makes one call. This module fans out to all sources in
parallel, isolates failures per source, deduplicates, and returns PRISMA
counts. Source coverage becomes a property of the code rather than
something the model might forget.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from typing import Any, Callable

from .. import config
from ..schemas import StudyRecord
from . import dedupe as dedupe_mod
from . import query as query_mod
from .http import AUDIT, safe_call

# --------------------------------------------------------------------------
# Source registry
# --------------------------------------------------------------------------
# Imported defensively: a source that fails to import (missing optional
# dependency, syntax error during development) must degrade the search
# rather than crash the whole review.

_SOURCES: dict[str, Callable[..., list[StudyRecord]]] = {}
_IMPORT_ERRORS: dict[str, str] = {}


def _register(name: str, module_name: str | None = None) -> None:
    """Bind a source name to its connector's search entry point.

    Two naming conventions are accepted, `search` and `search_<source>`,
    so that adding a connector never requires editing this file and the
    connector in lockstep. A mismatch would otherwise silently drop a
    database from every review.
    """
    module_name = module_name or name
    candidates = ("search", f"search_{name}", f"search_{module_name}")
    try:
        module = __import__(f"{__package__}.{module_name}",
                            fromlist=list(candidates))
        for func_name in candidates:
            func = getattr(module, func_name, None)
            if callable(func):
                _SOURCES[name] = func
                return
        _IMPORT_ERRORS[name] = (
            f"no search entry point found; tried {', '.join(candidates)}")
    except Exception as exc:  # noqa: BLE001
        _IMPORT_ERRORS[name] = f"{type(exc).__name__}: {exc}"


# Core bibliographic sources required by the specification.
_register("pubmed")
_register("europepmc")
_register("clinicaltrials")
# Open scholarly infrastructure: citation graph and DOI metadata.
_register("openalex")
_register("crossref")
_register("semantic_scholar")
# Grey literature: preprints. Required to mitigate publication bias.
_register("preprints")


def available_sources() -> dict[str, Any]:
    """Report which sources loaded, for diagnostics and the PRISMA appendix."""
    return {
        "available": sorted(_SOURCES),
        "unavailable": _IMPORT_ERRORS,
    }


# --------------------------------------------------------------------------
# Federated search
# --------------------------------------------------------------------------


def federated_search(
    query: str | query_mod.StructuredQuery,
    *,
    max_results_per_source: int | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Query every source concurrently in its own dialect, then deduplicate.

    Args:
        query: Either a StructuredQuery, which is rendered separately for
            each database, or a raw Boolean string. Prefer the former.
            A raw string is assumed to be PubMed-flavoured and is adapted
            per source on a best-effort basis - PubMed field tags are
            stripped for databases that do not understand them, and Boolean
            operators are stripped for the two that have no Boolean support
            at all.
        max_results_per_source: Per-source cap. Defaults to config.
        sources: Restrict to named sources. Defaults to all available.

    Returns:
        Dict with per-source results, the exact query sent to each source,
        deduplicated records, and PRISMA counts.
    """
    cap = max_results_per_source or config.MAX_RECORDS_PER_SOURCE
    chosen = sources or sorted(_SOURCES)
    chosen = [s for s in chosen if s in _SOURCES]

    # Rendering happens here rather than inside each connector so that the
    # exact string sent to every database is recorded in one place. A
    # systematic review must be reproducible, which means publishing the
    # per-database query, not just the concept list.
    if isinstance(query, query_mod.StructuredQuery):
        queries = query.render_all(chosen)
        canonical = query.render("pubmed")
    else:
        queries = {name: query_mod.adapt_raw_query(query, name)
                   for name in chosen}
        canonical = query

    per_source: dict[str, dict[str, Any]] = {}
    records_by_source: dict[str, list[StudyRecord]] = {}

    # I/O-bound, so threads are the right tool. Rate limiting lives in
    # http.py and is shared across threads.
    with ThreadPoolExecutor(max_workers=min(8, len(chosen) or 1)) as pool:
        futures = {
            pool.submit(safe_call, name, _SOURCES[name], queries[name], cap):
                name
            for name in chosen
            if queries.get(name)
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - defensive
                result = {"source": name, "status": "error", "count": 0,
                          "records": [], "error": f"{type(exc).__name__}: {exc}"}
            per_source[name] = {
                "status": result["status"],
                "count": result["count"],
                "error": result.get("error"),
                "query_sent": queries[name],
            }
            records_by_source[name] = list(result["records"])

    # Interleave records round-robin across sources in bibliographic priority
    # order so that a screening cap (e.g. max_abstracts_to_screen=20) samples
    # published peer-reviewed trials from PubMed/EuropePMC/OpenAlex rather than
    # taking all 20 records from whichever API responded fastest.
    priority_order = [
        "pubmed", "europepmc", "openalex", "semantic_scholar",
        "crossref", "preprints", "clinicaltrials",
    ]
    ordered_sources = [s for s in priority_order if s in records_by_source]
    ordered_sources += [s for s in sorted(records_by_source) if s not in ordered_sources]

    pooled: list[StudyRecord] = []
    max_len = max((len(v) for v in records_by_source.values()), default=0)
    for i in range(max_len):
        for s in ordered_sources:
            src_list = records_by_source[s]
            if i < len(src_list):
                pooled.append(src_list[i])

    # A source we could not build a query for is still part of the PRISMA
    # accounting; silently omitting it would overstate coverage.
    for name in chosen:
        if not queries.get(name):
            per_source[name] = {
                "status": "skipped", "count": 0, "query_sent": "",
                "error": "no query could be rendered for this source",
            }

    unique, dedupe_report = dedupe_mod.deduplicate(pooled)

    outcome_terms = []
    if isinstance(query, query_mod.StructuredQuery) and query.outcome:
        outcome_terms = [t.lower() for t in (query.outcome.clean_terms() + query.outcome.clean_mesh()) if t]

    import re as _re
    _SECONDARY_OR_PRECLINICAL = _re.compile(
        r"\b(systematic\s+review|meta-analysis|network\s+meta-analysis|"
        r"narrative\s+review|state-of-the-art|expert\s+consensus|"
        r"modeling\s+study|in\s+male\s+and\s+female\s+rats|"
        r"\brats\b|\bmice\b|\bmurine\b|bacillus\s+subtilis|in\s+vitro)\b",
        _re.IGNORECASE,
    )
    _TRIAL_SIGNAL = _re.compile(
        r"\b(randomi[sz]ed|placebo-controlled|double-blind|clinical\s+trial|"
        r"phase\s+(?:2|3|ii|iii)|versus|compared\s+with)\b",
        _re.IGNORECASE,
    )
    _NUMERIC_OUTCOME_SIGNAL = _re.compile(
        r"(\b\d+\s*/\s*\d+\b|\b\d+(?:\.\d+)?%\s*(?:vs\.?|versus|and)\s*\d+(?:\.\d+)?%|"
        r"\b(?:hazard\s+ratio|risk\s+ratio|odds\s+ratio|95%\s*ci|95%\s*confidence\s+interval)\b|"
        r"\bn\s*=\s*\d+)",
        _re.IGNORECASE,
    )

    def _record_priority_key(r: StudyRecord) -> tuple:
        title_str = (r.title or "")
        abs_str = (r.abstract or "")
        combined = f"{title_str} {abs_str}"
        has_abs = 0 if (abs_str and r.has_results is not False) else (1 if abs_str else 2)
        is_secondary = 1 if _SECONDARY_OR_PRECLINICAL.search(title_str) else 0
        has_numeric = 0 if _NUMERIC_OUTCOME_SIGNAL.search(abs_str) else 1
        has_trial = 0 if _TRIAL_SIGNAL.search(combined) else 1
        has_outcome = (
            0 if (outcome_terms and any(ot in combined.lower() for ot in outcome_terms))
            else 1
        )
        return (has_abs, is_secondary, has_numeric, has_trial, has_outcome)

    # Prioritise primary clinical trials with abstracts, quantitative outcome
    # data, and matching outcome terms ahead of secondary reviews, animal
    # studies, or ongoing trial registrations without results.
    unique.sort(key=_record_priority_key)

    # Record sources that failed to import as explicit zeroes. A systematic
    # review must account for every source it claims to have searched.
    for name, err in _IMPORT_ERRORS.items():
        per_source.setdefault(name, {
            "status": "unavailable", "count": 0, "error": err,
            "query_sent": "",
        })

    return {
        "status": "success",
        "query": canonical,
        "queries_by_source": queries,
        "sources_searched": chosen,
        "per_source": per_source,
        "total_identified": len(pooled),
        "duplicates_removed": dedupe_report["duplicates_removed"],
        "unique_records": len(unique),
        "dedupe_report": dedupe_report,
        "records": [asdict(r) for r in unique],
        "audit_summary": AUDIT.summary(),
    }


# --------------------------------------------------------------------------
# ADK tool wrapper
# --------------------------------------------------------------------------


def run_literature_search(boolean_query: str) -> dict:
    """Search all medical literature databases for a systematic review.

    Queries PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex, Crossref,
    Semantic Scholar and medRxiv/bioRxiv preprints simultaneously, then
    removes duplicate records that appear in more than one database.

    Call this exactly once per review, with one comprehensive Boolean query.

    Args:
        boolean_query: A Boolean search string combining population,
            intervention and outcome terms with AND, joining synonyms
            within each block with OR. PubMed field tags such as
            [MeSH] and [tiab] are supported.

    Returns:
        A dictionary containing the record count found in each database,
        the number of duplicates removed, and the deduplicated records.
    """
    result = federated_search(boolean_query)

    # Full records can be tens of thousands of tokens. The model only needs
    # the counts; the records are passed onward through session state.
    return {
        "status": result["status"],
        "query": result["query"],
        "counts_by_source": {
            name: info["count"] for name, info in result["per_source"].items()
        },
        "errors_by_source": {
            name: info["error"]
            for name, info in result["per_source"].items() if info.get("error")
        },
        "total_identified": result["total_identified"],
        "duplicates_removed": result["duplicates_removed"],
        "unique_records": result["unique_records"],
        "sample_titles": [
            r["title"][:120] for r in result["records"][:5]
        ],
    }
