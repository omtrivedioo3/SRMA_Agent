"""Europe PMC connector.

Europe PMC indexes MEDLINE plus content PubMed does not carry: preprints,
Agricola, patents, NHS guidance and, crucially for this pipeline, a large
open-access full-text corpus. Full text matters because risk-of-bias
assessment needs the Methods section, which an abstract never contains.

`resultType=core` is requested throughout: the default `lite` response omits
abstracts, MeSH headings and full-text links, which would force a second
round trip per record.
"""

from __future__ import annotations

from typing import Any

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

SOURCE = "europepmc"

_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_SEARCH = f"{_BASE}/search"

# Europe PMC caps pageSize at 1000, but 100 keeps responses small and lets
# the cursorMark loop fail cheaply.
_PAGE_SIZE = 100


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Search Europe PMC, paging with cursorMark until the cap is reached.

    Raises:
        http.SourceError: if the REST service is unreachable.
    """
    limit = resolve_limit(max_results)
    records: list[StudyRecord] = []
    cursor = "*"

    while len(records) < limit:
        params = {
            "query": query,
            "format": "json",
            "resultType": "core",
            "pageSize": min(_PAGE_SIZE, limit - len(records)),
            "cursorMark": cursor,
        }
        payload = http.request_json(SOURCE, _SEARCH, params)
        results = ((payload or {}).get("resultList") or {}).get("result") or []
        if not results:
            break

        for item in results:
            record = _to_record(item)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = query
            records.append(record)

        next_cursor = (payload or {}).get("nextCursorMark")
        # Europe PMC repeats the cursor on the final page; that is the signal
        # to stop, otherwise this loops forever.
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return records[:limit]


def fetch_full_text_xml(pmcid: str) -> str | None:
    """Return open-access full-text JATS XML, or None when not available.

    Only a subset of PMC records are in the OA subset; a miss is an expected
    outcome rather than an error, so this returns None instead of raising.
    """
    canonical = normalise_pmcid(pmcid)
    if not canonical:
        return None
    try:
        xml_text = http.request_json(
            SOURCE,
            f"{_BASE}/{canonical}/fullTextXML",
            headers={"Accept": "application/xml"},
            expect_json=False,
            max_retries=2,
        )
    except http.SourceError:
        return None
    if not xml_text or "<" not in xml_text:
        return None
    return xml_text


def fetch_full_text(pmcid: str) -> str | None:
    """Plain-text rendering of the open-access full text, for LLM prompts."""
    xml_text = fetch_full_text_xml(pmcid)
    return clean_text(xml_text) if xml_text else None


def fetch_references(record_id: str, source_db: str = "MED",
                     max_results: int | None = None) -> list[StudyRecord]:
    """Backward citations (reference list) for one Europe PMC record."""
    return _citation_edges("references", record_id, source_db, max_results)


def fetch_citations(record_id: str, source_db: str = "MED",
                    max_results: int | None = None) -> list[StudyRecord]:
    """Forward citations (works citing this record)."""
    return _citation_edges("citations", record_id, source_db, max_results)


def _citation_edges(kind: str, record_id: str, source_db: str,
                    max_results: int | None) -> list[StudyRecord]:
    limit = resolve_limit(max_results)
    url = f"{_BASE}/{source_db}/{record_id}/{kind}"
    payload = http.request_json(
        SOURCE, url, {"format": "json", "pageSize": min(_PAGE_SIZE, limit)})
    container = (payload or {}).get(
        "referenceList" if kind == "references" else "citationList") or {}
    items = container.get(
        "reference" if kind == "references" else "citation") or []

    records: list[StudyRecord] = []
    for item in items[:limit]:
        record = StudyRecord(
            pmid=normalise_pmid(item.get("id") if item.get("source") == "MED"
                                else item.get("pmid")),
            doi=normalise_doi(item.get("doi")),
            title=clean_text(item.get("title")),
            journal=clean_text(item.get("journalAbbreviation")),
            year=parse_year(item.get("pubYear")),
            authors=[a.strip() for a in
                     (item.get("authorString") or "").split(",") if a.strip()],
            cited_by_count=item.get("citedByCount"),
            source=SOURCE,
            sources=[SOURCE],
            retrieved_query=f"{kind}:{source_db}/{record_id}",
        )
        records.append(record)
    return records


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _to_record(item: dict[str, Any]) -> StudyRecord:
    pmid = normalise_pmid(item.get("pmid"))
    pmcid = normalise_pmcid(item.get("pmcid"))
    doi = normalise_doi(item.get("doi"))
    is_oa = str(item.get("isOpenAccess", "")).upper() == "Y"

    return StudyRecord(
        doi=doi,
        pmid=pmid,
        pmcid=pmcid,
        title=clean_text(item.get("title")),
        abstract=clean_text(item.get("abstractText")),
        authors=_authors(item),
        journal=clean_text(
            ((item.get("journalInfo") or {}).get("journal") or {}).get("title")
            or (item.get("bookOrReportDetails") or {}).get("publisher") or ""),
        year=parse_year(item.get("pubYear")
                        or (item.get("journalInfo") or {}).get(
                            "yearOfPublication")),
        publication_types=_pub_types(item),
        mesh_terms=_mesh(item),
        keywords=dedupe_preserving_order(
            clean_text(k) for k in
            ((item.get("keywordList") or {}).get("keyword") or [])),
        url=_landing_url(item, pmcid, pmid, doi),
        is_open_access=is_oa,
        full_text_url=_full_text_url(item, pmcid, is_oa),
        cited_by_count=item.get("citedByCount"),
    )


def _authors(item: dict[str, Any]) -> list[str]:
    author_list = ((item.get("authorList") or {}).get("author") or [])
    names = [clean_text(a.get("fullName") or a.get("collectiveName"))
             for a in author_list]
    names = [n for n in names if n]
    if names:
        return names
    return [a.strip() for a in (item.get("authorString") or "").split(",")
            if a.strip()]


def _pub_types(item: dict[str, Any]) -> list[str]:
    types = ((item.get("pubTypeList") or {}).get("pubType") or [])
    return dedupe_preserving_order(clean_text(t) for t in types)


def _mesh(item: dict[str, Any]) -> list[str]:
    headings = ((item.get("meshHeadingList") or {}).get("meshHeading") or [])
    terms: list[str] = []
    for heading in headings:
        descriptor = clean_text(heading.get("descriptorName"))
        if not descriptor:
            continue
        qualifiers = ((heading.get("meshQualifierList") or {})
                      .get("meshQualifier") or [])
        names = [clean_text(q.get("qualifierName")) for q in qualifiers]
        names = [n for n in names if n]
        if names:
            terms.extend(f"{descriptor}/{n}" for n in names)
        else:
            terms.append(descriptor)
    return dedupe_preserving_order(terms)


def _landing_url(item: dict[str, Any], pmcid: str | None,
                 pmid: str | None, doi: str | None) -> str:
    source_db = item.get("source")
    ident = item.get("id")
    if source_db and ident:
        return f"https://europepmc.org/article/{source_db}/{ident}"
    if pmcid:
        return f"https://europepmc.org/article/PMC/{pmcid}"
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return f"https://doi.org/{doi}" if doi else ""


def _full_text_url(item: dict[str, Any], pmcid: str | None,
                   is_oa: bool) -> str | None:
    """Prefer a declared free full-text link; fall back to the PMC landing."""
    urls = ((item.get("fullTextUrlList") or {}).get("fullTextUrl") or [])
    for entry in urls:
        availability = (entry.get("availability") or "").lower()
        if availability in ("open access", "free") and entry.get("url"):
            return entry["url"]
    if is_oa and pmcid:
        return f"https://europepmc.org/article/PMC/{pmcid}"
    return None
