"""Dual-reviewer title and abstract screening.

WHY THIS MODULE EXISTS SEPARATELY FROM THE AGENT

Screening hundreds of abstracts with an identical prompt is a loop, not a
conversation. Running it as a plain Python loop rather than as agent turns
makes it testable, resumable, and cheap to reason about.

WHY TWO CALLS RATHER THAN ONE

The first implementation asked the model in a single call to "act as two
independent reviewers". On MedGemma 4B the two reviewers returned
byte-identical reasoning: the second was copying the first, so the
agreement rate was meaninglessly perfect and the safeguard was decorative.

Here each reviewer is a separate call with a different system prompt, and
neither sees the other's answer. They can therefore genuinely disagree.

WHY CONSENSUS IS COMPUTED IN PYTHON

Asking a model to adjudicate its own disagreement reintroduces exactly the
correlation we just removed. Eligibility is decided by two fixed rules
applied in order:

    1. RELEVANCE GATE (deterministic, no model call)
       The record must literally mention the population and the intervention
       somewhere in its title, abstract, MeSH headings or keywords.
       Fails -> Exclude, and no reviewer is ever consulted.

    2. LIBERAL CONSENSUS (among records that pass the gate)
       either reviewer says Include  ->  Include

THE ORDER IS THE WHOLE DESIGN, AND IT WAS ARRIVED AT BY MEASUREMENT.

Rule 2 alone is Cochrane's "liberal accelerated" convention. It exists
because the two errors are not symmetric: wrongly excluding an eligible
trial is invisible and permanent, while wrongly including one is caught at
full text and costs a few minutes. On its own, with a 4B model, it failed
badly. A run on an aspirin-after-myocardial-infarction question screened 6
records, included 6 and excluded 0, admitting "Canadian Consensus Conference
on Diagnosis and Treatment of Dementia" into a cardiology review.

The obvious correction - require both reviewers to agree - was tried and is
worse. It loses ISIS-2, the 17,187-patient aspirin trial that is the single
most important study such a review could find. The strict reviewer rejects
it as "Wrong intervention" because the abstract mentions streptokinase as
well as aspirin, missing that a 2x2 factorial design makes the aspirin
comparison valid. The objection reads as methodologically literate and is
simply wrong, and unanimity cannot distinguish that from a correct one.

So the two failures have different causes and need different remedies. Junk
records fail on subject matter, which is a factual question Python can settle
and no amount of prompting can be argued out of. Eligibility is a judgement,
and there the asymmetry of errors still holds, so the permissive reviewer
gets the benefit of the doubt. Disagreements are counted and recorded either
way.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import config, llm, prompts
from .schemas import (
    DualScreenResult,
    ReviewerVote,
    ScreeningDecision,
    StudyRecord,
)

# The exact strings the PRISMA flow diagram is allowed to contain. A model
# that invents "Not relevant" would produce a diagram whose exclusion
# reasons do not sum to anything meaningful.
VALID_EXCLUSION_CATEGORIES = (
    "Wrong population",
    "Wrong intervention",
    "Wrong comparator",
    "Wrong outcome",
    "Wrong study design",
    "Not human research",
    "Not primary research",
)

_UNCATEGORISED = "Uncategorised exclusion"

# Keywords that map a free-text reason onto a PRISMA category when the model
# supplies a category that is not on the list. Ordered: the first match wins,
# so the more specific patterns come first.
_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Not human research", ("animal", "mice", "mouse", "rat", "in vitro",
                            "in-vitro", "preclinical", "cell line")),
    ("Not primary research", ("review", "editorial", "commentary", "letter",
                              "meta-analysis", "case report", "protocol",
                              "guideline")),
    ("Wrong study design", ("observational", "cohort", "cross-sectional",
                            "retrospective", "single-arm", "single arm",
                            "not randomis", "not randomiz", "registry")),
    ("Wrong population", ("population", "participants", "patients", "enrol",
                          "enroll", "healthy", "children", "paediatric",
                          "pediatric", "age")),
    ("Wrong intervention", ("intervention", "drug", "dose", "treatment",
                            "therapy", "agent")),
    ("Wrong comparator", ("comparator", "control group", "placebo",
                          "comparison")),
    ("Wrong outcome", ("outcome", "endpoint", "measure")),
)


def _normalise_category(category: str, reason: str) -> str:
    """Coerce a model-supplied exclusion category onto the PRISMA list.

    Testing showed the model will give a population-based reason and then
    tag it "Wrong intervention". An incoherent category silently corrupts
    the flow diagram, so the reason text is treated as more trustworthy
    than the label and is used to re-derive it.
    """
    category = (category or "").strip()
    for valid in VALID_EXCLUSION_CATEGORIES:
        if category.lower() == valid.lower():
            return valid

    haystack = f"{category} {reason}".lower()
    for valid, keywords in _CATEGORY_HINTS:
        if any(word in haystack for word in keywords):
            return valid
    return _UNCATEGORISED


def _format_record(record: StudyRecord) -> str:
    """Render a record as the text the reviewer actually judges.

    Only the title and abstract are shown. Journal name and author list are
    deliberately withheld: they invite prestige bias, and a screening
    decision must rest on eligibility, not on where the work was published.
    """
    parts = [f"TITLE: {record.title or '(no title supplied)'}"]
    if record.publication_types:
        parts.append(f"PUBLICATION TYPE: {', '.join(record.publication_types)}")
    abstract = record.abstract.strip() if record.abstract else ""
    parts.append(f"\nABSTRACT: {abstract or '(no abstract available)'}")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Relevance gate
# --------------------------------------------------------------------------


def _term_pattern(term: str) -> "re.Pattern[str] | None":
    """Word-boundary matcher for one term, tolerant of spelling variation.

    Boundaries matter more than they look. A plain substring search for the
    abbreviation "ASA" also matches "disaster", "assay" and every author
    named Asare, which would wave through exactly the irrelevant records this
    gate exists to stop.

    The trailing \\w{0,3} is a cheap stand-in for stemming, so "infarction"
    also matches "infarctions" without pulling in a real stemmer.
    """
    words = [re.escape(w) for w in str(term or "").split() if w]
    if not words:
        return None
    # Papers write both "post-MI" and "post MI", so treat hyphen as space.
    return re.compile(r"\b" + r"[\s-]+".join(words) + r"\w{0,3}\b",
                      re.IGNORECASE)


def _mentions_any(haystack: str, terms: list[str]) -> str | None:
    """Return the first term found in the text, or None."""
    for term in terms:
        pattern = _term_pattern(term)
        if pattern and pattern.search(haystack):
            return term
    return None


def relevance_gate(
    record: StudyRecord,
    population_terms: list[str],
    intervention_terms: list[str],
) -> tuple[bool, str]:
    """Cheap deterministic check that a record is about the right subject.

    Runs before any model call. Searches title, abstract, MeSH headings and
    keywords. The MeSH headings matter: an indexer may have tagged
    "Myocardial Infarction" on a paper whose abstract only says "heart
    attack".

    Records with an abstract must mention BOTH concepts, mirroring the AND in
    the search strategy. Records with a title only need mention just one,
    because a title is a few words long and demanding both would discard
    legitimate trials that happen to be indexed without an abstract.

    Returns:
        (passed, reason). `reason` is empty when the record passes.
    """
    if not population_terms or not intervention_terms:
        # No vocabulary to check against. Letting the model decide is better
        # than silently rejecting the entire search.
        return True, ""

    abstract = (record.abstract or "").strip()
    haystack = " ".join([
        record.title or "",
        abstract,
        " ".join(record.mesh_terms or []),
        " ".join(record.keywords or []),
    ])

    has_population = _mentions_any(haystack, population_terms)
    has_intervention = _mentions_any(haystack, intervention_terms)

    if abstract:
        if has_population and has_intervention:
            return True, ""
        missing = []
        if not has_population:
            missing.append(f"population ({', '.join(population_terms[:3])})")
        if not has_intervention:
            missing.append(
                f"intervention ({', '.join(intervention_terms[:3])})")
        return False, (
            "Title, abstract, MeSH headings and keywords contain no mention "
            f"of the {' or the '.join(missing)}."
        )

    if has_population or has_intervention:
        return True, ""
    return False, (
        "No abstract available, and the title mentions neither the "
        "population nor the intervention."
    )


def _vote(system_prompt: str, protocol_text: str, record_text: str) -> ReviewerVote:
    """One reviewer's independent judgement."""
    vote = llm.call_json(
        system_prompt,
        f"REVIEW PROTOCOL\n{protocol_text}\n\n"
        f"RECORD TO SCREEN\n{record_text}",
        ReviewerVote,
    )
    return vote


def screen_record(
    record: StudyRecord,
    protocol_text: str,
    *,
    parallel: bool = True,
) -> DualScreenResult:
    """Screen one record with two independent reviewers.

    Args:
        record: The bibliographic record to judge.
        protocol_text: The eligibility criteria, rendered as text. Supplied
            in full on every call because the model must apply criteria, not
            recall them.
        parallel: Issue both reviewer calls at once. Roughly halves latency;
            set False when debugging so the logs stay ordered.

    Returns:
        Both votes plus the consensus. The consensus is computed here, not
        by the model.
    """
    record_text = _format_record(record)

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_a = pool.submit(_vote, prompts.SCREENER_SENSITIVE,
                                protocol_text, record_text)
            fut_b = pool.submit(_vote, prompts.SCREENER_SPECIFIC,
                                protocol_text, record_text)
            vote_a, vote_b = fut_a.result(), fut_b.result()
    else:
        vote_a = _vote(prompts.SCREENER_SENSITIVE, protocol_text, record_text)
        vote_b = _vote(prompts.SCREENER_SPECIFIC, protocol_text, record_text)

    include_a = vote_a.decision == ScreeningDecision.INCLUDE
    include_b = vote_b.decision == ScreeningDecision.INCLUDE

    if include_a or include_b:
        consensus = ScreeningDecision.INCLUDE
        category = ""
        if include_a and include_b:
            resolution = ""
        else:
            # Disagreement, resolved to Include. The objection is preserved
            # verbatim so that a human checking the full text knows what to
            # look at, and so a wrongly admitted record is traceable.
            objector_name, objector = (
                ("precision-oriented", vote_b) if include_a
                else ("recall-oriented", vote_a))
            resolution = (
                f"Reviewers disagreed: the {objector_name} reviewer would "
                f"have excluded this record. Resolved to Include, because at "
                f"title/abstract stage a disagreement is sent to full text, "
                f"where eligibility can be checked against the methods "
                f"section rather than guessed from an abstract. Objection "
                f"raised, to be verified at full text: {objector.reason[:300]}"
            )
    else:
        consensus = ScreeningDecision.EXCLUDE
        resolution = ""
        # Both excluded. Prefer the strict reviewer's category, since that
        # is the role that reasons about explicit mismatches, but fall back
        # to the other if it produced nothing usable.
        category = _normalise_category(vote_b.exclusion_category, vote_b.reason)
        if category == _UNCATEGORISED:
            category = _normalise_category(vote_a.exclusion_category,
                                           vote_a.reason)

    return DualScreenResult(
        reviewer_1=vote_a,
        reviewer_2=vote_b,
        consensus=consensus,
        conflict_resolution=resolution,
        exclusion_category=category,
    )


def screen_batch(
    records: list[StudyRecord],
    protocol_text: str,
    *,
    max_records: int | None = None,
    max_workers: int = 2,
    population_terms: list[str] | None = None,
    intervention_terms: list[str] | None = None,
    progress: Callable[[int, int, StudyRecord, DualScreenResult], None] | None = None,
) -> dict[str, Any]:
    """Screen many records and return the included set plus PRISMA counts.

    Args:
        records: Deduplicated records to screen.
        protocol_text: Eligibility criteria, supplied in full to every call.
        max_records: Hard cap. Screening is the slowest phase by far
            (roughly 10-40s per record on CPU), so development runs need a
            ceiling. Records beyond the cap are reported as `not_screened`
            rather than quietly dropped: a PRISMA diagram that does not
            account for every record is invalid.
        max_workers: Concurrent records. Each record already issues two
            calls, so the real concurrency against Ollama is double this.
            Beyond about 2 a CPU-bound local model gets slower, not faster.
        population_terms: Population vocabulary for the relevance gate. When
            omitted the gate is disabled and every record reaches the model.
        intervention_terms: Intervention vocabulary for the relevance gate.
        progress: Optional callback invoked after each record.

    Returns:
        Included records with their justification, excluded records with
        reasons, exclusion-reason counts for PRISMA, the inter-reviewer
        agreement rate, and any records that errored.
    """
    cap = max_records if max_records is not None else config.MAX_ABSTRACTS_TO_SCREEN
    to_screen = records[:cap] if cap and cap > 0 else list(records)
    not_screened = records[len(to_screen):]

    included: list[StudyRecord] = []
    included_records: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    exclusion_reasons: dict[str, int] = {}
    agreements = 0
    disagreements = 0
    gate_rejected = 0
    started = time.time()

    pop_terms = population_terms or []
    int_terms = intervention_terms or []

    def run_one(index_record: tuple[int, StudyRecord]):
        index, record = index_record
        # The gate runs first so an off-topic record costs no inference at
        # all. At ~20s per record on CPU this is also the single biggest
        # speed-up available.
        passed, gate_reason = relevance_gate(record, pop_terms, int_terms)
        if not passed:
            return index, record, None, None, gate_reason
        try:
            return index, record, screen_record(record, protocol_text), None, ""
        except Exception as exc:  # noqa: BLE001
            # One unparseable abstract must not abort a review that may have
            # taken hours to reach this point.
            return index, record, None, f"{type(exc).__name__}: {exc}", ""

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        results = pool.map(run_one, enumerate(to_screen))

        for position, (index, record, result, error, gate_reason) in \
                enumerate(results, 1):
            if error is not None:
                errors.append({"record": record.best_id, "error": error})
                continue

            rec_source = ", ".join(
                record.sources or ([record.source] if record.source else [])
            ) or "unknown"

            if result is None:
                # Rejected by the relevance gate. Counted under a standard
                # PRISMA category so it appears in the flow diagram rather
                # than vanishing between phases.
                gate_rejected += 1
                reason_lower = gate_reason.lower()
                if "intervention" in reason_lower and "population" not in reason_lower:
                    category = "Wrong intervention"
                else:
                    category = "Wrong population"
                exclusion_reasons[category] = exclusion_reasons.get(category, 0) + 1
                excluded.append({
                    "id": record.best_id,
                    "citation": record.citation,
                    "year": record.year,
                    "source": rec_source,
                    "url": record.verification_url,
                    "title": (record.title or "")[:240],
                    "category": category,
                    "reason": gate_reason,
                    "reviewer_1_decision": "Skipped (Gate)",
                    "reviewer_1_reason": gate_reason,
                    "reviewer_2_decision": "Skipped (Gate)",
                    "reviewer_2_reason": gate_reason,
                    "decided_by": "relevance gate (Python, no model call)",
                })
                continue

            if result.reviewer_1.decision == result.reviewer_2.decision:
                agreements += 1
            else:
                disagreements += 1

            if result.consensus == ScreeningDecision.INCLUDE:
                included.append(record)
                # Inclusions were previously not recorded at all, only
                # exclusions. That made it impossible to audit why a record
                # entered the review - which is how an off-topic paper
                # survived unnoticed in an earlier run.
                included_records.append({
                    "id": record.best_id,
                    "citation": record.citation,
                    "year": record.year,
                    "source": rec_source,
                    "url": record.verification_url,
                    "title": (record.title or "")[:240],
                    "reviewer_1_decision": result.reviewer_1.decision.value,
                    "reviewer_1_reason": result.reviewer_1.reason[:400],
                    "reviewer_2_decision": result.reviewer_2.decision.value,
                    "reviewer_2_reason": result.reviewer_2.reason[:400],
                    "decided_by": (result.conflict_resolution
                                   or "both reviewers agreed to include"),
                })
            else:
                category = result.exclusion_category or _UNCATEGORISED
                exclusion_reasons[category] = exclusion_reasons.get(category, 0) + 1
                excluded.append({
                    "id": record.best_id,
                    "citation": record.citation,
                    "year": record.year,
                    "source": rec_source,
                    "url": record.verification_url,
                    "title": (record.title or "")[:240],
                    "category": category,
                    "reason": result.reviewer_2.reason[:400],
                    "reviewer_1_decision": result.reviewer_1.decision.value,
                    "reviewer_1_reason": result.reviewer_1.reason[:400],
                    "reviewer_2_decision": result.reviewer_2.decision.value,
                    "reviewer_2_reason": result.reviewer_2.reason[:400],
                    "decided_by": (result.conflict_resolution
                                   or "both reviewers agreed to exclude"),
                })

            if progress:
                progress(position, len(to_screen), record, result)

    # Only records that actually reached both reviewers can contribute to an
    # agreement rate. Including gate-rejected records in the denominator
    # would make the reviewers look less consistent than they are.
    n_judged = agreements + disagreements
    return {
        "screened": len(to_screen),
        "not_screened": len(not_screened),
        "not_screened_note": (
            f"{len(not_screened)} record(s) were not screened because the "
            f"cap of {cap} was reached. They are excluded from the review "
            f"but counted here, because a PRISMA flow diagram must account "
            f"for every identified record. Raise SRMA_MAX_ABSTRACTS_TO_SCREEN "
            f"for a complete run."
        ) if not_screened else "",
        "included": included,
        "included_records": included_records,
        "excluded": excluded,
        "exclusion_reasons": exclusion_reasons,
        "errors": errors,
        "n_included": len(included),
        "n_excluded": len(excluded),
        "gate_rejected": gate_rejected,
        "gate_note": (
            f"{gate_rejected} record(s) were rejected by the Python relevance "
            f"gate before any model call, because their title, abstract, MeSH "
            f"headings and keywords never mentioned the population or the "
            f"intervention. This is a deterministic check that the model "
            f"cannot override."
        ) if gate_rejected else "",
        "reviewer_disagreements": disagreements,
        "reviewer_agreement_rate": (
            round(agreements / n_judged, 3) if n_judged else None
        ),
        "agreement_note": (
            "Agreement is measured between two prompts with deliberately "
            "different risk tolerances, over the records that reached both "
            "reviewers. A rate of exactly 1.0 across many records suggests "
            "the personas are not actually diverging and the dual-review "
            "safeguard is not doing any work. Because inclusion follows the "
            "liberal rule, every disagreement counted here is a record that "
            "was admitted despite one reviewer objecting; the objection is "
            "recorded against each such record in `included_records` and "
            "should be settled at full text."
        ),
        "elapsed_seconds": round(time.time() - started, 1),
    }
