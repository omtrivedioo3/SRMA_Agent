"""ClinicalTrials.gov connector (API v2).

Trial registries are the only systematic defence against outcome-reporting
bias: a registered trial that never published is invisible to PubMed but
visible here. The spec therefore treats registry records as first-class
evidence, and `has_results` plus the linked-publication list are what let the
pipeline flag "registered, completed, never published" studies.
"""

from __future__ import annotations

import re
from typing import Any

from ..schemas import StudyRecord
from . import http
from ._common import (
    clean_text,
    dedupe_preserving_order,
    normalise_doi,
    normalise_nct,
    normalise_pmid,
    parse_year,
    resolve_limit,
)

SOURCE = "clinicaltrials"

_BASE = "https://clinicaltrials.gov/api/v2"
_STUDIES = f"{_BASE}/studies"

# API v2 caps pageSize at 1000.
_PAGE_SIZE = 100

# Citation strings are free text; this is the only way to recover a DOI.
_DOI_IN_TEXT = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>,;]+)", re.IGNORECASE)


def search(query: str, max_results: int | None = None) -> list[StudyRecord]:
    """Search the registry with a free-text expression.

    Raises:
        http.SourceError: if ClinicalTrials.gov is unreachable.
    """
    limit = resolve_limit(max_results)
    records: list[StudyRecord] = []
    page_token: str | None = None

    while len(records) < limit:
        params: dict[str, Any] = {
            "query.term": query,
            "pageSize": min(_PAGE_SIZE, limit - len(records)),
            "format": "json",
            "countTotal": "true",
        }
        if page_token:
            params["pageToken"] = page_token

        payload = http.request_json(SOURCE, _STUDIES, params)
        studies = (payload or {}).get("studies") or []
        if not studies:
            break

        for study in studies:
            record = _to_record(study)
            record.source = SOURCE
            record.sources = [SOURCE]
            record.retrieved_query = query
            records.append(record)

        page_token = (payload or {}).get("nextPageToken")
        if not page_token:
            break

    return records[:limit]


def fetch_study(nct_id: str) -> StudyRecord | None:
    """Fetch a single registration by NCT number."""
    canonical = normalise_nct(nct_id)
    if not canonical:
        return None
    payload = http.request_json(
        SOURCE, f"{_STUDIES}/{canonical}", {"format": "json"})
    if not payload:
        return None
    record = _to_record(payload)
    record.source = SOURCE
    record.sources = [SOURCE]
    record.retrieved_query = canonical
    return record


def linked_publications(record: StudyRecord) -> dict[str, list[str]]:
    """PMIDs and DOIs a trial declares, for cross-registry deduplication."""
    return {
        "pmids": [p for p in record.keywords if p.isdigit()],
        "dois": list(record.references),
    }


# --------------------------------------------------------------------------
# Mapping
# --------------------------------------------------------------------------


def _to_record(study: dict[str, Any]) -> StudyRecord:
    protocol = study.get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    description = protocol.get("descriptionModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}

    nct_id = normalise_nct(ident.get("nctId"))
    pmids, dois = _linked_ids(protocol)

    return StudyRecord(
        nct_id=nct_id,
        # A registry record is not itself a publication; the first linked
        # PMID is recorded so dedup can collapse it onto the journal article.
        pmid=pmids[0] if pmids else None,
        doi=dois[0] if dois else None,
        title=clean_text(ident.get("briefTitle")
                         or ident.get("officialTitle")),
        abstract=clean_text(description.get("briefSummary")),
        authors=_investigators(sponsor, protocol),
        journal="ClinicalTrials.gov",
        year=_year(status),
        publication_types=_publication_types(design),
        keywords=dedupe_preserving_order(
            [clean_text(c) for c in conditions.get("conditions") or []]
            + [clean_text(k) for k in conditions.get("keywords") or []]
            + pmids),
        url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        is_open_access=True,  # registry records are always publicly readable
        full_text_url=(f"https://clinicaltrials.gov/study/{nct_id}"
                       if nct_id else None),
        references=dois,
        trial_status=clean_text(status.get("overallStatus")) or None,
        enrollment=_enrollment(design),
        has_results=bool(study.get("hasResults")),
    )


def _enrollment(design: dict[str, Any]) -> int | None:
    info = design.get("enrollmentInfo") or {}
    count = info.get("count")
    try:
        return int(count) if count is not None else None
    except (TypeError, ValueError):
        return None


def _year(status: dict[str, Any]) -> int | None:
    """Prefer start date; a trial's "year" is when it ran, not when posted."""
    for key in ("startDateStruct", "primaryCompletionDateStruct",
                "completionDateStruct"):
        year = parse_year((status.get(key) or {}).get("date"))
        if year:
            return year
    return parse_year(status.get("studyFirstSubmitDate"))


def _publication_types(design: dict[str, Any]) -> list[str]:
    types = ["Clinical Trial Registration"]
    study_type = clean_text(design.get("studyType"))
    if study_type:
        types.append(study_type.title())
    for phase in design.get("phases") or []:
        cleaned = clean_text(phase)
        if cleaned:
            types.append(cleaned.replace("_", " ").title())
    allocation = ((design.get("designInfo") or {}).get("allocation") or "")
    if "RANDOMIZED" in allocation.upper() and "NON" not in allocation.upper():
        types.append("Randomized Controlled Trial")
    return dedupe_preserving_order(types)


def _investigators(sponsor: dict[str, Any],
                   protocol: dict[str, Any]) -> list[str]:
    """Registries name sponsors and officials rather than authors."""
    names: list[str] = []
    lead = (sponsor.get("leadSponsor") or {}).get("name")
    if lead:
        names.append(clean_text(lead))
    contacts = protocol.get("contactsLocationsModule") or {}
    for official in contacts.get("overallOfficials") or []:
        name = clean_text(official.get("name"))
        if name:
            names.append(name)
    return dedupe_preserving_order(names)


def _linked_ids(protocol: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Publications the trial itself points at, as (pmids, dois)."""
    references = (protocol.get("referencesModule") or {}).get(
        "references") or []
    pmids: list[str] = []
    dois: list[str] = []
    for ref in references:
        pmid = normalise_pmid(ref.get("pmid"))
        if pmid:
            pmids.append(pmid)
        for candidate in _DOI_IN_TEXT.findall(ref.get("citation") or ""):
            doi = normalise_doi(candidate)
            if doi:
                dois.append(doi)
    return dedupe_preserving_order(pmids), dedupe_preserving_order(dois)
