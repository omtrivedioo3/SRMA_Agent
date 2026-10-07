"""Semantic Scholar Graph API connector.

Semantic Scholar adds two things the other sources lack: a large corpus of
conference and CS-adjacent literature, and typed citation edges. It is used
here as a supplementary recall net and as a second opinion for the citation
audit.

Everything degrades to an empty list rather than raising. The public tier is
aggressively rate-limited (HTTP 429 is the normal response under any load),
and an optional bonus source must never be able to fail a systematic review.
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
    normalise_pmcid,
    normalise_pmid,
    parse_year,
    resolve_limit,
)

SOURCE = "semantic_scholar"

_BASE = "https://api.semanticscholar.org/graph/v1"
_SEARCH = f"{_BASE}/paper/search"

# Requesting fields explicitly is mandatory; the default response is 3 fields.
_FIELDS = ",".join([
    "paperId", "externalIds", "title", "abstract", "venue", "year",
    "authors", "publicationTypes", "fieldsOfStudy", "citationCount",
    "referenceCount", "openAccessPdf", "isOpenAccess", "url",
    "publicationDate", "journal",
])
_EDGE_FIELDS = ",".join([
    "paperId", "externalIds", "title", "abstract", "venue", "year",
    "authors", "publicationTypes", "citationCount", "openAccessPdf", "url",
])

# Hard ceiling imposed by the API on a single search page.
_PAGE_SIZE = 100


def _headers() -> dict[str, str]:
    """An API key lifts us out of the shared, heavily contended public pool."""
    if config.SEMANTIC_SCHOLAR_API_KEY:
        return {"x-api-key": config.SEMANTIC_SCHOLAR_API_KEY}
    return {}


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Relevance search. Returns [] rather than raising when rate-limited."""
    limit = resolve_limit(max_results)
    records: list[StudyRecord] = []
    offset = 0

    while len(records) < limit:
        params = {
            "query": query,
            "limit": min(_PAGE_SIZE, limit - len(records)),
            "offset": offset,
            "fields": _FIELDS,
        }
        payload = _try_get(_SEARCH, params)
        if payload is None:
            break

        items = payload.get("data") or []
        if not items:
            break

        for item in items:
            record = _to_record(item)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = query
            records.append(record)

        next_offset = payload.get("next")
        if next_offset is None:
            break
        offset = int(next_offset)

    return records[:limit]


def citations(paper_id: str,
              max_results: int | None = None) -> list[StudyRecord]:
    """Forward citations for a paper id, DOI (`DOI:…`) or PMID (`PMID:…`)."""
    return _edges(paper_id, "citations", "citingPaper", max_results)


def references(paper_id: str,
               max_results: int | None = None) -> list[StudyRecord]:
    """Backward citations: the paper's own reference list."""
    return _edges(paper_id, "references", "citedPaper", max_results)


def fetch_paper(paper_id: str) -> StudyRecord | None:
    """Fetch a single paper; None on any failure or unknown identifier."""
    ident = _qualify(paper_id)
    payload = _try_get(f"{_BASE}/paper/{ident}", {"fields": _FIELDS})
    if not payload:
        return None
    record = _to_record(payload)
    record.source = SOURCE
    record.sources = [SOURCE]
    record.retrieved_query = ident
    return record


def _edges(paper_id: str, kind: str, item_key: str,
           max_results: int | None) -> list[StudyRecord]:
    limit = resolve_limit(max_results)
    ident = _qualify(paper_id)
    payload = _try_get(f"{_BASE}/paper/{ident}/{kind}",
                       {"fields": _EDGE_FIELDS, "limit": min(_PAGE_SIZE, limit)})
    if not payload:
        return []

    records: list[StudyRecord] = []
    for edge in payload.get("data") or []:
        item = edge.get(item_key) or {}
        if not item:
            continue
        record = _to_record(item)
        record.source = SOURCE
        record.sources = [SOURCE]
        record.retrieved_query = f"{kind}:{ident}"
        records.append(record)
    return records[:limit]


def _qualify(paper_id: str) -> str:
    """Accept bare DOIs/PMIDs and prefix them the way the API expects."""
    ident = (paper_id or "").strip()
    if ":" in ident and not ident.startswith("10."):
        return ident
    doi = normalise_doi(ident)
    if doi:
        return f"DOI:{doi}"
    if ident.upper().startswith("PMC"):
        return f"PMCID:{ident.upper()}"
    if ident.isdigit():
        return f"PMID:{ident}"
    return ident


def _try_get(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """GET that converts every failure into None, per this module's contract."""
    try:
        payload = http.request_json(SOURCE, url, params, headers=_headers())
    except http.SourceError:
        return None
    return payload if isinstance(payload, dict) else None


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _to_record(item: dict[str, Any]) -> StudyRecord:
    external = item.get("externalIds") or {}
    oa_pdf = (item.get("openAccessPdf") or {}).get("url")

    return StudyRecord(
        doi=normalise_doi(external.get("DOI")),
        pmid=normalise_pmid(external.get("PubMed")),
        pmcid=normalise_pmcid(external.get("PubMedCentral")),
        title=clean_text(item.get("title")),
        abstract=clean_text(item.get("abstract")),
        authors=[clean_text(a.get("name")) for a in item.get("authors") or []
                 if a.get("name")],
        journal=clean_text((item.get("journal") or {}).get("name")
                           or item.get("venue")),
        year=parse_year(item.get("year") or item.get("publicationDate")),
        publication_types=dedupe_preserving_order(
            clean_text(t) for t in item.get("publicationTypes") or []),
        keywords=dedupe_preserving_order(
            clean_text(f) for f in item.get("fieldsOfStudy") or []),
        url=item.get("url") or "",
        is_open_access=bool(item.get("isOpenAccess") or oa_pdf),
        full_text_url=oa_pdf,
        cited_by_count=item.get("citationCount"),
    )
