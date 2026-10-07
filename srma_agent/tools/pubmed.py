"""PubMed / MEDLINE connector via NCBI E-Utilities.

PubMed is the mandatory backbone of any biomedical systematic review, and it
is the only source here that exposes MeSH indexing and PublicationType tags.
Those two fields drive study-design eligibility filtering downstream, so this
connector parses the full efetch XML rather than the thinner esummary JSON.

The two-step esearch -> efetch dance is deliberate: esearch honours the
PubMed query grammar (MeSH terms, field tags, booleans) that reviewers write
in their protocol, while efetch is the only endpoint returning abstracts.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .. import config
from ..schemas import StudyRecord
from . import http
from ._common import (
    chunked,
    clean_text,
    dedupe_preserving_order,
    normalise_doi,
    normalise_pmcid,
    normalise_pmid,
    parse_year,
    resolve_limit,
)

SOURCE = "pubmed"

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ESEARCH = f"{_BASE}/esearch.fcgi"
_EFETCH = f"{_BASE}/efetch.fcgi"

# NCBI rejects very long URLs; 200 PMIDs per efetch stays well inside limits.
_EFETCH_BATCH = 200


def _etiquette_params() -> dict[str, str]:
    """NCBI requires `tool` and `email`; an api_key lifts 3/sec to 10/sec."""
    params = {"tool": "SRMA-Agent", "email": config.CONTACT_EMAIL}
    if config.NCBI_API_KEY:
        params["api_key"] = config.NCBI_API_KEY
    return params


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Search PubMed and return fully populated records.

    Raises:
        http.SourceError: if NCBI is unreachable or returns malformed data.
    """
    limit = resolve_limit(max_results)
    pmids = search_pmids(query, limit)
    if not pmids:
        return []

    records = fetch_by_pmids(pmids)
    for record in records:
        record.source = SOURCE
        record.sources = [SOURCE]
        record.retrieved_query = query
    return records


def search_pmids(query: str, max_results: int | None = None) -> list[str]:
    """Return only PMIDs, for callers that just need an identifier set."""
    limit = resolve_limit(max_results)
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
        "sort": "relevance",
        **_etiquette_params(),
    }
    payload = http.request_json(SOURCE, _ESEARCH, params)
    result = (payload or {}).get("esearchresult") or {}
    if "ERROR" in result:
        raise http.SourceError(f"{SOURCE}: esearch error: {result['ERROR']}")
    return [str(pmid) for pmid in result.get("idlist", [])][:limit]


def fetch_by_pmids(pmids: list[str]) -> list[StudyRecord]:
    """Fetch and parse full MEDLINE XML for an explicit PMID list."""
    records: list[StudyRecord] = []
    for batch in chunked([p for p in pmids if p], _EFETCH_BATCH):
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            **_etiquette_params(),
        }
        xml_text = http.request_json(
            SOURCE, _EFETCH, params,
            headers={"Accept": "application/xml"},
            expect_json=False,
        )
        records.extend(_parse_efetch_xml(xml_text))
    return records


# --------------------------------------------------------------------------
# XML parsing
# --------------------------------------------------------------------------


def _text(node: ET.Element | None) -> str:
    """Concatenate all descendant text; MEDLINE titles contain inline markup."""
    if node is None:
        return ""
    return clean_text("".join(node.itertext()))


def _parse_efetch_xml(xml_text: str) -> list[StudyRecord]:
    """Convert an efetch PubmedArticleSet into StudyRecords."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise http.SourceError(f"{SOURCE}: unparseable efetch XML: {exc}") from exc

    records: list[StudyRecord] = []
    for article in root.findall(".//PubmedArticle"):
        parsed = _parse_article(article)
        if parsed is not None:
            records.append(parsed)
    # Book chapters (rare in searches) still carry usable metadata.
    for book in root.findall(".//PubmedBookArticle"):
        parsed = _parse_book(book)
        if parsed is not None:
            records.append(parsed)
    return records


def _parse_article(article: ET.Element) -> StudyRecord | None:
    citation = article.find("MedlineCitation")
    if citation is None:
        return None
    art = citation.find("Article")

    pmid = normalise_pmid(_text(citation.find("PMID")))
    ids = _article_ids(article)
    doi = ids.get("doi") or normalise_doi(
        _first_elocation_doi(art)
    )

    record = StudyRecord(
        pmid=pmid,
        doi=doi,
        pmcid=ids.get("pmc"),
        title=_text(art.find("ArticleTitle")) if art is not None else "",
        abstract=_abstract(art),
        authors=_authors(art),
        journal=_journal(art, citation),
        year=_year(art, article),
        publication_types=_publication_types(art),
        mesh_terms=_mesh_terms(citation),
        keywords=_keywords(citation),
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    )
    if record.pmcid:
        # A PMCID means PubMed Central holds a free full text.
        record.is_open_access = True
        record.full_text_url = (
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{record.pmcid}/"
        )
    return record


def _parse_book(book: ET.Element) -> StudyRecord | None:
    citation = book.find("BookDocument")
    if citation is None:
        return None
    pmid = normalise_pmid(_text(citation.find("PMID")))
    book_el = citation.find("Book")
    return StudyRecord(
        pmid=pmid,
        doi=_article_ids(book).get("doi"),
        title=_text(citation.find("ArticleTitle")) or _text(
            book_el.find("BookTitle") if book_el is not None else None),
        abstract=_abstract(citation),
        authors=_authors(citation),
        journal=_text(book_el.find("Publisher/PublisherName"))
        if book_el is not None else "",
        year=parse_year(_text(book_el.find("PubDate/Year"))
                        if book_el is not None else None),
        publication_types=["Book"],
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    )


def _article_ids(article: ET.Element) -> dict[str, str]:
    """Map ArticleIdList entries (doi, pmc, pubmed...) to normalised values."""
    out: dict[str, str] = {}
    for aid in article.findall(".//ArticleIdList/ArticleId"):
        id_type = (aid.get("IdType") or "").lower()
        raw = (aid.text or "").strip()
        if id_type == "doi":
            doi = normalise_doi(raw)
            if doi:
                out["doi"] = doi
        elif id_type == "pmc":
            pmcid = normalise_pmcid(raw)
            if pmcid:
                out["pmc"] = pmcid
    return out


def _first_elocation_doi(art: ET.Element | None) -> str | None:
    if art is None:
        return None
    for el in art.findall("ELocationID"):
        if (el.get("EIdType") or "").lower() == "doi":
            return el.text
    return None


def _abstract(art: ET.Element | None) -> str:
    """Join labelled abstract sections, keeping the structure LLMs rely on."""
    if art is None:
        return ""
    parts: list[str] = []
    for node in art.findall(".//Abstract/AbstractText"):
        text = _text(node)
        if not text:
            continue
        label = node.get("Label")
        parts.append(f"{label.strip().title()}: {text}" if label else text)
    if not parts:
        other = art.find(".//OtherAbstract")
        if other is not None:
            parts.append(_text(other))
    return " ".join(parts).strip()


def _authors(art: ET.Element | None) -> list[str]:
    if art is None:
        return []
    names: list[str] = []
    for author in art.findall(".//AuthorList/Author"):
        collective = _text(author.find("CollectiveName"))
        if collective:
            names.append(collective)
            continue
        last = _text(author.find("LastName"))
        fore = _text(author.find("ForeName")) or _text(author.find("Initials"))
        full = f"{fore} {last}".strip()
        if full:
            names.append(full)
    return names


def _journal(art: ET.Element | None, citation: ET.Element) -> str:
    if art is not None:
        title = _text(art.find("Journal/Title"))
        if title:
            return title
        iso = _text(art.find("Journal/ISOAbbreviation"))
        if iso:
            return iso
    return _text(citation.find("MedlineJournalInfo/MedlineTA"))


def _year(art: ET.Element | None, article: ET.Element) -> int | None:
    if art is not None:
        year = parse_year(_text(art.find("Journal/JournalIssue/PubDate/Year")))
        if year:
            return year
        medline_date = _text(
            art.find("Journal/JournalIssue/PubDate/MedlineDate"))
        year = parse_year(medline_date)
        if year:
            return year
        year = parse_year(_text(art.find("ArticleDate/Year")))
        if year:
            return year
    for tag in ("PubMedPubDate", "DateCompleted", "DateRevised"):
        node = article.find(f".//{tag}/Year")
        year = parse_year(_text(node))
        if year:
            return year
    return None


def _publication_types(art: ET.Element | None) -> list[str]:
    if art is None:
        return []
    return dedupe_preserving_order(
        _text(pt) for pt in art.findall(".//PublicationTypeList/PublicationType")
    )


def _mesh_terms(citation: ET.Element) -> list[str]:
    """Descriptor plus its qualifiers, e.g. 'Aspirin/therapeutic use'."""
    terms: list[str] = []
    for heading in citation.findall(".//MeshHeadingList/MeshHeading"):
        descriptor = _text(heading.find("DescriptorName"))
        if not descriptor:
            continue
        qualifiers = [_text(q) for q in heading.findall("QualifierName")]
        qualifiers = [q for q in qualifiers if q]
        if qualifiers:
            terms.extend(f"{descriptor}/{q}" for q in qualifiers)
        else:
            terms.append(descriptor)
    return dedupe_preserving_order(terms)


def _keywords(citation: ET.Element) -> list[str]:
    return dedupe_preserving_order(
        _text(kw) for kw in citation.findall(".//KeywordList/Keyword")
    )
