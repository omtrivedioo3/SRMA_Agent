"""Crossref connector for DOI metadata resolution and reference lists.

Crossref is the registration agency for most scholarly DOIs, so it is the
authoritative place to (a) resolve a bare DOI scraped from a PDF or a trial
registry into real bibliographic metadata, and (b) obtain publisher-deposited
reference lists for backward citation chasing when OpenAlex has not yet
ingested a very recent paper.

Crossref's relevance ranking is weak compared with PubMed's, so `search` here
is a supplementary recall net, not a primary source.
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..schemas import StudyRecord
from . import http
from ._common import (
    clean_text,
    dedupe_preserving_order,
    normalise_doi,
    normalise_pmid,
    parse_year,
    resolve_limit,
)

SOURCE = "crossref"

_BASE = "https://api.crossref.org"
_WORKS = f"{_BASE}/works"

# Crossref allows up to 1000 rows; 100 keeps individual responses manageable.
_PAGE_SIZE = 100


def _polite_params() -> dict[str, str]:
    """`mailto` buys access to Crossref's polite pool (better SLA)."""
    return {"mailto": config.CONTACT_EMAIL}


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Bibliographic search across Crossref works.

    Raises:
        http.SourceError: if Crossref is unreachable.
    """
    limit = resolve_limit(max_results)
    records: list[StudyRecord] = []
    cursor = "*"

    while len(records) < limit:
        params: dict[str, Any] = {
            "query.bibliographic": query,
            "rows": min(_PAGE_SIZE, limit - len(records)),
            "cursor": cursor,
            **_polite_params(),
        }
        payload = http.request_json(SOURCE, _WORKS, params)
        message = (payload or {}).get("message") or {}
        items = message.get("items") or []
        if not items:
            break

        for item in items:
            record = _to_record(item)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = query
            records.append(record)

        next_cursor = message.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return records[:limit]


def _fetch_message(doi: str) -> dict[str, Any] | None:
    """GET one work. None covers both "unknown DOI" and "Crossref is down".

    Retries are capped at two: a 404 here means the DOI belongs to another
    registration agency (DataCite, mEDRA...), which no amount of retrying
    will change.
    """
    canonical = normalise_doi(doi)
    if not canonical:
        return None
    try:
        payload = http.request_json(
            SOURCE, f"{_WORKS}/{canonical}", _polite_params(), max_retries=2)
    except http.SourceError:
        return None
    message = (payload or {}).get("message")
    return message if isinstance(message, dict) else None


def fetch_doi(doi: str) -> StudyRecord | None:
    """Resolve one DOI to metadata; None when the DOI is unknown to Crossref."""
    message = _fetch_message(doi)
    if not message:
        return None
    record = _to_record(message)
    record.source = SOURCE
    record.sources = [SOURCE]
    record.retrieved_query = normalise_doi(doi) or doi
    return record


def fetch_references(doi: str) -> list[str]:
    """Publisher-deposited reference DOIs, for backward citation chasing."""
    message = _fetch_message(doi)
    return _reference_dois(message) if message else []


def resolve_dois(dois: list[str]) -> list[StudyRecord]:
    """Batch DOI resolution; unknown DOIs are silently dropped."""
    out: list[StudyRecord] = []
    for doi in dedupe_preserving_order(
            d for d in (normalise_doi(x) for x in dois) if d):
        record = fetch_doi(doi)
        if record:
            out.append(record)
    return out


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _to_record(item: dict[str, Any]) -> StudyRecord:
    doi = normalise_doi(item.get("DOI"))
    full_text_url = _full_text_url(item)

    return StudyRecord(
        doi=doi,
        pmid=normalise_pmid(_pmid_from_relation(item)),
        title=clean_text(_first(item.get("title"))),
        abstract=clean_text(item.get("abstract")),
        authors=_authors(item),
        journal=clean_text(_first(item.get("container-title"))
                           or _first(item.get("institution"))
                           or item.get("publisher")),
        year=_year(item),
        publication_types=[clean_text(item.get("type"))]
        if item.get("type") else [],
        keywords=dedupe_preserving_order(
            clean_text(s) for s in item.get("subject") or []),
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        is_open_access=bool(full_text_url),
        full_text_url=full_text_url,
        cited_by_count=item.get("is-referenced-by-count"),
        references=_reference_dois(item),
    )


def _first(value: Any) -> Any:
    """Crossref wraps most scalar fields in single-element lists."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _authors(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for author in item.get("author") or []:
        name = author.get("name")
        if not name:
            name = f"{author.get('given', '')} {author.get('family', '')}"
        name = clean_text(name)
        if name:
            names.append(name)
    return names


def _year(item: dict[str, Any]) -> int | None:
    for key in ("issued", "published", "published-print",
                "published-online", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = parse_year(parts[0][0])
            if year:
                return year
    return None


def _reference_dois(item: dict[str, Any]) -> list[str]:
    dois = (normalise_doi(ref.get("DOI"))
            for ref in item.get("reference") or [])
    return dedupe_preserving_order(d for d in dois if d)


def _full_text_url(item: dict[str, Any]) -> str | None:
    """Only links marked for text-mining are legally safe to fetch."""
    for link in item.get("link") or []:
        if link.get("intended-application") in ("text-mining", "similarity-checking"):
            if link.get("URL"):
                return link["URL"]
    return None


def _pmid_from_relation(item: dict[str, Any]) -> str | None:
    """Some publishers deposit the PMID as a Crossref relation."""
    relations = item.get("relation") or {}
    for entries in relations.values():
        for entry in entries if isinstance(entries, list) else []:
            if str(entry.get("id-type", "")).lower() == "pmid":
                return entry.get("id")
    return None
