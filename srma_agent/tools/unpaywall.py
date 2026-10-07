"""Unpaywall connector: legal open-access full-text discovery by DOI.

Full-text retrieval is the bottleneck for risk-of-bias assessment, and the
only defensible way to automate it is to fetch copies the publisher or author
has deliberately made free. Unpaywall aggregates exactly those: repository
deposits, hybrid-OA articles and publisher-hosted free versions. Nothing here
touches a paywall or a shadow library.

Unpaywall has no keyword-search endpoint — it is a DOI-keyed lookup service.
`search()` is therefore provided only so this module honours the same
signature as the other connectors: it accepts one or more DOIs.
"""

from __future__ import annotations

from typing import Any, Iterable

from .. import config
from ..schemas import StudyRecord
from . import http
from ._common import (
    clean_text,
    dedupe_preserving_order,
    normalise_doi,
    parse_year,
    resolve_limit,
)

SOURCE = "unpaywall"

_BASE = "https://api.unpaywall.org/v2"

# Repository copies are preferred over publisher landing pages when both
# exist: they are stable, machine-readable, and usually a direct PDF.
_HOST_PREFERENCE = ("repository", "publisher", "other")


def _params() -> dict[str, str]:
    """Unpaywall rejects any request without an identifying email."""
    return {"email": config.CONTACT_EMAIL}


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Resolve DOIs (comma, whitespace or newline separated) to OA records.

    Unpaywall is a lookup service, not a search engine; `query` must contain
    DOIs. Unknown DOIs are skipped rather than raising, since a miss is the
    normal outcome for non-Crossref identifiers.
    """
    limit = resolve_limit(max_results)
    dois = _extract_dois(query)
    records: list[StudyRecord] = []
    for doi in dois[:limit]:
        record = fetch_record(doi)
        if record is None:
            continue
        record.source = SOURCE
        record.sources = [SOURCE]
        record.retrieved_query = query
        records.append(record)
    return records


def lookup(doi: str) -> dict[str, Any] | None:
    """Raw Unpaywall payload for a DOI, or None when it is not indexed."""
    canonical = normalise_doi(doi)
    if not canonical:
        return None
    try:
        payload = http.request_json(
            SOURCE, f"{_BASE}/{canonical}", _params(), max_retries=2)
    except http.SourceError:
        # 404 simply means "DOI unknown to Unpaywall", which is routine and
        # will not become true on a retry.
        return None
    return payload if isinstance(payload, dict) else None


def find_full_text(doi: str) -> str | None:
    """Best legal open-access URL for a DOI, preferring a direct PDF."""
    payload = lookup(doi)
    return _best_location_url(payload) if payload else None


def fetch_record(doi: str) -> StudyRecord | None:
    """Unpaywall's own metadata for a DOI as a StudyRecord."""
    payload = lookup(doi)
    if not payload:
        return None
    record = _to_record(payload)
    record.source = SOURCE
    record.sources = [SOURCE]
    record.retrieved_query = record.doi or doi
    return record


def enrich(records: Iterable[StudyRecord]) -> list[StudyRecord]:
    """Fill in open-access status and full-text URL on existing records.

    Mutates in place and returns the same objects, so this can be dropped
    into the pipeline after deduplication without reshuffling identity.
    """
    out: list[StudyRecord] = []
    for record in records:
        out.append(record)
        if record.full_text_url or not record.doi:
            continue  # already resolved, or nothing to look up
        payload = lookup(record.doi)
        if not payload:
            continue
        if payload.get("is_oa"):
            record.is_open_access = True
            url = _best_location_url(payload)
            if url:
                record.full_text_url = url
        if not record.journal:
            record.journal = clean_text(payload.get("journal_name"))
        if not record.year:
            record.year = parse_year(payload.get("year")
                                     or payload.get("published_date"))
    return out


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _extract_dois(text: str) -> list[str]:
    tokens = (text or "").replace(",", " ").replace(";", " ").split()
    return dedupe_preserving_order(
        d for d in (normalise_doi(t) for t in tokens) if d)


def _best_location_url(payload: dict[str, Any]) -> str | None:
    best = payload.get("best_oa_location") or {}
    for key in ("url_for_pdf", "url", "url_for_landing_page"):
        if best.get(key):
            return best[key]

    # best_oa_location can be null even when oa_locations is populated.
    locations = payload.get("oa_locations") or []
    ranked = sorted(
        locations,
        key=lambda loc: _HOST_PREFERENCE.index(loc.get("host_type"))
        if loc.get("host_type") in _HOST_PREFERENCE else len(_HOST_PREFERENCE))
    for location in ranked:
        for key in ("url_for_pdf", "url", "url_for_landing_page"):
            if location.get(key):
                return location[key]
    return None


def _to_record(payload: dict[str, Any]) -> StudyRecord:
    doi = normalise_doi(payload.get("doi"))
    is_oa = bool(payload.get("is_oa"))
    genre = clean_text(payload.get("genre"))

    return StudyRecord(
        doi=doi,
        title=clean_text(payload.get("title")),
        authors=_authors(payload),
        journal=clean_text(payload.get("journal_name")
                           or payload.get("publisher")),
        year=parse_year(payload.get("year") or payload.get("published_date")),
        publication_types=[genre] if genre else [],
        keywords=dedupe_preserving_order(
            [clean_text(payload.get("oa_status"))] if payload.get("oa_status")
            else []),
        url=payload.get("doi_url") or (f"https://doi.org/{doi}" if doi else ""),
        is_open_access=is_oa,
        full_text_url=_best_location_url(payload) if is_oa else None,
    )


def _authors(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for author in payload.get("z_authors") or []:
        name = author.get("name") or (
            f"{author.get('given', '')} {author.get('family', '')}")
        name = clean_text(name)
        if name:
            names.append(name)
    return names
