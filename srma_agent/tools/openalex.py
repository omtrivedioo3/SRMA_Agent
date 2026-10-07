"""OpenAlex connector, including forward and backward citation tracking.

OpenAlex is the citation backbone of this pipeline. The specification requires
a citation audit — checking that no eligible study was missed — and that is
done two ways:

  backward chasing : the reference lists of included studies
  forward chasing  : everything that has since cited them

OpenAlex exposes both directions as filters (`cited_by:` and `cites:`), which
is cheaper and far more complete than scraping reference lists per publisher.
Abstracts arrive as an inverted index and are reconstructed here, because the
screening model needs running prose.
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

SOURCE = "openalex"

_BASE = "https://api.openalex.org"
_WORKS = f"{_BASE}/works"

# OpenAlex caps per-page at 200.
_PAGE_SIZE = 200


def _polite_params() -> dict[str, str]:
    """`mailto` moves us into OpenAlex's faster, more reliable polite pool."""
    return {"mailto": config.CONTACT_EMAIL}


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Full-text relevance search across OpenAlex works.

    Raises:
        http.SourceError: if OpenAlex is unreachable.
    """
    return _paged_search(
        {"search": query}, resolve_limit(max_results), query)


def search_by_filter(filter_expr: str,
                     max_results: int | None = None) -> list[StudyRecord]:
    """Escape hatch for any OpenAlex filter expression, e.g. a date window."""
    return _paged_search(
        {"filter": filter_expr}, resolve_limit(max_results), filter_expr)


def cited_by(work_id: str,
             max_results: int | None = None) -> list[StudyRecord]:
    """Forward citations: works that cite `work_id`.

    This is how the review catches studies published after the original
    search was designed.
    """
    short_id = _short_id(work_id)
    if not short_id:
        return []
    return _paged_search({"filter": f"cites:{short_id}"},
                         resolve_limit(max_results),
                         f"cites:{short_id}")


def references_of(work_id: str,
                  max_results: int | None = None) -> list[StudyRecord]:
    """Backward citations: works cited by `work_id` (its reference list)."""
    short_id = _short_id(work_id)
    if not short_id:
        return []
    return _paged_search({"filter": f"cited_by:{short_id}"},
                         resolve_limit(max_results),
                         f"cited_by:{short_id}")


def citation_audit(work_ids: list[str],
                   max_per_work: int = 50) -> dict[str, list[StudyRecord]]:
    """Run both citation directions over a seed set of included studies.

    Returns a dict with `forward` and `backward` record lists, deduplicated
    on OpenAlex id. Per-work failures are swallowed: a citation audit is a
    supplementary search, and one bad id must not sink the whole review.
    """
    forward: dict[str, StudyRecord] = {}
    backward: dict[str, StudyRecord] = {}
    seeds = {(_short_id(w) or "") for w in work_ids}

    for work_id in work_ids:
        for bucket, fetch in ((forward, cited_by), (backward, references_of)):
            try:
                for record in fetch(work_id, max_per_work):
                    key = record.openalex_id or record.best_id
                    if key not in bucket and _short_id(key) not in seeds:
                        bucket[key] = record
            except http.SourceError:
                continue

    return {"forward": list(forward.values()),
            "backward": list(backward.values())}


def fetch_work(identifier: str) -> StudyRecord | None:
    """Fetch one work by OpenAlex id, DOI, PMID or PMCID."""
    path = _entity_path(identifier)
    if not path:
        return None
    try:
        payload = http.request_json(SOURCE, f"{_WORKS}/{path}",
                                    _polite_params())
    except http.SourceError:
        return None
    if not payload:
        return None
    record = _to_record(payload)
    record.source = SOURCE
    record.sources = [SOURCE]
    record.retrieved_query = identifier
    return record


# --------------------------------------------------------------------------
# Paging
# --------------------------------------------------------------------------


def _paged_search(query_params: dict[str, str], limit: int,
                  provenance: str) -> list[StudyRecord]:
    records: list[StudyRecord] = []
    cursor = "*"

    while len(records) < limit:
        params: dict[str, Any] = {
            **query_params,
            **_polite_params(),
            "per-page": min(_PAGE_SIZE, limit - len(records)),
            "cursor": cursor,
        }
        payload = http.request_json(SOURCE, _WORKS, params)
        results = (payload or {}).get("results") or []
        if not results:
            break

        for item in results:
            record = _to_record(item)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = provenance
            records.append(record)

        cursor = ((payload or {}).get("meta") or {}).get("next_cursor")
        if not cursor:
            break

    return records[:limit]


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _short_id(value: str | None) -> str | None:
    """OpenAlex ids are URLs; filters want the bare `W…` form."""
    if not value:
        return None
    tail = str(value).rstrip("/").split("/")[-1]
    return tail if tail.upper().startswith("W") else None


def _entity_path(identifier: str) -> str | None:
    """Build the single-entity path OpenAlex accepts for various id types."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    short = _short_id(ident)
    if short:
        return short
    doi = normalise_doi(ident)
    if doi:
        return f"doi:{doi}"
    if ident.upper().startswith("PMC"):
        return f"pmcid:{ident.upper()}"
    if ident.isdigit():
        return f"pmid:{ident}"
    return None


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Rebuild prose from OpenAlex's inverted index.

    OpenAlex stores abstracts as {token: [positions]} to sidestep copyright
    on contiguous text; the screening model needs the contiguous text back.
    """
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for token, indices in inverted_index.items():
        for index in indices or []:
            positions.append((index, token))
    if not positions:
        return ""
    positions.sort(key=lambda pair: pair[0])
    return clean_text(" ".join(token for _, token in positions))


def _to_record(item: dict[str, Any]) -> StudyRecord:
    ids = item.get("ids") or {}
    open_access = item.get("open_access") or {}
    primary = item.get("primary_location") or {}
    best_oa = item.get("best_oa_location") or {}
    is_oa = bool(open_access.get("is_oa"))

    return StudyRecord(
        doi=normalise_doi(item.get("doi") or ids.get("doi")),
        pmid=normalise_pmid(_tail(ids.get("pmid"))),
        pmcid=normalise_pmcid(_tail(ids.get("pmcid"))),
        openalex_id=_short_id(item.get("id") or ids.get("openalex")),
        title=clean_text(item.get("display_name") or item.get("title")),
        abstract=reconstruct_abstract(item.get("abstract_inverted_index")),
        authors=_authors(item),
        journal=clean_text(
            ((primary.get("source") or {}).get("display_name")) or ""),
        year=parse_year(item.get("publication_year")
                        or item.get("publication_date")),
        publication_types=dedupe_preserving_order(
            clean_text(t) for t in
            (item.get("type"), item.get("type_crossref")) if t),
        mesh_terms=_mesh(item),
        keywords=_keywords(item),
        url=(primary.get("landing_page_url")
             or (f"https://doi.org/{normalise_doi(item.get('doi'))}"
                 if item.get("doi") else "")
             or item.get("id") or ""),
        is_open_access=is_oa,
        full_text_url=(open_access.get("oa_url")
                       or best_oa.get("pdf_url")
                       or best_oa.get("landing_page_url")) or None,
        cited_by_count=item.get("cited_by_count"),
        references=[rid for rid in
                    (_short_id(r) for r in item.get("referenced_works") or [])
                    if rid],
    )


def _tail(url: str | None) -> str | None:
    return str(url).rstrip("/").split("/")[-1] if url else None


def _authors(item: dict[str, Any]) -> list[str]:
    names = []
    for authorship in item.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name")
                or authorship.get("raw_author_name"))
        if name:
            names.append(clean_text(name))
    return names


def _mesh(item: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for entry in item.get("mesh") or []:
        descriptor = clean_text(entry.get("descriptor_name"))
        if not descriptor:
            continue
        qualifier = clean_text(entry.get("qualifier_name"))
        terms.append(f"{descriptor}/{qualifier}" if qualifier else descriptor)
    return dedupe_preserving_order(terms)


def _keywords(item: dict[str, Any]) -> list[str]:
    values = [clean_text(k.get("display_name"))
              for k in item.get("keywords") or []]
    values += [clean_text(c.get("display_name"))
               for c in item.get("concepts") or []]
    return dedupe_preserving_order(v for v in values if v)
