"""The eight-phase systematic review pipeline.

This is the whole method, in order, in one place:

    1  PICO protocol            LLM  (judgement)
    2  Search strategy          LLM vocabulary + Python syntax
    3  Federated search         Python (9 databases, parallel)
    4  Deduplication            Python (deterministic)
    5  Dual-reviewer screening  LLM x2 + Python consensus
    6  Extraction and RoB 2     LLM  (judgement, grounded in text)
    7  Meta-analysis            Python (numpy/scipy, never the LLM)
    8  GRADE certainty          LLM judgement + Python arithmetic check

THE DIVISION OF LABOUR IS THE DESIGN

The model is used only where the task is judgement applied to supplied
text: is this study eligible, was allocation concealed, is this imprecise.
Every number, count, pooled estimate and flow-diagram figure is computed in
Python. The model never calculates and never recalls a fact from memory.

That line is drawn deliberately. We measured MedGemma 4B inventing five
plausible-sounding but entirely fictitious "RoB 2 domains" when asked to
recall them, and answering correctly when the real domains were supplied.
Anything a model can be wrong about quietly is computed instead.

WHY THIS IS A PLAIN MODULE AND NOT A TREE OF ADK AGENTS

Phases 3, 4 and 7 involve no language model at all. Phase 5 is a loop over
hundreds of records. Modelling those as conversational agent turns would
add failure modes and cost without adding capability. The ADK agent in
agent.py wraps this pipeline as a single tool, which is the part an agent
is genuinely good at: talking to the user and deciding when to run it.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import config, llm, prompts, screening
from .schemas import (
    GradeAssessment,
    PicoProtocol,
    PrismaFlow,
    SearchStrategy,
    StudyExtraction,
    StudyRecord,
)
from .tools import query as query_mod
from .tools import search as search_mod
from .tools.http import AUDIT

# GRADE starting certainty by body of evidence. RCTs start High; everything
# else starts Low. Encoded here rather than left to the model, because it is
# a rule, not a judgement.
_GRADE_ORDER = ["Very low", "Low", "Moderate", "High"]


# ==========================================================================
# Phase 1 - protocol
# ==========================================================================


def build_protocol(question: str) -> PicoProtocol:
    """Turn a clinical question into a PICOS protocol."""
    return llm.call_json(prompts.MODULE_1_PICO, question, PicoProtocol)


def protocol_text(protocol: PicoProtocol) -> str:
    """Render the protocol as the eligibility criteria shown to screeners.

    Supplied in full on every screening call. The model must apply criteria
    it can see, never recall criteria it was told about earlier.
    """
    lines = [
        f"  Population   : {protocol.population}",
        f"  Intervention : {protocol.intervention}",
        f"  Comparator   : {protocol.comparator}",
        f"  Primary outcome : {protocol.primary_outcome}",
    ]
    if protocol.secondary_outcomes:
        lines.append("  Secondary outcomes : "
                     + "; ".join(protocol.secondary_outcomes))
    if protocol.study_designs:
        lines.append("  Eligible designs : " + ", ".join(protocol.study_designs))
    if protocol.inclusion_criteria:
        lines.append("  Inclusion criteria:")
        lines += [f"      - {c}" for c in protocol.inclusion_criteria]
    if protocol.exclusion_criteria:
        lines.append("  Exclusion criteria:")
        lines += [f"      - {c}" for c in protocol.exclusion_criteria]
    return "\n".join(lines)


# ==========================================================================
# Phase 2 - search strategy
# ==========================================================================


def build_query(protocol: PicoProtocol) -> tuple[query_mod.StructuredQuery,
                                                 SearchStrategy]:
    """Ask the model for search vocabulary, then assemble the query here.

    The model supplies vocabulary only. Syntax is assembled in Python and
    rendered per database by tools/query.py, because the two jobs fail
    differently: a missing synonym costs recall, whereas malformed syntax
    returns zero results while looking like an honest empty search.

    Returns the structured query and the strategy it was built from, so the
    reproducibility appendix can show both.
    """
    strategy = llm.call_json(
        prompts.MODULE_2_SEARCH,
        f"Produce search vocabulary for this protocol.\n\n"
        f"{protocol_text(protocol)}\n\n"
        f"Existing keyword suggestions: "
        f"{', '.join(protocol.search_keywords) or '(none)'}\n"
        f"Existing MeSH suggestions: "
        f"{', '.join(protocol.mesh_terms) or '(none)'}",
        SearchStrategy,
    )

    # Each concept gets ONLY its own vocabulary. An earlier version merged
    # every MeSH term into the population block and every protocol keyword
    # into the intervention block, producing
    #     (aspirin OR MI OR ...) AND (aspirin OR MI OR ...)
    # which is very nearly a tautology: both sides were satisfied by any
    # document mentioning either concept, so it matched conference
    # proceedings and review supplements rather than trials.
    structured = query_mod.StructuredQuery(
        population=query_mod.Concept(
            "population", strategy.population_terms, strategy.population_mesh),
        intervention=query_mod.Concept(
            "intervention", strategy.intervention_terms,
            strategy.intervention_mesh),
        outcome=query_mod.Concept("outcome", strategy.outcome_terms, []),
        # Only populated by the model for a named active comparator (e.g.
        # warfarin). Empty for placebo / usual care, so it is never ANDed in.
        comparator=query_mod.Concept(
            "comparator", strategy.comparator_terms, strategy.comparator_mesh),
        # Used only if a concept ends up empty. Raw PICO text is a poor
        # search, but it is honest about being one, unlike a half-built
        # Boolean expression that silently matches everything.
        fallback_text=f"{protocol.population} {protocol.intervention}",
    )
    return structured, strategy


def query_hygiene_report(strategy: SearchStrategy,
                         structured: query_mod.StructuredQuery) -> list[str]:
    """List vocabulary discarded during normalisation, and why.

    Term hygiene silently rewriting the model's output is exactly the kind of
    thing that makes a pipeline hard to trust. A measured run had the model
    return the whole PICO sentence as a population term -
    "Adults with a prior myocardial infarction" - which was quoted as a
    phrase and therefore matched nothing. The repair is correct, but it must
    be visible in the run record rather than inferred from a bad result.
    """
    notes: list[str] = []
    pairs = (
        ("population", strategy.population_terms,
         structured.population.clean_terms()),
        ("intervention", strategy.intervention_terms,
         structured.intervention.clean_terms()),
    )
    for concept, original, kept in pairs:
        kept_lower = {k.lower() for k in kept}
        for term in original:
            normalised = query_mod.normalise_term(term)
            if not normalised:
                notes.append(
                    f"{concept}: dropped {term!r} - not a searchable term "
                    f"(too long to appear in a title or abstract).")
            elif normalised.lower() != str(term).strip().lower() \
                    and normalised.lower() in kept_lower:
                notes.append(
                    f"{concept}: rewrote {term!r} to {normalised!r} - the "
                    f"original was a cohort description, not a phrase an "
                    f"author would write.")
    return notes


# ==========================================================================
# Phase 6 - extraction and risk of bias
# ==========================================================================


def _verify_extracted_numbers(extraction: StudyExtraction, record: StudyRecord) -> None:
    """Deterministically verify that extracted numbers are grounded in the text.

    Small local clinical models (e.g. MedGemma 4B) occasionally fill in
    symmetric placeholder numbers such as 5/10 vs 5/10, 10/10 vs 10/10, or
    split total planned enrollment 50/50 when given a trial registration (NCT)
    or abstract that contains no outcome results. Python catches and nulls out
    any ungrounded numbers before they can corrupt the meta-analysis.
    """
    int_arm = extraction.intervention_arm
    ctrl_arm = extraction.control_arm
    has_binary = (int_arm.n_events is not None or ctrl_arm.n_events is not None)
    has_cont = (int_arm.mean is not None or ctrl_arm.mean is not None)

    if not has_binary and not has_cont:
        return

    # Rule 1: ClinicalTrials.gov registrations that explicitly report
    # has_results=False and have no linked publication (PMID/DOI) do not have
    # posted clinical outcome data.
    if record.nct_id and record.has_results is False and not record.pmid and not record.doi:
        int_arm.n_events = None
        ctrl_arm.n_events = None
        int_arm.mean = None
        int_arm.sd = None
        ctrl_arm.mean = None
        ctrl_arm.sd = None
        if "trial_registration_without_posted_results" not in extraction.missing_data_flags:
            extraction.missing_data_flags.append(
                "trial_registration_without_posted_results"
            )
        return

    # Rule 2: Any extracted event count must either appear literally as a
    # number in the title/abstract or be derivable from a percentage in the
    # text. Symmetric placeholder counts (e.g. 5/10 vs 5/10) not present in
    # the text are rejected.
    haystack = f"{record.title or ''} {record.abstract or ''}"
    numbers_in_text = {int(m) for m in re.findall(r"\b\d+\b", haystack)}
    has_percentage = "%" in haystack or "percent" in haystack.lower()

    if has_binary:
        ev_i = int_arm.n_events
        ev_c = ctrl_arm.n_events
        n_i = int_arm.n_total
        n_c = ctrl_arm.n_total

        # Check if neither event count appears in the text and no percentages
        # are reported, OR if the model emitted identical symmetric numbers
        # (ev_i == ev_c and n_i == n_c) where the event count is absent from text.
        events_in_text = (
            (ev_i is not None and ev_i in numbers_in_text)
            or (ev_c is not None and ev_c in numbers_in_text)
        )
        symmetric_hallucination = (
            ev_i is not None
            and ev_i == ev_c
            and n_i is not None
            and n_i == n_c
            and ev_i not in numbers_in_text
        )
        if (not events_in_text and not has_percentage) or symmetric_hallucination:
            int_arm.n_events = None
            ctrl_arm.n_events = None
            if "ungrounded_event_counts_removed_by_python_verifier" not in extraction.missing_data_flags:
                extraction.missing_data_flags.append(
                    "ungrounded_event_counts_removed_by_python_verifier"
                )


def extract_study(record: StudyRecord, protocol: PicoProtocol) -> StudyExtraction:
    """Extract outcome data and assess RoB 2 for one study.

    Only the abstract is available for most records, so most extractions
    will legitimately return nulls and populate missing_data_flags. That is
    the correct behaviour, not a failure: the specification forbids
    inferring a number that was not reported.
    """
    label = record.citation
    rec_source = ", ".join(
        record.sources or ([record.source] if record.source else [])
    ) or "unknown"
    trial_status_line = (
        f"TRIAL STATUS: {record.trial_status or 'not stated'} "
        f"(has_posted_results={record.has_results})\n"
        if record.nct_id else ""
    )
    text = (
        f"STUDY IDENTIFIER: {record.best_id}\n"
        f"SUGGESTED LABEL: {label}\n"
        f"YEAR: {record.year or 'not stated'}\n"
        f"SOURCE DATABASE: {rec_source}\n"
        f"PUBLICATION TYPE: {', '.join(record.publication_types) or 'not stated'}\n"
        f"REGISTRATION: {record.nct_id or 'none found'}\n"
        f"{trial_status_line}\n"
        f"TITLE: {record.title}\n\n"
        f"TEXT AVAILABLE FOR EXTRACTION:\n{record.abstract or '(none)'}\n\n"
        f"TARGET OUTCOME: {protocol.primary_outcome}"
    )
    extraction = llm.call_json(prompts.MODULE_4_5_EXTRACTION, text,
                               StudyExtraction)

    # Always enforce deterministic provenance fields from the source record.
    extraction.study_id = record.best_id
    extraction.study_label = label
    extraction.title = record.title or extraction.title
    extraction.source_db = rec_source
    extraction.verification_url = record.verification_url
    if extraction.year is None:
        extraction.year = record.year

    # Verify extracted numbers against source text and trial results status.
    _verify_extracted_numbers(extraction, record)

    # Full text was not retrieved, so domains resting on the methods
    # section cannot honestly be judged Low risk from an abstract alone.
    if record.abstract and not record.full_text_url:
        if "assessed_from_abstract_only" not in extraction.missing_data_flags:
            extraction.missing_data_flags.append("assessed_from_abstract_only")
    return extraction


def _extraction_to_meta_input(extraction: StudyExtraction) -> dict[str, Any]:
    """Shape one extraction for the meta-analysis engine."""
    return {
        "label": extraction.study_label or extraction.study_id,
        "study_id": extraction.study_id,
        "year": extraction.year,
        "intervention_arm": extraction.intervention_arm.model_dump(),
        "control_arm": extraction.control_arm.model_dump(),
    }


# ==========================================================================
# Phase 8 - GRADE
# ==========================================================================


def _verify_grade(assessment: GradeAssessment) -> tuple[str, list[str]]:
    """Recompute the GRADE rating from the domain downgrades.

    The model reports both the per-domain downgrades and a final rating.
    Those two can disagree, and a wrong certainty rating is exactly the kind
    of error a reader would never catch. So the rating is recomputed here
    and the model's own answer is overridden when it does not follow.
    """
    start_index = _GRADE_ORDER.index(assessment.starting_rating.value)
    total = sum(d.downgrade_levels for d in (
        assessment.risk_of_bias,
        assessment.inconsistency,
        assessment.indirectness,
        assessment.imprecision,
        assessment.publication_bias,
    ))
    computed = _GRADE_ORDER[max(0, start_index - total)]

    notes: list[str] = []
    if computed != assessment.final_rating.value:
        notes.append(
            f"The model reported '{assessment.final_rating.value}' but its "
            f"own domain judgements total {total} downgrade level(s) from "
            f"'{assessment.starting_rating.value}', which gives "
            f"'{computed}'. The computed value is used."
        )
    return computed, notes


def assess_grade(
    protocol: PicoProtocol,
    meta_result: dict[str, Any],
    extractions: list[StudyExtraction],
) -> dict[str, Any]:
    """Rate certainty of evidence, then check the arithmetic in Python."""
    rob_counts: dict[str, int] = {}
    for ex in extractions:
        if ex.rob_overall:
            key = ex.rob_overall.value
            rob_counts[key] = rob_counts.get(key, 0) + 1

    het = meta_result.get("heterogeneity", {})
    pooled = meta_result.get("pooled", {})
    bias = meta_result.get("publication_bias", {})

    facts = (
        f"OUTCOME: {protocol.primary_outcome}\n"
        f"POPULATION: {protocol.population}\n"
        f"INTERVENTION: {protocol.intervention} versus {protocol.comparator}\n\n"
        f"COMPUTED STATISTICS - these are final, do not recalculate them:\n"
        f"  Effect measure       : {meta_result.get('effect_measure_label')}\n"
        f"  Pooled estimate      : {pooled.get('estimate_transformed')}\n"
        f"  95% CI               : {pooled.get('ci_low_transformed')} to "
        f"{pooled.get('ci_high_transformed')}\n"
        f"  p-value              : {pooled.get('p_value')}\n"
        f"  Studies pooled       : {meta_result.get('k_included')}\n"
        f"  Total participants   : {meta_result.get('total_participants')}\n"
        f"  I-squared            : {het.get('I2')}%\n"
        f"  tau-squared          : {het.get('tau2')}\n"
        f"  Cochran's Q          : {het.get('Q')} (p = {het.get('p_value')})\n"
        f"  Egger's test         : {json.dumps(bias.get('egger', {}))[:400]}\n"
        f"  Risk of bias tally   : {rob_counts or 'not assessed'}\n"
        f"  Engine warnings      : {'; '.join(meta_result.get('warnings', [])) or 'none'}\n"
        f"  Engine flags         : "
        f"{'; '.join(f['message'] for f in meta_result.get('flags', [])) or 'none'}\n"
    )

    assessment = llm.call_json(
        prompts.MODULE_6_8_SYNTHESIS
        + "\n\nProduce ONLY the GRADE assessment, as JSON matching the schema.",
        facts,
        GradeAssessment,
    )
    computed, notes = _verify_grade(assessment)

    payload = assessment.model_dump()
    payload["final_rating"] = computed
    payload["verification_notes"] = notes
    return payload


# ==========================================================================
# Orchestration
# ==========================================================================


def run_review(
    question: str,
    *,
    max_records_per_source: int | None = None,
    max_abstracts_to_screen: int | None = None,
    max_studies_to_extract: int | None = None,
    effect_measure: str = "auto",
    model: str = "random",
    make_plots: bool = True,
    run_id: str | None = None,
    on_phase: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Run a complete systematic review and meta-analysis.

    Args:
        question: The clinical question, in plain English.
        max_records_per_source: Per-database retrieval cap.
        max_abstracts_to_screen: Screening cap. None -> config default;
            0 -> unbounded (screen every deduplicated record).
        max_studies_to_extract: Extraction cap. None -> config default;
            0 -> unbounded (extract every included study).
        effect_measure: "auto", "RR", "OR", "RD", "MD" or "SMD".
        model: Pooling model. See meta_analysis.run_meta_analysis.
        make_plots: Render forest and funnel plots.
        run_id: Output directory name under runs/. Timestamped if omitted.
        on_phase: Callback(phase_name, message) for progress reporting.

    Returns:
        A dict containing the protocol, search strategy, PRISMA counts,
        screening results, extractions, the full meta-analysis, the GRADE
        assessment, plot paths, and the path to the saved run directory.

        A failure in any phase is captured in the returned dict rather than
        raised. A review that got as far as screening still has value, and
        the PRISMA record of what was searched must survive the failure.
    """
    started = time.time()
    run_id = run_id or datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    out_dir = Path(config.RUNS_DIR) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # None -> config default. 0 (or negative) -> unbounded, handled where
    # the slice happens so the "cap reached" bookkeeping stays correct.
    if max_studies_to_extract is None:
        max_studies_to_extract = config.MAX_STUDIES_TO_EXTRACT

    def emit(phase: str, message: str) -> None:
        if on_phase:
            on_phase(phase, message)

    # The audit log is module-level and shared. Snapshot from here so the
    # saved log covers this run only.
    audit_start = len(AUDIT.records)

    result: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "run_dir": str(out_dir),
        "question": question,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "gemini_backend": config.GEMINI_BACKEND,
            "orchestrator_model": config.ORCHESTRATOR_MODEL,
            "clinical_model": config.CLINICAL_MODEL,
            "clinical_endpoint": (
                config.VERTEX_MEDGEMMA_ENDPOINT_ID
                if config.CLINICAL_MODEL.startswith("vertex") else config.OLLAMA_API_BASE
            ),
            "clinical_fallback": (
                config.LOCAL_CLINICAL_MODEL if config.VERTEX_FALLBACK_TO_LOCAL else None
            ),
            "clinical_workers": config.CLINICAL_MAX_WORKERS,
            "max_abstracts_to_screen": (
                max_abstracts_to_screen if max_abstracts_to_screen is not None
                else config.MAX_ABSTRACTS_TO_SCREEN
            ) or "unbounded",
            "max_studies_to_extract": max_studies_to_extract or "unbounded",
        },
        "phases_completed": [],
        "errors": [],
    }
    prisma = PrismaFlow()

    def fail(phase: str, exc: Exception) -> dict[str, Any]:
        result["errors"].append(f"{phase}: {type(exc).__name__}: {exc}")
        result["failed_at"] = phase
        result["prisma"] = prisma.to_dict()
        result["elapsed_seconds"] = round(time.time() - started, 1)
        _save(out_dir, result, audit_start)
        return result

    # --- Phase 1: protocol ------------------------------------------------
    emit("protocol", "Formulating the PICO protocol")
    try:
        protocol = build_protocol(question)
    except Exception as exc:  # noqa: BLE001
        return fail("protocol", exc)
    result["protocol"] = protocol.model_dump()
    result["protocol_text"] = protocol_text(protocol)
    result["phases_completed"].append("protocol")

    # --- Phase 2: search strategy ----------------------------------------
    emit("search_strategy", "Building the Boolean search strategy")
    try:
        structured, strategy = build_query(protocol)
    except Exception as exc:  # noqa: BLE001
        return fail("search_strategy", exc)

    query = structured.render("pubmed")
    hygiene = query_hygiene_report(strategy, structured)

    result["search_strategy"] = {
        **strategy.model_dump(),
        **structured.describe(),
        "hygiene_notes": hygiene,
    }
    result["query"] = query
    result["queries_by_source"] = structured.render_all(
        search_mod.available_sources()["available"])
    result["phases_completed"].append("search_strategy")

    # A query that falls back to raw PICO text is not a systematic search.
    # Say so in the report rather than letting the reader assume the
    # Boolean strategy shown was the one actually used.
    if not structured.is_usable():
        result["errors"].append(
            "The search vocabulary was too thin to build a two-concept "
            "Boolean query, so a plain-text fallback was used. Recall is "
            "likely poor and the strategy is not reproducible as written."
        )
    for note in hygiene:
        emit("search_strategy", note)

    # --- Phase 3 + 4: search and deduplicate ------------------------------
    emit("search", f"Searching every database in its own dialect: "
                   f"{query[:110]}")
    try:
        found = search_mod.federated_search(
            structured, max_results_per_source=max_records_per_source)
    except Exception as exc:  # noqa: BLE001
        return fail("search", exc)

    records = [StudyRecord(**r) for r in found["records"]]
    prisma.identified_by_source = {
        name: info["count"] for name, info in found["per_source"].items()
    }
    prisma.total_identified = found["total_identified"]
    prisma.duplicates_removed = found["duplicates_removed"]

    result["search"] = {
        "query": query,
        "queries_by_source": found.get("queries_by_source", {}),
        "queries_by_source_precision": found.get("queries_by_source_precision", {}),
        "per_source": found["per_source"],
        "total_identified": found["total_identified"],
        "duplicates_removed": found["duplicates_removed"],
        "unique_records": found["unique_records"],
        "dedupe_report": found.get("dedupe_report", {}),
        "sources_unavailable": search_mod.available_sources()["unavailable"],
    }
    result["phases_completed"] += ["search", "deduplication"]
    emit("search", f"{found['total_identified']} records, "
                   f"{found['unique_records']} unique after deduplication")

    if not records:
        result["errors"].append(
            "The search returned no records. Either the question is too "
            "narrow, or the query was over-constrained. The PRISMA counts "
            "above show which databases were reachable."
        )
        result["prisma"] = prisma.to_dict()
        result["elapsed_seconds"] = round(time.time() - started, 1)
        _save(out_dir, result, audit_start)
        return result

    # --- Phase 5: screening -----------------------------------------------
    cap = (max_abstracts_to_screen if max_abstracts_to_screen is not None
           else config.MAX_ABSTRACTS_TO_SCREEN)
    if cap and cap > 0:
        emit("screening", f"Screening up to {cap} of {len(records)} records "
                          f"with two reviewers ({config.CLINICAL_MAX_WORKERS} parallel)")
    else:
        emit("screening", f"Screening all {len(records)} records with two "
                          f"reviewers ({config.CLINICAL_MAX_WORKERS} parallel)")
    try:
        screened = screening.screen_batch(
            records, result["protocol_text"], max_records=cap,
            max_workers=config.CLINICAL_MAX_WORKERS,
            # The same vocabulary the search was built from. Reusing it keeps
            # the gate consistent with the query: a record the search should
            # never have returned is exactly what the gate should remove.
            population_terms=structured.population.clean_terms()
            + structured.population.clean_mesh(),
            intervention_terms=structured.intervention.clean_terms()
            + structured.intervention.clean_mesh(),
            progress=lambda i, n, rec, res: emit(
                "screening", f"[{i}/{n}] {res.consensus.value}: {rec.title[:70]}"),
        )
    except Exception as exc:  # noqa: BLE001
        return fail("screening", exc)

    prisma.records_screened = screened["screened"]
    prisma.excluded_at_screening = screened["n_excluded"]
    prisma.exclusion_reasons = screened["exclusion_reasons"]
    prisma.studies_included = screened["n_included"]

    result["screening"] = {
        "screened": screened["screened"],
        "not_screened": screened["not_screened"],
        "not_screened_note": screened["not_screened_note"],
        "included": screened["n_included"],
        "excluded": screened["n_excluded"],
        "exclusion_reasons": screened["exclusion_reasons"],
        "included_records": screened["included_records"],
        "excluded_records": screened["excluded"],
        "gate_rejected": screened["gate_rejected"],
        "gate_note": screened["gate_note"],
        "reviewer_disagreements": screened["reviewer_disagreements"],
        "reviewer_agreement_rate": screened["reviewer_agreement_rate"],
        "agreement_note": screened["agreement_note"],
        "errors": screened["errors"],
        "elapsed_seconds": screened["elapsed_seconds"],
    }
    result["phases_completed"].append("screening")
    emit("screening", f"{screened['n_included']} included, "
                      f"{screened['n_excluded']} excluded "
                      f"({screened['gate_rejected']} by relevance gate)")

    included = list(screened["included"])
    if not included:
        result["errors"].append(
            "No record survived screening. The eligibility criteria may be "
            "too strict, or the search may have retrieved the wrong "
            "literature. See screening.excluded_records for the reasons."
        )
        result["prisma"] = prisma.to_dict()
        result["elapsed_seconds"] = round(time.time() - started, 1)
        _save(out_dir, result, audit_start)
        return result

    # --- Phase 6: extraction and risk of bias -----------------------------
    # Prioritise peer-reviewed publications and trials with posted results
    # ahead of ongoing registry protocols when an extraction cap is active.
    included.sort(
        key=lambda r: (
            0 if (r.pmid or r.doi or r.has_results is True) else
            1 if r.has_results is None else
            2,
            1 if re.search(
                r"\b(systematic\s+review|meta-analysis|narrative\s+review|"
                r"state-of-the-art|expert\s+consensus|modeling\s+study|"
                r"\brats\b|\bmice\b|\bmurine\b)\b",
                r.title or "",
                re.IGNORECASE,
            ) else 0,
            0 if re.search(
                r"(\b\d+\s*/\s*\d+\b|\b\d+(?:\.\d+)?%|\bn\s*=\s*\d+|\b95%\s*ci\b)",
                r.abstract or "",
                re.IGNORECASE,
            ) else 1,
        )
    )
    to_extract = (
        included[:max_studies_to_extract]
        if max_studies_to_extract and max_studies_to_extract > 0
        else list(included)
    )
    skipped_extract = included[len(to_extract):]
    skipped_due_to_cap = [
        {
            "id": r.best_id,
            "citation": r.citation,
            "year": r.year,
            "source": ", ".join(r.sources or ([r.source] if r.source else [])),
            "url": r.verification_url,
            "title": (r.title or "")[:240],
            "reason": (
                f"Passed dual-reviewer title/abstract screening, but skipped "
                f"at Phase 6 because max_studies_to_extract={max_studies_to_extract} "
                f"cap was reached."
            ),
        }
        for r in skipped_extract
    ]

    emit("extraction", f"Extracting data and assessing RoB 2 for "
                       f"{len(to_extract)} studies "
                       f"({config.CLINICAL_MAX_WORKERS} parallel)")
    extractions: list[StudyExtraction] = []
    extraction_errors: list[dict[str, str]] = []

    # Each extraction is an independent model call, so they run concurrently.
    # Results are collected into a positional slot list and then flattened
    # in the original order: downstream code (meta-analysis excluded_studies
    # `index`, Table 1 numbering, PDF) assumes extraction order == to_extract
    # order, and a completion-order list would silently scramble that.
    def _extract_one(idx_record: tuple[int, StudyRecord]):
        idx, record = idx_record
        try:
            return idx, extract_study(record, protocol), None
        except Exception as exc:  # noqa: BLE001
            return idx, None, f"{type(exc).__name__}: {exc}"

    slots: list[StudyExtraction | None] = [None] * len(to_extract)
    slot_errors: list[dict[str, str] | None] = [None] * len(to_extract)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, config.CLINICAL_MAX_WORKERS)) as pool:
        for idx, extraction, error in pool.map(_extract_one, enumerate(to_extract)):
            done += 1
            record = to_extract[idx]
            if error is None:
                slots[idx] = extraction
                emit("extraction", f"[{done}/{len(to_extract)}] {record.best_id}")
            else:
                slot_errors[idx] = {
                    "record": record.best_id,
                    "title": (record.title or "")[:200],
                    "url": record.verification_url,
                    "error": error,
                }
                emit("extraction", f"[{done}/{len(to_extract)}] FAILED {record.best_id}")

    extractions = [e for e in slots if e is not None]
    extraction_errors = [e for e in slot_errors if e is not None]

    prisma.full_text_assessed = len(to_extract)
    result["extraction"] = {
        "attempted": len(to_extract),
        "succeeded": len(extractions),
        "not_attempted": len(skipped_due_to_cap),
        "skipped_due_to_cap": skipped_due_to_cap,
        "errors": extraction_errors,
        "studies": [e.model_dump() for e in extractions],
    }
    result["phases_completed"].append("extraction")

    # --- Phase 7: meta-analysis -------------------------------------------
    emit("meta_analysis", "Pooling the results")
    from .tools import meta_analysis as ma  # imported late; scipy is heavy

    meta_input = [_extraction_to_meta_input(e) for e in extractions]
    try:
        meta_result = ma.run_meta_analysis(
            meta_input, effect_measure=effect_measure, model=model)
    except Exception as exc:  # noqa: BLE001
        return fail("meta_analysis", exc)
    result["meta_analysis"] = meta_result
    result["phases_completed"].append("meta_analysis")

    excluded_at_ft = meta_result.get("excluded_studies") or []
    prisma.excluded_at_full_text = len(excluded_at_ft)
    ft_reasons: dict[str, int] = {}
    for ex_item in excluded_at_ft:
        rc = ex_item.get("reason_code") or "Missing quantitative outcome data"
        ft_reasons[rc] = ft_reasons.get(rc, 0) + 1
    prisma.full_text_exclusion_reasons = ft_reasons

    if not meta_result.get("ok"):
        # Not fatal. A review whose studies did not report poolable data is
        # a legitimate finding, and the narrative synthesis still stands.
        result["errors"].append(
            f"Quantitative pooling was not possible: {meta_result.get('error')}. "
            "This usually means the abstracts did not report event counts or "
            "means with standard deviations. A narrative synthesis is the "
            "correct output in that case, not a fabricated number."
        )
        prisma.studies_included = 0
        result["prisma"] = prisma.to_dict()
        result["elapsed_seconds"] = round(time.time() - started, 1)
        _save(out_dir, result, audit_start)
        return result

    emit("meta_analysis", meta_result.get("interpretation", "")[:160])

    # --- plots -------------------------------------------------------------
    if make_plots:
        try:
            from .tools import plots
            result["plots"] = {
                "forest": plots.forest_plot(
                    meta_result, str(out_dir / "forest.png"),
                    title=f"{protocol.intervention} vs {protocol.comparator}"),
                "funnel": plots.funnel_plot(
                    meta_result, str(out_dir / "funnel.png")),
            }
            result["phases_completed"].append("plots")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"plots: {type(exc).__name__}: {exc}")

    # --- Phase 8: GRADE ----------------------------------------------------
    emit("grade", "Rating certainty of evidence with GRADE")
    try:
        result["grade"] = assess_grade(protocol, meta_result, extractions)
        result["phases_completed"].append("grade")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"grade: {type(exc).__name__}: {exc}")

    # --- finish ------------------------------------------------------------
    prisma.studies_included = meta_result.get("k_included", len(extractions))
    result["prisma"] = prisma.to_dict()
    result["ok"] = True
    result["elapsed_seconds"] = round(time.time() - started, 1)
    _save(out_dir, result, audit_start)
    emit("done", f"Review complete in {result['elapsed_seconds']}s -> {out_dir}")
    return result


def _save(out_dir: Path, result: dict[str, Any], audit_start: int) -> None:
    """Persist the run so any claim in the report can be traced back.

    Artefacts saved: full result JSON, HTTP audit log, plain-text summary,
    publication-grade Markdown report (`report.md`), reproducible R script
    (`r_script.R`), and publication-grade PDF manuscript (`manuscript.pdf`).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from .tools import pdf_report
        r_code = pdf_report.generate_r_script(result)
        r_path = out_dir / "r_script.R"
        r_path.write_text(r_code)
        result["r_script_path"] = str(r_path)

        pdf_path = out_dir / "manuscript.pdf"
        pdf_report.generate_manuscript_pdf(result, pdf_path)
        result["pdf_report"] = str(pdf_path)
    except Exception as exc:  # noqa: BLE001
        result.setdefault("errors", []).append(
            f"pdf_report: {type(exc).__name__}: {exc}"
        )

    (out_dir / "result.json").write_text(
        json.dumps(result, indent=2, default=str))

    audit = AUDIT.as_dicts()[audit_start:]
    (out_dir / "audit_log.json").write_text(json.dumps(audit, indent=2))

    (out_dir / "summary.txt").write_text(render_summary(result))
    (out_dir / "report.md").write_text(render_markdown_report(result))


def _md_cell(val: Any, max_len: int = 240) -> str:
    """Sanitise a value for safe inclusion inside a Markdown table cell."""
    text = str(val if val is not None else "").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len - 3].rstrip() + "..."
    return text.replace("|", "\\|")


def _infer_url(study_id: str, existing_url: str = "") -> str:
    """Ensure every study ID has a direct clickable verification URL."""
    if existing_url and existing_url != "None":
        return existing_url
    sid = str(study_id or "").strip()
    if not sid:
        return ""
    if sid.startswith("http"):
        return sid
    if sid.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{sid.upper()}"
    if sid.upper().startswith("PMID:"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{sid.split(':', 1)[1].strip()}/"
    if sid.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{sid}/"
    if sid.upper().startswith("PMC"):
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{sid.upper()}/"
    if "/" in sid and sid[:3] in ("10.", "doi"):
        clean = sid.removeprefix("doi:").removeprefix("DOI:").strip()
        return f"https://doi.org/{clean}"
    return ""


def _format_id_link(study_id: str, url: str = "") -> str:
    """Format a study identifier as a clickable Markdown link when possible."""
    sid = str(study_id or "Unknown").strip()
    link = _infer_url(sid, url)
    if link:
        return f"[`{sid}`]({link})"
    return f"`{sid}`"


def render_markdown_report(result: dict[str, Any]) -> str:
    """Render a comprehensive, publication-grade Markdown systematic review report.

    Modeled on peer-reviewed systematic reviews (e.g. Acta Oncologica / PRISMA
    2020 / Cochrane Handbook), providing 100% article-level transparency for
    ADK Web, Gemini Enterprise, and saved run artifacts.
    """
    lines: list[str] = []
    add = lines.append

    question = result.get("question", "")
    run_id = result.get("run_id", "")
    generated = result.get("generated_utc", "")
    elapsed = result.get("elapsed_seconds", "")
    cfg = result.get("config") or {}
    protocol = result.get("protocol") or {}
    search_info = result.get("search") or {}
    prisma = result.get("prisma") or {}
    screening_info = result.get("screening") or {}
    extraction_info = result.get("extraction") or {}
    meta = result.get("meta_analysis") or {}
    grade = result.get("grade") or {}
    plots = result.get("plots") or {}

    # Build lookup maps across phases so every study has unified metadata
    inc_records = screening_info.get("included_records") or []
    exc_records = screening_info.get("excluded_records") or []
    inc_by_id: dict[str, dict[str, Any]] = {
        str(r.get("id")): r for r in inc_records if r.get("id")
    }
    extracted_studies = extraction_info.get("studies") or []
    ext_by_id: dict[str, dict[str, Any]] = {
        str(s.get("study_id")): s for s in extracted_studies if s.get("study_id")
    }

    # Map pooled meta-analysis study rows by study_id or label
    pooled_studies = meta.get("studies") or []
    pooled_by_key: dict[str, dict[str, Any]] = {}
    for ps in pooled_studies:
        lbl = str(ps.get("label") or "")
        pooled_by_key[lbl] = ps
        for sid, ext in ext_by_id.items():
            if sid in lbl or lbl == str(ext.get("study_label") or ""):
                pooled_by_key[sid] = ps

    meta_excluded = meta.get("excluded_studies") or []
    meta_exc_by_label: dict[str, dict[str, Any]] = {
        str(e.get("label") or ""): e for e in meta_excluded
    }

    # Aggregate pooled arm totals and single-arm rates
    total_int_ev = 0
    total_int_n = 0
    total_ctrl_ev = 0
    total_ctrl_n = 0
    pooled_id_list: list[str] = []
    single_arm_rates: list[str] = []
    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        label = str(ext.get("study_label") or sid)
        ps = pooled_by_key.get(sid) or pooled_by_key.get(label)
        ia = ext.get("intervention_arm") or {}
        ca = ext.get("control_arm") or {}
        if ps:
            pooled_id_list.append(f"[{idx}] {sid}")
            if ia.get("n_events") is not None and ia.get("n_total") is not None:
                total_int_ev += int(ia["n_events"])
                total_int_n += int(ia["n_total"])
            if ca.get("n_events") is not None and ca.get("n_total") is not None:
                total_ctrl_ev += int(ca["n_events"])
                total_ctrl_n += int(ca["n_total"])
        elif ia.get("n_events") is not None and ia.get("n_total"):
            pct_sa = (int(ia["n_events"]) / int(ia["n_total"])) * 100.0
            single_arm_rates.append(f"`[{idx}] {sid}` ({ia['n_events']}/{ia['n_total']}, {pct_sa:.1f}%)")

    # ======================================================================
    # HEADER & SECTION 1: STRUCTURED ABSTRACT & EXECUTIVE CLINICAL SYNTHESIS
    # ======================================================================
    add("# Systematic Review and Meta-Analysis Report")
    add("")
    add(f"**Clinical Question:** {question}")
    add(f"**Run ID:** `{run_id}` | **Generated (UTC):** `{generated}` | "
        f"**Elapsed Time:** `{elapsed}s` | "
        f"**Clinical Model:** `{cfg.get('clinical_model', 'medgemma')}`")
    add("")

    add("## 1. Structured Abstract & Executive Evidence Synthesis")
    add("")
    pop_simple = protocol.get("population") or "the target clinical cohort"
    int_simple = protocol.get("intervention") or "the target intervention"
    cmp_simple = protocol.get("comparator") or "the comparator / control regimen"
    out_simple = protocol.get("primary_outcome") or "the primary clinical outcome"
    tot_id_abs = prisma.get("total_identified", search_info.get("total_identified", 0))
    dups_abs = prisma.get("duplicates_removed", search_info.get("duplicates_removed", 0))
    uniq_abs = search_info.get("unique_records", max(0, tot_id_abs - dups_abs))
    scr_abs = screening_info.get("screened", prisma.get("records_screened", 0))
    exc_abs = screening_info.get("excluded", prisma.get("excluded_at_screening", 0))
    inc_abs = screening_info.get("included", len(inc_records))

    add(f"- **Background & Objective:** To systematically evaluate and synthesize clinical evidence addressing **{out_simple}** in **{pop_simple}** receiving **{int_simple}** compared with **{cmp_simple}**.")
    add(f"- **Methods (PRISMA 2020 / Cochrane Handbook):** Multi-database searches were executed across indexed biomedical repositories, clinical trial registries, and preprint servers (`{tot_id_abs}` records identified; `{dups_abs}` duplicates removed; `{uniq_abs}` unique citations). Records underwent deterministic PICO relevance gating and independent dual-reviewer screening (`{scr_abs}` screened; `{exc_abs}` excluded with documented PRISMA reasons; `{inc_abs}` eligible). Structured arm-level extraction and 5-domain Cochrane Risk of Bias 2.0 (RoB 2) assessments were performed on `{len(extracted_studies)}` studies.")

    if meta.get("ok"):
        pooled = meta["pooled"]
        het = meta["heterogeneity"]
        eff_label = meta.get("effect_measure_label", "Effect Estimate")
        est = pooled.get("estimate_transformed")
        ci_l = pooled.get("ci_low_transformed")
        ci_h = pooled.get("ci_high_transformed")
        pval = pooled.get("p_value")
        k_inc = meta.get("k_included", 0)
        n_part = meta.get("total_participants") or "Not stated"
        i2 = het.get("I2")
        tau2 = het.get("tau2")
        grade_rating = grade.get("final_rating", "Not rated")
        grade_summary = grade.get("summary") or ""

        arm_rates_str = ""
        if total_int_n > 0 and total_ctrl_n > 0:
            arm_rates_str = (
                f" Aggregate event rates across pooled arms were `{total_int_ev}/{total_int_n}` "
                f"(`{total_int_ev / total_int_n * 100:.1f}%`) in the **{int_simple}** group versus "
                f"`{total_ctrl_ev}/{total_ctrl_n}` (`{total_ctrl_ev / total_ctrl_n * 100:.1f}%`) in the **{cmp_simple}** group."
            )
        het_sent = (
            f" Between-study heterogeneity was `I² = {i2:.1f}%` (`τ² = {(tau2 or 0.0):.4f}`, `Q = {(het.get('Q') or 0.0):.2f}`, `p = {(het.get('p_value') or 1.0):.4g}`)."
            if i2 is not None
            else " Between-study heterogeneity was not estimable (`k = 1`)."
        )
        add(f"- **Results (Quantitative Synthesis):** A total of **`{k_inc}` studies** (`{n_part}` participants; Study IDs: {', '.join(f'`{s}`' for s in pooled_id_list)}) contributed to quantitative random-effects pooling. The pooled **{eff_label}** was **`{est:.3f}`** (95% CI `{ci_l:.3f}` to `{ci_h:.3f}`; `p = {pval:.4g}`).{arm_rates_str}{het_sent}")
        add(f"- **Conclusion & GRADE Certainty:** **{grade_rating} Certainty** — {grade_summary or meta.get('interpretation', '')}")
        add("")

        add("| Metric | Value | Methodological & Clinical Interpretation |")
        add("| :--- | :--- | :--- |")
        add(f"| **Primary Endpoint** | {_md_cell(protocol.get('primary_outcome'))} | "
            f"Comparing {_md_cell(protocol.get('intervention'))} vs. {_md_cell(protocol.get('comparator'))} |")
        add(f"| **Pooled {eff_label}** | **`{est:.3f}`** (95% CI `{ci_l:.3f}` to `{ci_h:.3f}`) | "
            f"`p = {pval:.4g}` ({'Statistically significant effect (p < 0.05)' if pval is not None and pval < 0.05 else 'No statistically significant difference demonstrated (p >= 0.05)'}) |")
        add(f"| **Pooled Study Cohort** | **`{k_inc}` studies** (`{n_part}` participants) | "
            f"`{tot_id_abs}` identified -> `{scr_abs}` screened -> `{len(extracted_studies)}` extracted -> `{k_inc}` pooled |")
        if i2 is not None:
            add(f"| **Between-Study Heterogeneity** | **`I² = {i2:.1f}%`** (`τ² = {tau2:.4f}`, `Q = {het.get('Q', 0):.2f}`, `p = {het.get('p_value', 1):.4g}`) | "
                f"{_md_cell(het.get('interpretation', ''))} |")
        add(f"| **GRADE Certainty of Evidence** | **`{grade_rating}`** | "
            f"{_md_cell(grade_summary)} |")
        add("")
        if meta.get("interpretation"):
            add(f"> **Quantitative Synthesis Conclusion:** {meta['interpretation']}")
            add("")
    else:
        sa_note = (
            f" Single-arm event rates extracted from included cohorts included: {', '.join(single_arm_rates)}."
            if single_arm_rates else ""
        )
        add(f"- **Results (Qualitative & Single-Arm Synthesis):** Fewer than 2 extracted abstracts reported complete two-arm comparative event counts or means/SDs.{sa_note}")
        add(f"- **Conclusion:** In accordance with Cochrane Handbook standards against fabricating or imputing unreported control-arm counts from abstracts, a structured qualitative synthesis of all `{len(extracted_studies)}` included studies is presented in **Table 1** and **Section 5** below.")
        add("")

    # ======================================================================
    # SECTION 2: PICO PROTOCOL & SEARCH STRATEGY
    # ======================================================================
    add("## 2. PICO Protocol, Eligibility Criteria & Search Strategy")
    add("")
    if protocol:
        add("| PICOS Element | Specification |")
        add("| :--- | :--- |")
        add(f"| **Population (P)** | {_md_cell(protocol.get('population'))} |")
        add(f"| **Intervention (I)** | {_md_cell(protocol.get('intervention'))} |")
        add(f"| **Comparator (C)** | {_md_cell(protocol.get('comparator'))} |")
        add(f"| **Primary Outcome (O)** | {_md_cell(protocol.get('primary_outcome'))} |")
        if protocol.get("secondary_outcomes"):
            add(f"| **Secondary Outcomes** | {_md_cell('; '.join(protocol['secondary_outcomes']))} |")
        if protocol.get("study_designs"):
            add(f"| **Eligible Study Designs (S)** | {_md_cell(', '.join(protocol['study_designs']))} |")
        if protocol.get("inclusion_criteria"):
            add(f"| **Inclusion Criteria** | {_md_cell('; '.join(protocol['inclusion_criteria']), 400)} |")
        if protocol.get("exclusion_criteria"):
            add(f"| **Exclusion Criteria** | {_md_cell('; '.join(protocol['exclusion_criteria']), 400)} |")
        add("")

    if result.get("query"):
        add("**Canonical Boolean Search Strategy (PubMed / MEDLINE Syntax):**")
        add(f"```text\n{result['query']}\n```")
        add("")

    # ======================================================================
    # SECTION 3: COMPLETE PRISMA 2020 EVIDENCE FUNNEL & ACCOUNTING
    # ======================================================================
    add("## 3. Complete PRISMA 2020 Evidence Funnel & Record Accounting")
    add("")
    add("Every single record retrieved from the literature search is accounted for below:")
    add("")
    add("| Funnel Phase | Step / Database Source | Record Count | Notes & Accounting Proof |")
    add("| :--- | :--- | :---: | :--- |")

    per_src = search_info.get("per_source") or {}
    for src_name, src_info in per_src.items():
        status_str = src_info.get("status", "ok")
        cnt = src_info.get("count", 0)
        err_note = f" ({src_info['error']})" if src_info.get("error") else ""
        add(f"| **1. Identification** | Database: `{src_name}` | `{cnt}` | Status: `{status_str}`{err_note} |")

    tot_id = prisma.get("total_identified", search_info.get("total_identified", 0))
    dups_rem = prisma.get("duplicates_removed", search_info.get("duplicates_removed", 0))
    uniq_cnt = search_info.get("unique_records", max(0, tot_id - dups_rem))
    dedupe_rep = search_info.get("dedupe_report") or {}
    matched_by = dedupe_rep.get("matched_by") or {}
    match_breakdown = ", ".join(f"{k.upper()}: {v}" for k, v in matched_by.items() if v) or "DOI / PMID / NCT / Title+Year"

    add(f"| **1. Identification** | **Total Records Identified** | **`{tot_id}`** | Across all queried databases |")
    add(f"| **2. Deduplication** | Duplicates Removed | `-{dups_rem}` | Matched by: {match_breakdown} (see Table 4 below) |")
    add(f"| **2. Deduplication** | **Unique Records After Deduplication** | **`{uniq_cnt}`** | `{tot_id} - {dups_rem} = {uniq_cnt}` unique records |")

    n_scr = screening_info.get("screened", prisma.get("records_screened", 0))
    n_not_scr = screening_info.get("not_screened", max(0, uniq_cnt - n_scr))
    n_exc_scr = screening_info.get("excluded", prisma.get("excluded_at_screening", 0))
    n_inc_scr = screening_info.get("included", len(inc_records))
    gate_rej = screening_info.get("gate_rejected", 0)
    agree_rate = screening_info.get("reviewer_agreement_rate")
    agree_str = f"{agree_rate * 100:.1f}%" if agree_rate is not None else "N/A"

    if n_not_scr > 0:
        add(f"| **3. Screening** | Unscreened (Beyond Screening Cap) | `-{n_not_scr}` | Screening cap was set to `{n_scr}` records (`SRMA_MAX_ABSTRACTS_TO_SCREEN`) |")
    add(f"| **3. Screening** | **Records Screened (Title & Abstract)** | **`{n_scr}`** | Dual independent MedGemma reviewers (Agreement rate: `{agree_str}`) |")
    add(f"| **3. Screening** | Excluded at Title/Abstract Screening | `-{n_exc_scr}` | `{gate_rej}` by Python Relevance Gate + `{max(0, n_exc_scr - gate_rej)}` by Dual Reviewers (see Table 2) |")
    for reason_cat, r_cnt in (prisma.get("exclusion_reasons") or {}).items():
        add(f"| *↳ Exclusion Breakdown* | *{reason_cat}* | *`{r_cnt}`* | *PRISMA 2020 exclusion category* |")
    add(f"| **3. Screening** | **Studies Approved at Screening** | **`{n_inc_scr}`** | `{n_scr} screened - {n_exc_scr} excluded = {n_inc_scr} eligible studies` |")

    n_ext_att = extraction_info.get("attempted", len(extracted_studies))
    n_ext_skip = extraction_info.get("not_attempted", max(0, n_inc_scr - n_ext_att))
    if n_ext_skip > 0:
        add(f"| **4. Extraction / Full-Text** | Skipped Due to Extraction Cap | `-{n_ext_skip}` | Extraction cap (`max_studies_to_extract={n_ext_att}`) reached (see Table 3) |")
    add(f"| **4. Extraction / Full-Text** | **Studies Assessed for Data & RoB 2** | **`{n_ext_att}`** | Full structured extraction + 5-domain Cochrane RoB 2 assessment |")

    k_pooled = meta.get("k_included", 0) if meta.get("ok") else 0
    n_unpooled = max(0, len(extracted_studies) - k_pooled)
    if n_unpooled > 0:
        add(f"| **5. Synthesis** | Excluded from Statistical Pooling (Narrative Only) | `-{n_unpooled}` | Missing event counts / means in abstract or ongoing trial protocol (see Table 3) |")
    add(f"| **5. Synthesis** | **Final Studies Pooled in Meta-Analysis** | **`{k_pooled}`** | **`{meta.get('total_participants') or 0}` total participants analysed quantitatively** |")
    add("")

    # ======================================================================
    # SECTION 4: TABLE 1 - CHARACTERISTICS OF INCLUDED STUDIES
    # ======================================================================
    add("## 4. Table 1: Characteristics & Extracted Evidence of Included Studies")
    add("")
    add("This table documents every study that passed screening and underwent data extraction "
        "(modeled on publication tables in *Acta Oncologica* / Cochrane reviews). Click any **Study ID** "
        "to open and verify the original source record:")
    add("")
    add("| Ref | Study ID & Verification Link | Author (Year) & Title | Source & Design | Target Population | Intervention Arm (`Events / N` or `Mean ± SD`) | Comparator Arm (`Events / N` or `Mean ± SD`) | Study Effect `[95% CI]` & Weight | RoB 2 Overall | Status & Key Findings |")
    add("| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |")

    references: list[dict[str, str]] = []

    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        inc_meta = inc_by_id.get(sid, {})
        url = _infer_url(sid, str(ext.get("verification_url") or inc_meta.get("url") or ""))
        id_link = _format_id_link(sid, url)

        label = str(ext.get("study_label") or inc_meta.get("citation") or sid)
        title = str(ext.get("title") or inc_meta.get("title") or "(Title not stated)")
        source_db = str(ext.get("source_db") or inc_meta.get("source") or "Literature DB")
        design = str(ext.get("design") or "Clinical Study")
        pop_desc = str(ext.get("population_description") or protocol.get("population") or "Target cohort")

        int_arm = ext.get("intervention_arm") or {}
        ctrl_arm = ext.get("control_arm") or {}

        def _fmt_arm(arm: dict[str, Any], desc: str) -> str:
            lbl = arm.get("label") or desc or "Arm"
            n_tot = arm.get("n_total")
            n_ev = arm.get("n_events")
            mean_v = arm.get("mean")
            sd_v = arm.get("sd")
            if n_ev is not None and n_tot is not None:
                return f"**{_md_cell(lbl, 40)}**: `{n_ev} / {n_tot}` ({n_ev / n_tot * 100:.1f}%)" if n_tot > 0 else f"**{_md_cell(lbl, 40)}**: `{n_ev} / {n_tot}`"
            if mean_v is not None and sd_v is not None and n_tot is not None:
                return f"**{_md_cell(lbl, 40)}**: `{mean_v} ± {sd_v}` (`N={n_tot}`)"
            if n_tot is not None:
                return f"**{_md_cell(lbl, 40)}**: `N={n_tot}` *(events not reported)*"
            return f"**{_md_cell(lbl, 40)}**: *Not reported*"

        int_str = _fmt_arm(int_arm, str(ext.get("intervention_description") or ""))
        ctrl_str = _fmt_arm(ctrl_arm, str(ext.get("comparator_description") or ""))

        ps = pooled_by_key.get(sid) or pooled_by_key.get(label)
        if ps:
            eff_v = ps.get("effect_transformed", ps.get("effect"))
            cil_v = ps.get("ci_low_transformed", ps.get("ci_low"))
            cih_v = ps.get("ci_high_transformed", ps.get("ci_high"))
            wt_v = ps.get("weight_random_pct", ps.get("weight_fixed_pct", 0.0))
            eff_str = f"**`{eff_v:.2f}`** `[{cil_v:.2f}, {cih_v:.2f}]` (Wt: `{wt_v:.1f}%`)"
            status_badge = "**Pooled in Meta-Analysis**"
        else:
            ex_info = meta_exc_by_label.get(label) or {}
            ex_reason = ex_info.get("reason") or ", ".join(ext.get("missing_data_flags") or []) or "Missing arm event counts"
            eff_str = "*Not pooled (Narrative synthesis)*"
            status_badge = f"**Narrative Only** ({_md_cell(ex_reason, 90)})"

        rob_ov = str(ext.get("rob_overall") or "Some concerns")
        findings = str(ext.get("key_findings_summary") or ext.get("evidence_quote") or "")
        status_and_findings = f"{status_badge}. {_md_cell(findings, 140)}" if findings else status_badge

        add(f"| `[{idx}]` | {id_link} | **{_md_cell(label, 60)}** — {_md_cell(title, 120)} | "
            f"`{_md_cell(source_db, 35)}` ({_md_cell(design, 45)}) | {_md_cell(pop_desc, 80)} | "
            f"{int_str} | {ctrl_str} | {eff_str} | `{rob_ov}` | {status_and_findings} |")

        references.append({
            "ref_num": str(idx),
            "id": sid,
            "citation": label,
            "title": title,
            "source": source_db,
            "url": url,
            "role": "Included & Pooled" if ps else "Included (Narrative Synthesis)",
        })
    add("")

    # ======================================================================
    # SECTION 5: STUDY-BY-STUDY EVIDENCE PROOF & ROB 2 AUDIT
    # ======================================================================
    add("## 5. Study-by-Study Evidence Proof, Dual-Reviewer Justifications & RoB 2 Audit")
    add("")
    add("Below is the complete audit trail for each extracted study, including **why it passed screening**, "
        "**verbatim text quotes**, and **all 5 Cochrane RoB 2 domain judgements**:")
    add("")

    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        inc_meta = inc_by_id.get(sid, {})
        url = _infer_url(sid, str(ext.get("verification_url") or inc_meta.get("url") or ""))
        id_link = _format_id_link(sid, url)
        label = str(ext.get("study_label") or inc_meta.get("citation") or sid)
        title = str(ext.get("title") or inc_meta.get("title") or "(Title not stated)")
        source_db = str(ext.get("source_db") or inc_meta.get("source") or "Literature DB")

        add(f"### [{idx}] {label} — {id_link}")
        add(f"- **Full Title:** {title}")
        add(f"- **Source Database(s):** `{source_db}` | **Verification URL:** {url or 'N/A'}")
        if inc_meta:
            add(f"- **Screening Reviewer 1 (Recall-Oriented) Proof:** {_md_cell(inc_meta.get('reviewer_1_reason'), 400)}")
            add(f"- **Screening Reviewer 2 (Precision-Oriented) Proof:** {_md_cell(inc_meta.get('reviewer_2_reason'), 400)}")
            add(f"- **Screening Consensus Decision:** `{_md_cell(inc_meta.get('decided_by'), 350)}`")
        if ext.get("key_findings_summary"):
            add(f"- **Extracted Clinical Summary:** {ext['key_findings_summary']}")
        if ext.get("evidence_quote"):
            add(f"- **Verbatim Evidence Quote from Text:** *\"{ext['evidence_quote']}\"*")
        if ext.get("missing_data_flags"):
            add(f"- **Data Completeness / Verifier Flags:** `{', '.join(ext['missing_data_flags'])}`")

        rob_domains = ext.get("rob_domains") or []
        if rob_domains:
            add("")
            add("| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |")
            add("| :--- | :---: | :--- |")
            for rd in rob_domains:
                add(f"| {_md_cell(rd.get('domain'), 80)} | **`{_md_cell(rd.get('judgement'), 25)}`** | "
                    f"{_md_cell(rd.get('justification'), 280)} |")
        add("")

    # ======================================================================
    # SECTION 6: TABLE 2 - EXCLUDED STUDIES AT SCREENING (WITH EXACT REASONS)
    # ======================================================================
    add("## 6. Table 2: Excluded Articles at Title/Abstract Screening (Full Audit Log)")
    add("")
    if exc_records:
        add(f"All **`{len(exc_records)}` articles excluded at screening** are listed below with their "
            "identifier, clickable verification link, PRISMA category, decision source, and exact reason:")
        add("")
        add("| # | Article ID & Link | Title | Source DB | PRISMA Exclusion Category | Decided By | Exact Proof / Reason for Exclusion |")
        add("| :---: | :--- | :--- | :--- | :--- | :--- | :--- |")
        for i, ex in enumerate(exc_records, 1):
            ex_id = str(ex.get("id") or f"Ex-{i}")
            ex_url = _infer_url(ex_id, str(ex.get("url") or ""))
            ex_link = _format_id_link(ex_id, ex_url)
            ex_title = _md_cell(ex.get("title") or "(No title)", 140)
            ex_src = _md_cell(ex.get("source") or "Database", 35)
            ex_cat = _md_cell(ex.get("category") or "Excluded", 35)
            ex_by = _md_cell(ex.get("decided_by") or "Screening", 55)
            r1 = ex.get("reviewer_1_reason") or ""
            r2 = ex.get("reviewer_2_reason") or ex.get("reason") or ""
            if "relevance gate" in str(ex.get("decided_by") or "").lower():
                reason_full = _md_cell(ex.get("reason"), 280)
            elif r1 and r2 and r1 != r2:
                reason_full = f"**R1:** {_md_cell(r1, 140)} <br> **R2:** {_md_cell(r2, 140)}"
            else:
                reason_full = _md_cell(r2 or r1, 280)

            add(f"| `{i}` | {ex_link} | {ex_title} | `{ex_src}` | **`{ex_cat}`** | {ex_by} | {reason_full} |")
            references.append({
                "ref_num": f"E{i}",
                "id": ex_id,
                "citation": str(ex.get("citation") or ex_id),
                "title": str(ex.get("title") or ""),
                "source": str(ex.get("source") or ""),
                "url": ex_url,
                "role": f"Excluded at Screening ({ex.get('category', 'Excluded')})",
            })
        add("")
    else:
        add("*No articles were excluded during title/abstract screening.*")
        add("")

    # ======================================================================
    # SECTION 7: TABLE 3 - APPROVED AT SCREENING BUT NOT POOLED
    # ======================================================================
    skipped_cap = extraction_info.get("skipped_due_to_cap") or []
    if not skipped_cap and len(inc_records) > len(extracted_studies):
        for r in inc_records:
            rid = str(r.get("id") or "")
            if rid and rid not in ext_by_id:
                skipped_cap.append({
                    "id": rid,
                    "title": r.get("title") or "",
                    "source": r.get("source") or "",
                    "url": _infer_url(rid, str(r.get("url") or "")),
                    "reason": (
                        f"Passed dual-reviewer screening, but skipped at Phase 6 "
                        f"because max_studies_to_extract={len(extracted_studies)} cap was reached."
                    ),
                })

    unpooled_rows: list[dict[str, str]] = []
    for ex_st in meta_excluded:
        lbl = str(ex_st.get("label") or "")
        matched_ext = None
        for ext in extracted_studies:
            if str(ext.get("study_label")) == lbl or str(ext.get("study_id")) in lbl:
                matched_ext = ext
                break
        sid = str((matched_ext.get("study_id") if matched_ext else None) or lbl)
        raw_url = (matched_ext.get("verification_url") if matched_ext else None) or inc_by_id.get(sid, {}).get("url") or ""
        url = _infer_url(sid, str(raw_url))
        title = str(
            (matched_ext.get("title") if matched_ext else None)
            or inc_by_id.get(sid, {}).get("title")
            or lbl
        )
        flags = ", ".join((matched_ext.get("missing_data_flags") or []) if matched_ext else [])
        reason_detail = f"{ex_st.get('reason_code', 'MISSING_DATA')}: {ex_st.get('reason', '')}"
        if flags:
            reason_detail += f" (Flags: {flags})"
        unpooled_rows.append({
            "id": sid,
            "url": url,
            "title": title,
            "stage": "Phase 7 (Meta-Analysis Pooling)",
            "reason": reason_detail,
        })

    for sk in skipped_cap:
        sid = str(sk.get("id") or "")
        url = _infer_url(sid, str(sk.get("url") or ""))
        unpooled_rows.append({
            "id": sid,
            "url": url,
            "title": str(sk.get("title") or ""),
            "stage": "Phase 6 (Data Extraction Cap)",
            "reason": str(sk.get("reason") or "Skipped due to extraction cap"),
        })

    add("## 7. Table 3: Studies Approved at Screening but Excluded from Quantitative Pooling")
    add("")
    if unpooled_rows:
        add("These studies passed title/abstract screening (`Include`), and the table below explains "
            "why they were not included in the final statistical meta-analysis pool:")
        add("")
        add("| # | Study ID & Link | Title | Pipeline Stage | Exact Reason Not Pooled |")
        add("| :---: | :--- | :--- | :--- | :--- |")
        for i, row in enumerate(unpooled_rows, 1):
            add(f"| `{i}` | {_format_id_link(row['id'], row['url'])} | {_md_cell(row['title'], 140)} | "
                f"`{row['stage']}` | {_md_cell(row['reason'], 240)} |")
        add("")
    else:
        add("*Every study approved at screening was extracted and pooled in the quantitative meta-analysis.*")
        add("")

    # ======================================================================
    # SECTION 8: TABLE 4 - DEDUPLICATION AUDIT LOG
    # ======================================================================
    add("## 8. Table 4: Deduplication Audit Log (Removed Duplicate Records)")
    add("")
    rem_dups = dedupe_rep.get("removed_duplicates") or []
    if rem_dups:
        add(f"A total of **`{len(rem_dups)}` duplicate records** were identified across databases and merged into a single canonical study record before screening:")
        add("")
        add("| # | Removed Duplicate ID & Link | Duplicate Source DB | Merged Into Primary Study ID | Matched By | Article Title |")
        add("| :---: | :--- | :--- | :--- | :---: | :--- |")
        for i, d in enumerate(rem_dups[:50], 1):
            dup_id = str(d.get("duplicate_id") or "")
            dup_url = _infer_url(dup_id, str(d.get("url") or ""))
            prim_id = str(d.get("merged_into_id") or "")
            prim_url = _infer_url(prim_id, "")
            add(f"| `{i}` | {_format_id_link(dup_id, dup_url)} | `{_md_cell(d.get('duplicate_source'), 30)}` | "
                f"{_format_id_link(prim_id, prim_url)} | `{d.get('matched_on', 'id')}` | {_md_cell(d.get('title'), 120)} |")
        if len(rem_dups) > 50:
            add(f"\n*... plus `{len(rem_dups) - 50}` additional duplicates (all recorded in `result.json`).*")
        add("")
    else:
        add(f"*Total duplicates removed across databases: `{dups_rem}`.*")
        add("")

    # ======================================================================
    # SECTION 9: STATISTICAL META-ANALYSIS, SENSITIVITY & GRADE TABLE
    # ======================================================================
    add("## 9. Statistical Meta-Analysis, Sensitivity Analysis & GRADE Evidence Profile")
    add("")
    if meta.get("ok"):
        models_dict = meta.get("models") or {}
        if models_dict:
            add("### 9.1 Statistical Pooling Across Estimator Models")
            add("")
            add("| Statistical Model | τ² Estimator | Pooled Estimate | 95% Confidence Interval | p-value | Studies (`k`) |")
            add("| :--- | :---: | :---: | :---: | :---: | :---: |")
            for m_key, m_val in models_dict.items():
                est_v = m_val.get("estimate_transformed")
                cil_v = m_val.get("ci_low_transformed")
                cih_v = m_val.get("ci_high_transformed")
                pv = m_val.get("p_value")
                pv_str = f"`{pv:.4g}`" if pv is not None else "`N/A`"
                est_str = f"**`{est_v:.3f}`**" if est_v is not None else "`N/A`"
                ci_str = f"`[{cil_v:.3f}, {cih_v:.3f}]`" if (cil_v is not None and cih_v is not None) else "`N/A`"
                add(f"| `{m_key}` | `{m_val.get('tau2_method') or 'Fixed'}` | {est_str} | {ci_str} | {pv_str} | `{m_val.get('k', 0)}` |")
            add("")

        loo = meta.get("leave_one_out") or []
        if loo:
            add("### 9.2 Leave-One-Out Sensitivity Analysis")
            add("")
            add("Tests whether removing any single study changes the overall statistical conclusion:")
            add("")
            add("| Omitted Study | Remaining Studies (`k`) | Recalculated Pooled Estimate | 95% CI | p-value | Heterogeneity (`I²`) |")
            add("| :--- | :---: | :---: | :---: | :---: | :---: |")
            for row in loo:
                om = _md_cell(row.get("omitted_study"), 70)
                rem_k = row.get("k_remaining", 0)
                est_v = row.get("estimate_transformed")
                cil_v = row.get("ci_low_transformed")
                cih_v = row.get("ci_high_transformed")
                pv = row.get("p_value")
                i2_v = row.get("I2")
                add(f"| {om} | `{rem_k}` | **`{est_v:.3f}`** | `[{cil_v:.3f}, {cih_v:.3f}]` | "
                    f"`{pv:.4g}` | `{i2_v:.1f}%` |")
            add("")

    if grade:
        add("### 9.3 GRADE Certainty of Evidence Profile")
        add("")
        add(f"- **Starting Certainty:** `{grade.get('starting_rating', 'High')}` | "
            f"**Final Certainty Rating:** **`{grade.get('final_rating', 'Not rated')}`**")
        add("")
        add("| GRADE Domain | Judgement | Downgrade Levels | Methodological Rationale |")
        add("| :--- | :---: | :---: | :--- |")
        for dom in ("risk_of_bias", "inconsistency", "indirectness", "imprecision", "publication_bias"):
            d_obj = grade.get(dom) or {}
            add(f"| **{dom.replace('_', ' ').title()}** | `{_md_cell(d_obj.get('judgement'), 30)}` | "
                f"`-{d_obj.get('downgrade_levels', 0)}` | {_md_cell(d_obj.get('rationale'), 240)} |")
        add("")
        if grade.get("summary"):
            add(f"**GRADE Evidence Summary:** {grade['summary']}")
            add("")

    try:
        from .tools import pdf_report
        r_script_text = pdf_report.generate_r_script(result)
        add("### 9.4 Reproducible R Verification Script (`meta` / `metafor`)")
        add("")
        add(f"```r\n{r_script_text}\n```")
        add("")
    except Exception:  # noqa: BLE001
        pass

    # ======================================================================
    # SECTION 10: COMPLETE NUMBERED BIBLIOGRAPHY & VERIFICATION LINKS
    # ======================================================================
    add("## 10. Complete Bibliography & Direct Verification Links")
    add("")
    if references:
        for ref in references:
            r_url = ref.get("url") or ""
            url_md = f" — [Verify Source]({r_url}) (`{r_url}`)" if r_url else ""
            add(f"- **[{ref['ref_num']}]** **{ref['citation']}** *{ref['title']}* "
                f"[Source: `{ref['source']}` | Status: `{ref['role']}`]{url_md}")
        add("")

    if plots or result.get("pdf_report"):
        add("## 11. Generated Manuscript & Visual Figures")
        add("")
        if result.get("pdf_report"):
            add(f"- **Publication Manuscript (PDF):** `{result['pdf_report']}`")
        for name, path in plots.items():
            add(f"- **{name.title()} Plot:** `{path}`")
        add("")

    if result.get("errors"):
        add("## 12. Pipeline Warnings & Notes")
        add("")
        for err in result["errors"]:
            add(f"- {err}")
        add("")

    add("---")
    add("*Disclaimer: This report was generated by the SRMA Agent for clinical research synthesis "
        "and decision support. Every statistical value was computed deterministically in Python "
        "(NumPy/SciPy) from extracted study data. Verify primary clinical records via the links above "
        "before clinical or regulatory use.*")
    return "\n".join(lines)


def render_summary(result: dict[str, Any]) -> str:
    """A detailed plain-text report with full study-level transparency."""
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("SYSTEMATIC REVIEW AND META-ANALYSIS (FULL TRANSPARENCY REPORT)")
    add("=" * 78)
    add(f"Question : {result.get('question', '')}")
    add(f"Run      : {result.get('run_id')}  ({result.get('generated_utc')})")
    add(f"Elapsed  : {result.get('elapsed_seconds')}s")
    add("")

    protocol = result.get("protocol") or {}
    prisma = result.get("prisma") or {}
    search_info = result.get("search") or {}
    screening_info = result.get("screening") or {}
    extraction_info = result.get("extraction") or {}
    meta = result.get("meta_analysis") or {}
    grade = result.get("grade") or {}

    inc_records = screening_info.get("included_records") or []
    inc_by_id = {str(r.get("id")): r for r in inc_records if r.get("id")}
    extracted_studies = extraction_info.get("studies") or []
    ext_by_id = {str(s.get("study_id")): s for s in extracted_studies if s.get("study_id")}
    pooled_studies = meta.get("studies") or []
    pooled_by_key: dict[str, dict[str, Any]] = {}
    for ps in pooled_studies:
        lbl = str(ps.get("label") or "")
        pooled_by_key[lbl] = ps
        for ext in extracted_studies:
            sid = str(ext.get("study_id") or "")
            if sid and (sid in lbl or lbl == str(ext.get("study_label") or "")):
                pooled_by_key[sid] = ps

    total_int_ev = 0
    total_int_n = 0
    total_ctrl_ev = 0
    total_ctrl_n = 0
    pooled_id_list: list[str] = []
    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        label = str(ext.get("study_label") or sid)
        ps = pooled_by_key.get(sid) or pooled_by_key.get(label)
        if ps:
            pooled_id_list.append(f"[{idx}] {sid}")
            ia = ext.get("intervention_arm") or {}
            ca = ext.get("control_arm") or {}
            if ia.get("n_events") is not None and ia.get("n_total") is not None:
                total_int_ev += int(ia["n_events"])
                total_int_n += int(ia["n_total"])
            if ca.get("n_events") is not None and ca.get("n_total") is not None:
                total_ctrl_ev += int(ca["n_events"])
                total_ctrl_n += int(ca["n_total"])

    # ----------------------------------------------------------------------
    # SECTION 1: STRUCTURED CLINICAL ABSTRACT & EXECUTIVE SYNTHESIS
    # ----------------------------------------------------------------------
    add("-" * 78)
    add("1. STRUCTURED CLINICAL ABSTRACT & EXECUTIVE SYNTHESIS")
    add("-" * 78)
    pop_simple = protocol.get("population") or "the target clinical cohort"
    int_simple = protocol.get("intervention") or "the target intervention"
    cmp_simple = protocol.get("comparator") or "the control regimen"
    out_simple = protocol.get("primary_outcome") or "the primary clinical outcome"

    add(f"  Comparison      : [{int_simple}] vs. [{cmp_simple}]")
    add(f"  Target Cohort   : {pop_simple}")
    add(f"  Primary Endpoint: {out_simple}")
    add("")
    if meta.get("ok"):
        pooled = meta["pooled"]
        eff_label = meta.get("effect_measure_label", "Effect Estimate")
        est = pooled.get("estimate_transformed")
        ci_l = pooled.get("ci_low_transformed")
        ci_h = pooled.get("ci_high_transformed")
        pval = pooled.get("p_value")
        k_inc = meta.get("k_included", 0)
        n_part = meta.get("total_participants") or "unknown"
        add(f"  Pooled Synthesis: {eff_label} = {est:.3f} (95% CI {ci_l:.3f} to {ci_h:.3f}, p = {pval:.4g})")
        add(f"  Evidence Cohort : {k_inc} pooled studies ({n_part} total participants)")
        if total_int_n > 0 and total_ctrl_n > 0:
            add(f"  Intervention Arm: {total_int_ev} / {total_int_n} events ({total_int_ev / total_int_n * 100:.1f}%)")
            add(f"  Comparator Arm  : {total_ctrl_ev} / {total_ctrl_n} events ({total_ctrl_ev / total_ctrl_n * 100:.1f}%)")
        add(f"  GRADE Certainty : {grade.get('final_rating', 'Not rated')} - {grade.get('summary', '')}")
        if pooled_id_list:
            add(f"  Pooled Study IDs: {', '.join(pooled_id_list)} (see Section 5 below)")
    else:
        add("  Synthesis Status: Quantitative two-arm pooling was not executed because fewer than 2")
        add("                    extracted abstracts reported complete comparative arm counts. See Section 5")
        add("                    below for the structured qualitative and single-arm study synthesis.")
    add("")

    if protocol:
        add("-" * 78)
        add("2. PROTOCOL (PICO)")
        add("-" * 78)
        add(f"  Population   : {protocol.get('population')}")
        add(f"  Intervention : {protocol.get('intervention')}")
        add(f"  Comparator   : {protocol.get('comparator')}")
        add(f"  Outcome      : {protocol.get('primary_outcome')}")
        add("")

    if result.get("query"):
        add("-" * 78)
        add("3. SEARCH STRATEGY")
        add("-" * 78)
        add(f"  {result['query']}")
        add("")

    if prisma:
        add("-" * 78)
        add("4. PRISMA 2020 FLOW & RECORD ACCOUNTING")
        add("-" * 78)
        for name, count in (prisma.get("identified_by_source") or {}).items():
            add(f"  {name:.<32} {count}")
        tot_id = prisma.get("total_identified", 0)
        dups = prisma.get("duplicates_removed", 0)
        uniq = max(0, tot_id - dups)
        scr = prisma.get("records_screened", 0)
        not_scr = screening_info.get("not_screened", max(0, uniq - scr))
        exc_scr = prisma.get("excluded_at_screening", 0)
        inc_scr = screening_info.get("included", max(0, scr - exc_scr))
        ext_att = extraction_info.get("attempted", prisma.get("full_text_assessed", 0))
        ext_skip = extraction_info.get("not_attempted", max(0, inc_scr - ext_att))
        k_inc = prisma.get("studies_included", 0)
        unpooled_cnt = max(0, ext_att - k_inc)

        add(f"  {'TOTAL IDENTIFIED':.<32} {tot_id}")
        add(f"  {'duplicates removed':.<32} -{dups}")
        add(f"  {'unique records after dedup':.<32} {uniq}")
        if not_scr > 0:
            add(f"  {'unscreened (screening cap)':.<32} -{not_scr}")
        add(f"  {'records screened':.<32} {scr}")
        add(f"  {'excluded at screening':.<32} -{exc_scr}")
        for reason, count in (prisma.get("exclusion_reasons") or {}).items():
            add(f"      {reason:.<28} {count}")
        add(f"  {'approved at screening':.<32} {inc_scr}")
        if ext_skip > 0:
            add(f"  {'skipped (extraction cap)':.<32} -{ext_skip}")
        add(f"  {'studies extracted (Phase 6)':.<32} {ext_att}")
        if unpooled_cnt > 0:
            add(f"  {'narrative only (missing counts)':.<32} -{unpooled_cnt}")
        add(f"  {'FINAL STUDIES POOLED':.<32} {k_inc}")
        add("")

    if extracted_studies:
        add("-" * 78)
        add(f"5. INCLUDED & EXTRACTED STUDIES ({len(extracted_studies)} STUDIES)")
        add("-" * 78)
        for idx, ext in enumerate(extracted_studies, 1):
            sid = str(ext.get("study_id") or f"Study-{idx}")
            inc_meta = inc_by_id.get(sid, {})
            url = _infer_url(sid, str(ext.get("verification_url") or inc_meta.get("url") or ""))
            label = str(ext.get("study_label") or inc_meta.get("citation") or sid)
            title = str(ext.get("title") or inc_meta.get("title") or "(Title not stated)")
            source_db = str(ext.get("source_db") or inc_meta.get("source") or "Database")
            int_arm = ext.get("intervention_arm") or {}
            ctrl_arm = ext.get("control_arm") or {}
            ps = pooled_by_key.get(sid) or pooled_by_key.get(label)

            add(f"  [{idx}] ID: {sid}  |  Citation: {label}")
            add(f"      Title     : {title}")
            add(f"      Source DB : {source_db}  |  Verify: {url or 'N/A'}")
            add(f"      Intervent.: {int_arm.get('label', 'Intervention')} "
                f"(events={int_arm.get('n_events')}, N={int_arm.get('n_total')}, "
                f"mean={int_arm.get('mean')}, sd={int_arm.get('sd')})")
            add(f"      Control   : {ctrl_arm.get('label', 'Control')} "
                f"(events={ctrl_arm.get('n_events')}, N={ctrl_arm.get('n_total')}, "
                f"mean={ctrl_arm.get('mean')}, sd={ctrl_arm.get('sd')})")
            if ps:
                eff_v = ps.get("effect_transformed", ps.get("effect"))
                cil_v = ps.get("ci_low_transformed", ps.get("ci_low"))
                cih_v = ps.get("ci_high_transformed", ps.get("ci_high"))
                wt_v = ps.get("weight_random_pct", 0.0)
                add(f"      Pooling   : POOLED -> Effect = {eff_v:.3f} "
                    f"(95% CI {cil_v:.3f} to {cih_v:.3f}), Weight = {wt_v:.1f}%")
            else:
                flags = ", ".join(ext.get("missing_data_flags") or []) or "Missing arm event counts"
                add(f"      Pooling   : NOT POOLED (Narrative Only) -> Reason: {flags}")
            add(f"      RoB 2     : {ext.get('rob_overall') or 'Not rated'}")
            if inc_meta.get("decided_by"):
                add(f"      Inclusion : {inc_meta.get('decided_by')}")
            if ext.get("key_findings_summary"):
                add(f"      Findings  : {ext.get('key_findings_summary')}")
            add("")

    exc_records = screening_info.get("excluded_records") or []
    if exc_records:
        add("-" * 78)
        add(f"6. EXCLUDED ARTICLES AT SCREENING ({len(exc_records)} ARTICLES WITH REASONS)")
        add("-" * 78)
        for idx, ex in enumerate(exc_records, 1):
            ex_id = str(ex.get("id") or f"Ex-{idx}")
            ex_url = _infer_url(ex_id, str(ex.get("url") or ""))
            add(f"  [{idx}] ID: {ex_id}  |  Category: {ex.get('category')}  |  Verify: {ex_url or 'N/A'}")
            add(f"      Title      : {ex.get('title')}")
            add(f"      Decided By : {ex.get('decided_by')}")
            add(f"      Reason     : {ex.get('reason')}")
            add("")

    # Approved at screening but not pooled
    skipped_cap = extraction_info.get("skipped_due_to_cap") or []
    if not skipped_cap and len(inc_records) > len(extracted_studies):
        for r in inc_records:
            rid = str(r.get("id") or "")
            if rid and rid not in ext_by_id:
                skipped_cap.append({
                    "id": rid,
                    "title": r.get("title") or "",
                    "url": _infer_url(rid, str(r.get("url") or "")),
                    "reason": f"Passed screening, but skipped at Phase 6 because max_studies_to_extract={len(extracted_studies)} cap was reached.",
                })
    meta_excluded = meta.get("excluded_studies") or []
    if meta_excluded or skipped_cap:
        add("-" * 78)
        add("7. APPROVED AT SCREENING BUT NOT POOLED IN META-ANALYSIS")
        add("-" * 78)
        u_idx = 1
        for ex_st in meta_excluded:
            lbl = str(ex_st.get("label") or "")
            matched_ext = next(
                (e for e in extracted_studies if str(e.get("study_label")) == lbl or str(e.get("study_id")) in lbl),
                None,
            )
            sid = str((matched_ext.get("study_id") if matched_ext else None) or lbl)
            raw_url = (matched_ext.get("verification_url") if matched_ext else None) or inc_by_id.get(sid, {}).get("url") or ""
            url = _infer_url(sid, str(raw_url))
            title = str(
                (matched_ext.get("title") if matched_ext else None)
                or inc_by_id.get(sid, {}).get("title")
                or lbl
            )
            add(f"  [{u_idx}] ID: {sid}  |  Stage: Phase 7 (Pooling)  |  Verify: {url or 'N/A'}")
            add(f"      Title  : {title}")
            add(f"      Reason : {ex_st.get('reason_code', 'MISSING_DATA')}: {ex_st.get('reason', '')}")
            add("")
            u_idx += 1
        for sk in skipped_cap:
            sid = str(sk.get("id") or "")
            url = _infer_url(sid, str(sk.get("url") or ""))
            add(f"  [{u_idx}] ID: {sid}  |  Stage: Phase 6 (Extraction Cap)  |  Verify: {url or 'N/A'}")
            add(f"      Title  : {sk.get('title')}")
            add(f"      Reason : {sk.get('reason')}")
            add("")
            u_idx += 1

    dedupe_rep = search_info.get("dedupe_report") or {}
    rem_dups = dedupe_rep.get("removed_duplicates") or []
    if rem_dups:
        add("-" * 78)
        add(f"8. DEDUPLICATION AUDIT LOG ({len(rem_dups)} DUPLICATES REMOVED)")
        add("-" * 78)
        for idx, d in enumerate(rem_dups[:50], 1):
            dup_id = str(d.get("duplicate_id") or "")
            dup_url = _infer_url(dup_id, str(d.get("url") or ""))
            add(f"  [{idx}] Duplicate ID: {dup_id} ({d.get('duplicate_source')}) -> Merged Into: {d.get('merged_into_id')} [Matched on: {d.get('matched_on')}]")
            add(f"      Title  : {d.get('title')}")
            if dup_url:
                add(f"      Verify : {dup_url}")
        add("")

    if meta.get("ok"):
        pooled = meta["pooled"]
        het = meta["heterogeneity"]
        add("-" * 78)
        add("9. META-ANALYSIS RESULTS")
        add("-" * 78)
        add(f"  Effect measure : {meta['effect_measure_label']}")
        add(f"  Pooled estimate: {pooled['estimate_transformed']:.3f} "
            f"(95% CI {pooled['ci_low_transformed']:.3f} to "
            f"{pooled['ci_high_transformed']:.3f})")
        add(f"  p-value        : {pooled['p_value']:.4g}")
        add(f"  Studies pooled : {meta['k_included']}"
            f"   Participants: {meta.get('total_participants') or 'unknown'}")
        i2 = het.get("I2")
        add(f"  Heterogeneity  : I2 = {i2:.1f}%  tau2 = {het.get('tau2'):.4f}  "
            f"Q = {het.get('Q'):.2f} (p = {het.get('p_value'):.4g})"
            if i2 is not None else "  Heterogeneity  : not estimable")
        add("")
        for flag in meta.get("flags", []):
            add(f"  [{flag['severity'].upper()}] {flag['message']}")
        if meta.get("flags"):
            add("")

    if grade:
        add("-" * 78)
        add("10. CERTAINTY OF EVIDENCE (GRADE)")
        add("-" * 78)
        add(f"  Overall rating : {grade.get('final_rating')}")
        for domain in ("risk_of_bias", "inconsistency", "indirectness",
                       "imprecision", "publication_bias"):
            d = grade.get(domain) or {}
            add(f"    {domain.replace('_', ' '):<18} {d.get('judgement', '?')}"
                f"  (-{d.get('downgrade_levels', 0)})  |  {d.get('rationale', '')}")
        add(f"  Summary: {grade.get('summary', '')}")
        for note in grade.get("verification_notes", []):
            add(f"  NOTE: {note}")
        add("")

    plots = result.get("plots") or {}
    if plots:
        add("-" * 78)
        add("11. FIGURES & FULL MARKDOWN REPORT")
        add("-" * 78)
        for name, path in plots.items():
            add(f"  {name:<12} {path}")
        if result.get("run_dir"):
            add(f"  {'report.md':<12} {Path(result['run_dir']) / 'report.md'}")
        add("")

    if result.get("errors"):
        add("-" * 78)
        add("ISSUES ENCOUNTERED")
        add("-" * 78)
        for err in result["errors"]:
            add(f"  - {err}")
        add("")

    add("-" * 78)
    add("This is a research tool that supports expert reviewers. It does not")
    add("replace them, and its output is not clinical advice. Every number")
    add("above was computed in Python from extracted data; verify against the")
    add("source records in result.json and report.md before citing.")
    add("-" * 78)
    return "\n".join(lines)

