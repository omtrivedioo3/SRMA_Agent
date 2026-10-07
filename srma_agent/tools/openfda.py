"""openFDA connector for drug safety signals.

Harms are systematically under-reported in efficacy trials, so a review that
draws safety conclusions from RCT abstracts alone is incomplete. openFDA
exposes two complementary post-marketing sources:

  FAERS adverse event reports - spontaneous, real-world harm signals
  Structured product labels    - the regulator-approved harm statement

Neither is bibliographic evidence and neither supports causal inference
(FAERS has no denominator). They are carried as StudyRecords purely so the
downstream narrative-synthesis stage can cite them as contextual safety
signals, and every record is tagged with a publication_type that says so.

openFDA answers a zero-hit query with HTTP 404, so "no results" is handled
here as an empty list rather than as a source failure.
"""

from __future__ import annotations

from typing import Any

from ..schemas import StudyRecord
from . import http
from ._common import (
    clean_text,
    dedupe_preserving_order,
    parse_year,
    resolve_limit,
)

SOURCE = "openfda"

_BASE = "https://api.fda.gov"
_EVENTS = f"{_BASE}/drug/event.json"
_LABELS = f"{_BASE}/drug/label.json"

# openFDA accepts up to 1000, but 100 keeps single responses small.
_PAGE_SIZE = 100

# FAERS outcome codes, per the openFDA field reference.
_OUTCOMES = {
    "1": "recovered", "2": "recovering", "3": "not recovered",
    "4": "recovered with sequelae", "5": "fatal", "6": "unknown",
}


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Retrieve FAERS adverse event reports relevant to a free-text query.

    The query is interpreted as "<drug> <reaction terms>", which matches how
    a PICO question is phrased ("aspirin myocardial infarction").
    """
    limit = resolve_limit(max_results)
    drug, reaction = _split_query(query)

    # Narrowest useful query first, then widen, so a specific reaction term
    # does not silently zero out the whole safety search.
    for expression in _candidate_expressions(drug, reaction, query):
        items = _fetch_all(_EVENTS, expression, limit)
        if items:
            records = [_event_record(item) for item in items]
            for record in records:
                record.source = SOURCE
                record.sources = [SOURCE]
                record.retrieved_query = query
            return records[:limit]
    return []


def search_labels(query: str,
                  max_results: int | None = None) -> list[StudyRecord]:
    """Retrieve structured product labels (regulator-approved harm text)."""
    limit = resolve_limit(max_results)
    drug, _ = _split_query(query)
    expressions = [
        f'openfda.generic_name:"{drug}"',
        f'openfda.brand_name:"{drug}"',
        f'openfda.substance_name:"{drug}"',
    ]
    for expression in expressions:
        items = _fetch_all(_LABELS, expression, limit)
        if items:
            records = [_label_record(item) for item in items]
            for record in records:
                record.source = SOURCE
                record.sources = [SOURCE]
                record.retrieved_query = query
            return records[:limit]
    return []


def reaction_signal(drug: str, top_n: int = 25) -> dict[str, int]:
    """Reaction-term frequency counts for one drug.

    openFDA's `count` aggregation answers in a single request what would
    otherwise take thousands of report downloads.
    """
    params = {
        "search": f'patient.drug.medicinalproduct:"{drug}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": max(1, min(int(top_n), 1000)),
    }
    payload = _try_get(_EVENTS, params)
    if not payload:
        return {}
    return {clean_text(row.get("term")): int(row.get("count", 0))
            for row in payload.get("results") or []
            if row.get("term")}


def serious_outcome_counts(drug: str) -> dict[str, int]:
    """How many reports for a drug were flagged serious versus not."""
    params = {
        "search": f'patient.drug.medicinalproduct:"{drug}"',
        "count": "serious",
        "limit": 10,
    }
    payload = _try_get(_EVENTS, params)
    if not payload:
        return {}
    labels = {"1": "serious", "2": "non_serious"}
    return {labels.get(str(row.get("term")), str(row.get("term"))):
            int(row.get("count", 0))
            for row in payload.get("results") or []}


# --------------------------------------------------------------------------
# Query construction
# --------------------------------------------------------------------------


def _split_query(query: str) -> tuple[str, str]:
    """Split "aspirin myocardial infarction" into drug and reaction phrase."""
    tokens = [t for t in (query or "").split() if t]
    if not tokens:
        return "", ""
    return tokens[0], " ".join(tokens[1:])


def _candidate_expressions(drug: str, reaction: str,
                           raw_query: str) -> list[str]:
    drug_clause = ("(" + " OR ".join([
        f'patient.drug.medicinalproduct:"{drug}"',
        f'patient.drug.openfda.generic_name:"{drug}"',
        f'patient.drug.openfda.brand_name:"{drug}"',
    ]) + ")") if drug else ""

    expressions: list[str] = []
    if drug_clause and reaction:
        expressions.append(
            f'{drug_clause} AND patient.reaction.reactionmeddrapt:"{reaction}"')
    if drug_clause:
        expressions.append(drug_clause)
    if raw_query:
        expressions.append(f'patient.drug.medicinalproduct:"{raw_query}"')
    return [e for e in expressions if e]


def _fetch_all(url: str, expression: str, limit: int) -> list[dict[str, Any]]:
    """Page through an openFDA endpoint with skip/limit."""
    items: list[dict[str, Any]] = []
    skip = 0
    while len(items) < limit:
        params = {
            "search": expression,
            "limit": min(_PAGE_SIZE, limit - len(items)),
            "skip": skip,
        }
        payload = _try_get(url, params)
        if not payload:
            break
        results = payload.get("results") or []
        if not results:
            break
        items.extend(results)
        skip += len(results)
        total = ((payload.get("meta") or {}).get("results") or {}).get("total")
        if total is not None and skip >= int(total):
            break
    return items[:limit]


def _try_get(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """GET that maps openFDA's 404-for-no-matches onto None.

    Retries are capped: a 404 here is a terminal "no records matched", and
    the query-widening ladder above would otherwise pay the full backoff
    penalty on every rung.
    """
    try:
        payload = http.request_json(SOURCE, url, params, max_retries=2)
    except http.SourceError:
        return None
    return payload if isinstance(payload, dict) else None


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _reporter(item: dict[str, Any]) -> list[str]:
    """FAERS has no authors; the reporter's role/country is the closest thing."""
    source = item.get("primarysource") or {}
    attribution = clean_text(source.get("qualification_label")
                             or source.get("reportercountry")
                             or item.get("companynumb"))
    return [attribution] if attribution else []


def _event_record(item: dict[str, Any]) -> StudyRecord:
    patient = item.get("patient") or {}
    report_id = clean_text(item.get("safetyreportid")) or "unknown"
    drugs = _drug_names(patient)
    reactions = _reactions(patient)

    title = (f"FAERS adverse event report {report_id}: "
             f"{', '.join(drugs[:3]) or 'unspecified drug'} — "
             f"{', '.join(r[0] for r in reactions[:3]) or 'unspecified reaction'}")

    return StudyRecord(
        title=title,
        abstract=_event_abstract(item, patient, drugs, reactions),
        authors=_reporter(item),
        journal="openFDA FAERS",
        year=parse_year(item.get("receiptdate") or item.get("receivedate")),
        publication_types=["Adverse Event Report", "Pharmacovigilance",
                           "Non-bibliographic safety signal"],
        keywords=dedupe_preserving_order(
            drugs + [r[0] for r in reactions]),
        url=("https://api.fda.gov/drug/event.json?search=safetyreportid:"
             f'"{report_id}"'),
        is_open_access=True,
        trial_status=None,
        has_results=True,
    )


def _event_abstract(item: dict[str, Any], patient: dict[str, Any],
                    drugs: list[str],
                    reactions: list[tuple[str, str]]) -> str:
    serious = "serious" if str(item.get("serious")) == "1" else "non-serious"
    age = patient.get("patientonsetage")
    sex = {"1": "male", "2": "female"}.get(str(patient.get("patientsex")), "")
    indications = dedupe_preserving_order(
        clean_text(d.get("drugindication"))
        for d in patient.get("drug") or [] if d.get("drugindication"))

    parts = [
        f"Spontaneous post-marketing report classified as {serious}.",
        f"Suspect/concomitant products: {', '.join(drugs) or 'not stated'}.",
        "Reported reactions: " + (
            ", ".join(f"{term} ({outcome})" if outcome else term
                      for term, outcome in reactions) or "not stated") + ".",
    ]
    if indications:
        parts.append(f"Reported indications: {', '.join(indications)}.")
    if age or sex:
        parts.append(
            f"Patient: {age or 'unknown'} years, {sex or 'sex unknown'}.")
    if item.get("seriousnessdeath"):
        parts.append("Outcome included death.")
    parts.append("FAERS reports are unverified and have no denominator; "
                 "they indicate a signal, not causation or incidence.")
    return " ".join(parts)


def _drug_names(patient: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for drug in patient.get("drug") or []:
        name = clean_text(drug.get("medicinalproduct"))
        if name:
            names.append(name)
        for generic in (drug.get("openfda") or {}).get("generic_name") or []:
            names.append(clean_text(generic))
    return dedupe_preserving_order(names)


def _reactions(patient: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for reaction in patient.get("reaction") or []:
        term = clean_text(reaction.get("reactionmeddrapt"))
        if not term:
            continue
        outcome = _OUTCOMES.get(str(reaction.get("reactionoutcome")), "")
        out.append((term, outcome))
    return out


def _label_record(item: dict[str, Any]) -> StudyRecord:
    openfda = item.get("openfda") or {}
    brand = clean_text(_first(openfda.get("brand_name")))
    generic = clean_text(_first(openfda.get("generic_name")))
    label_id = clean_text(item.get("id"))

    name = " / ".join(n for n in (brand, generic) if n) or "Unnamed product"
    sections = []
    for field, heading in (("boxed_warning", "Boxed warning"),
                           ("warnings_and_cautions", "Warnings and cautions"),
                           ("warnings", "Warnings"),
                           ("adverse_reactions", "Adverse reactions"),
                           ("indications_and_usage", "Indications")):
        text = clean_text(_first(item.get(field)))
        if text:
            # Labels run to tens of thousands of characters; the screening
            # model only needs the leading summary of each section.
            sections.append(f"{heading}: {text[:1500]}")

    return StudyRecord(
        title=f"FDA structured product label: {name}",
        abstract=" ".join(sections),
        authors=dedupe_preserving_order(
            clean_text(m) for m in openfda.get("manufacturer_name") or []),
        journal="openFDA Drug Label",
        year=parse_year(item.get("effective_time")),
        publication_types=["Drug Label", "Regulatory Document",
                           "Non-bibliographic safety signal"],
        keywords=dedupe_preserving_order(
            [clean_text(x) for x in
             (openfda.get("generic_name") or []) +
             (openfda.get("brand_name") or []) +
             (openfda.get("pharm_class_epc") or [])]),
        url=(f'https://api.fda.gov/drug/label.json?search=id:"{label_id}"'
             if label_id else _LABELS),
        is_open_access=True,
        has_results=True,
    )


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value
