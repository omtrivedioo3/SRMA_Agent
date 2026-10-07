"""medRxiv / bioRxiv preprint connector — the grey-literature arm.

Publication bias is the single largest threat to a meta-analysis: negative and
null results disproportionately never reach a journal. The specification
therefore requires an unpublished-literature search, and preprint servers are
the highest-yield grey-literature source in biomedicine.

Two retrieval paths are implemented, because the Cold Spring Harbor APIs have
no keyword-search endpoint at all — they only expose date windows and
single-DOI lookups:

  1. `search()` resolves the keyword query against the Europe PMC preprint
     index (`SRC:PPR`), which mirrors every medRxiv/bioRxiv deposit, then
     enriches each hit through the native CSH API to recover the fields only
     it has: version number, subject category, and whether the preprint has
     since been published in a journal.
  2. `scan_by_date()` walks the native API directly and filters client-side.
     Slower, but it depends on no third-party index, which matters when the
     review protocol must justify its grey-literature search strategy.

The `published` field is load-bearing: including both a preprint and its
journal version double-counts a study in the pooled effect estimate.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Iterable

from ..schemas import StudyRecord
from . import http
from ._common import (
    clean_text,
    dedupe_preserving_order,
    normalise_doi,
    parse_year,
    resolve_limit,
)

SOURCE = "preprints"

_CSH_BASE = "https://api.biorxiv.org/details"
_EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

SERVERS = ("medrxiv", "biorxiv")

# Cold Spring Harbor's DOI prefix; both servers mint under it.
_CSH_PREFIX = "10.1101/"

# The native API returns 100 records per cursor page, fixed.
_CSH_PAGE = 100
_EPMC_PAGE = 100
_ENRICH_WORKERS = 10


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Keyword-search medRxiv and bioRxiv preprints.

    Raises:
        http.SourceError: if the preprint index is unreachable.
    """
    limit = resolve_limit(max_results)
    records = _search_preprint_index(query, limit)[:limit]

    if records:
        workers = min(_ENRICH_WORKERS, len(records))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_enrich_from_csh, records))

    for record in records:
        record.source = SOURCE
        record.sources = [SOURCE]
        record.retrieved_query = query
    return records


def scan_by_date(query_terms: Iterable[str],
                 server: str = "medrxiv",
                 start: str | None = None,
                 end: str | None = None,
                 max_results: int | None = None,
                 max_pages: int = 20) -> list[StudyRecord]:
    """Walk the native CSH API over a date window, filtering client-side.

    Args:
        query_terms: all terms must appear in the title or abstract.
        server: "medrxiv" or "biorxiv".
        start / end: ISO dates; defaults to the trailing 180 days.
        max_results: cap on matches returned.
        max_pages: cap on 100-record pages fetched, so a broad window cannot
            turn into a thousand-request crawl.

    Raises:
        http.SourceError: if the CSH API is unreachable.
    """
    if server not in SERVERS:
        raise ValueError(f"unknown preprint server: {server}")

    limit = resolve_limit(max_results)
    end_date = end or date.today().isoformat()
    start_date = start or (date.today() - timedelta(days=180)).isoformat()
    terms = [t.lower() for t in query_terms if t]

    records: list[StudyRecord] = []
    cursor = 0
    for _ in range(max_pages):
        url = f"{_CSH_BASE}/{server}/{start_date}/{end_date}/{cursor}/json"
        payload = http.request_json(SOURCE, url)
        collection = (payload or {}).get("collection") or []
        if not collection:
            break

        for item in collection:
            haystack = (f"{item.get('title', '')} "
                        f"{item.get('abstract', '')}").lower()
            if terms and not all(term in haystack for term in terms):
                continue
            record = _from_csh(item, server)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = " ".join(terms)
            records.append(record)
            if len(records) >= limit:
                return records

        if len(collection) < _CSH_PAGE:
            break
        cursor += _CSH_PAGE

    return records


def fetch_preprint(doi: str) -> StudyRecord | None:
    """Look up one preprint DOI on whichever CSH server hosts it."""
    canonical = normalise_doi(doi)
    if not canonical:
        return None
    for server in SERVERS:
        item = _csh_detail(server, canonical)
        if item:
            record = _from_csh(item, server)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = canonical
            return record
    return None


def published_doi(preprint_doi: str) -> str | None:
    """The journal DOI a preprint became, if any.

    Callers use this to collapse preprint/journal duplicates before pooling.
    """
    canonical = normalise_doi(preprint_doi)
    if not canonical:
        return None
    for server in SERVERS:
        item = _csh_detail(server, canonical)
        if item:
            return normalise_doi(item.get("published"))
    return None


# --------------------------------------------------------------------------
# Europe PMC preprint index
# --------------------------------------------------------------------------


def _search_preprint_index(query: str, limit: int) -> list[StudyRecord]:
    """Query the SRC:PPR index and keep only CSH-hosted preprints."""
    records: list[StudyRecord] = []
    cursor = "*"
    # Over-fetch: the index carries preprints from many servers (Research
    # Square, SSRN, Authorea...) and only the 10.1101 ones are medRxiv or
    # bioRxiv. The floor of 200 stops a small max_results from giving up
    # after a single page of non-CSH hits.
    budget = min(max(limit * 10, 200), 1000)
    seen = 0

    while len(records) < limit and seen < budget:
        params = {
            "query": f"({query}) AND (SRC:PPR)",
            "format": "json",
            "resultType": "core",
            "pageSize": _EPMC_PAGE,
            "cursorMark": cursor,
        }
        payload = http.request_json(SOURCE, _EPMC_SEARCH, params)
        results = ((payload or {}).get("resultList") or {}).get("result") or []
        if not results:
            break
        seen += len(results)

        for item in results:
            doi = normalise_doi(item.get("doi"))
            if not doi or not doi.startswith(_CSH_PREFIX):
                continue
            records.append(_from_epmc(item, doi))
            if len(records) >= limit:
                break

        next_cursor = (payload or {}).get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return records


def _from_epmc(item: dict[str, Any], doi: str) -> StudyRecord:
    authors = [clean_text(a.get("fullName"))
               for a in ((item.get("authorList") or {}).get("author") or [])]
    authors = [a for a in authors if a]
    if not authors:
        authors = [a.strip() for a in (item.get("authorString") or "").split(",")
                   if a.strip()]

    return StudyRecord(
        doi=doi,
        pmid=None,
        title=clean_text(item.get("title")),
        abstract=clean_text(item.get("abstractText")),
        authors=authors,
        journal=clean_text((item.get("bookOrReportDetails") or {}).get(
            "publisher") or "Preprint"),
        year=parse_year(item.get("pubYear") or item.get("firstPublicationDate")),
        publication_types=["Preprint"],
        keywords=dedupe_preserving_order(
            clean_text(k) for k in
            ((item.get("keywordList") or {}).get("keyword") or [])),
        url=f"https://doi.org/{doi}",
        is_open_access=True,  # every CSH preprint is freely readable
        full_text_url=f"https://doi.org/{doi}",
        cited_by_count=item.get("citedByCount"),
    )


# --------------------------------------------------------------------------
# Native Cold Spring Harbor API
# --------------------------------------------------------------------------


def _csh_detail(server: str, doi: str) -> dict[str, Any] | None:
    """Latest version record for a DOI, or None if that server lacks it.

    Retries are capped because probing the wrong server (medRxiv for a
    bioRxiv DOI) is an expected half of this lookup, not a transient fault.
    """
    try:
        payload = http.request_json(
            SOURCE, f"{_CSH_BASE}/{server}/{doi}/na/json", max_retries=2)
    except http.SourceError:
        return None
    collection = (payload or {}).get("collection") or []
    return collection[-1] if collection else None


def _enrich_from_csh(record: StudyRecord) -> None:
    """Add version, category and published-journal DOI from the native API.

    Failures are ignored: the record is already usable, this only sharpens it.
    """
    if not record.doi:
        return
    server = "medrxiv" if _looks_medical(record) else "biorxiv"
    item = _csh_detail(server, record.doi)
    if item is None:
        other = "biorxiv" if server == "medrxiv" else "medrxiv"
        item = _csh_detail(other, record.doi)
        server = other
    if not item:
        return

    if not record.abstract:
        record.abstract = clean_text(item.get("abstract"))
    record.journal = f"{server} (preprint)"
    record.year = record.year or parse_year(item.get("date"))
    extras = [f"category:{item.get('category')}" if item.get("category") else "",
              f"version:{item.get('version')}" if item.get("version") else ""]
    record.keywords = dedupe_preserving_order(
        record.keywords + [e for e in extras if e])

    published = normalise_doi(item.get("published"))
    if published:
        # Flag the journal version so the dedup stage can drop one of the two.
        record.references = dedupe_preserving_order(
            record.references + [published])
        record.publication_types = dedupe_preserving_order(
            record.publication_types + ["Preprint (subsequently published)"])


def _looks_medical(record: StudyRecord) -> bool:
    """Cheap server guess so enrichment usually needs only one request."""
    journal = (record.journal or "").lower()
    if "biorxiv" in journal:
        return False
    if "medrxiv" in journal:
        return True
    text = f"{record.title} {journal}".lower()
    return any(
        term in text for term in
        ("patient", "clinical", "trial", "cohort", "randomis", "randomiz"))


def _from_csh(item: dict[str, Any], server: str) -> StudyRecord:
    doi = normalise_doi(item.get("doi"))
    published = normalise_doi(item.get("published"))
    pub_types = ["Preprint"]
    if published:
        pub_types.append("Preprint (subsequently published)")

    return StudyRecord(
        doi=doi,
        title=clean_text(item.get("title")),
        abstract=clean_text(item.get("abstract")),
        authors=[a.strip() for a in (item.get("authors") or "").split(";")
                 if a.strip()],
        journal=f"{server} (preprint)",
        year=parse_year(item.get("date")),
        publication_types=pub_types,
        keywords=dedupe_preserving_order([
            f"category:{item.get('category')}" if item.get("category") else "",
            f"version:{item.get('version')}" if item.get("version") else "",
        ]),
        url=f"https://doi.org/{doi}" if doi else "",
        is_open_access=True,
        full_text_url=item.get("jatsxml") or (
            f"https://doi.org/{doi}" if doi else None),
        references=[published] if published else [],
    )
