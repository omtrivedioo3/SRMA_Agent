"""Deduplication across literature sources (PRISMA Phase 3).

The same trial appears in PubMed, Europe PMC, OpenAlex and Crossref under
different identifiers. Counting it four times would inflate the evidence
base, so records are merged before screening.

Matching runs in decreasing order of confidence:

  1. DOI        - a global unique identifier. Exact match is definitive.
  2. PMID       - unique within PubMed/MEDLINE.
  3. PMCID      - unique within PubMed Central.
  4. NCT ID     - links a publication to its trial registration.
  5. Normalised title + year - the fuzzy fallback, for records that carry
     no shared identifier at all.

Merging is union-preserving: when two records describe the same study, the
result keeps the longest abstract, the largest author list, and the union of
their identifiers and source names. Nothing is silently discarded, because
the PRISMA flow diagram must account for every record.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from ..schemas import StudyRecord

# Title similarity above which two records are considered the same study.
# 0.92 is deliberately conservative: a false merge loses a real study, which
# is worse than leaving a duplicate for the screening stage to catch.
TITLE_SIMILARITY_THRESHOLD = 0.92

_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")

# Dropped before comparison: they add no discriminating signal but do add noise.
_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with",
    "randomized", "randomised", "trial", "study", "controlled", "double",
    "blind", "placebo", "versus", "vs", "effect", "effects",
}


def normalise_doi(doi: str | None) -> str | None:
    """Reduce a DOI to a comparable canonical form."""
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip("/") or None


def normalise_title(title: str) -> str:
    """Aggressively normalise a title for fuzzy comparison.

    Strips accents, punctuation, case and boilerplate words so that
    'Aspirin vs. Placebo: A Randomized Trial' and
    'Aspirin versus placebo - a randomised trial' collapse to the same string.
    """
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _PUNCT_RE.sub(" ", t.lower())
    tokens = [w for w in _WS_RE.split(t) if w and w not in _STOPWORDS]
    return " ".join(tokens)


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _merge(primary: StudyRecord, other: StudyRecord) -> StudyRecord:
    """Fold `other` into `primary`, keeping the richest value for each field."""
    # Identifiers: fill any gap.
    for attr in ("doi", "pmid", "pmcid", "nct_id", "openalex_id"):
        if not getattr(primary, attr) and getattr(other, attr):
            setattr(primary, attr, getattr(other, attr))

    # Text: longer wins, on the assumption it is less truncated.
    if len(other.abstract or "") > len(primary.abstract or ""):
        primary.abstract = other.abstract
    if len(other.title or "") > len(primary.title or ""):
        primary.title = other.title
    if len(other.authors) > len(primary.authors):
        primary.authors = other.authors

    # Scalars: fill gaps only.
    for attr in ("journal", "year", "url", "full_text_url",
                 "trial_status", "enrollment", "has_results"):
        if not getattr(primary, attr) and getattr(other, attr):
            setattr(primary, attr, getattr(other, attr))

    # Lists: union, order-preserving.
    for attr in ("publication_types", "mesh_terms", "keywords",
                 "sources", "references"):
        merged = list(getattr(primary, attr))
        for item in getattr(other, attr):
            if item not in merged:
                merged.append(item)
        setattr(primary, attr, merged)

    # Flags and counts: most favourable / most informative value.
    primary.is_open_access = primary.is_open_access or other.is_open_access
    if other.cited_by_count is not None:
        primary.cited_by_count = max(primary.cited_by_count or 0,
                                     other.cited_by_count)
    return primary


def deduplicate(
    records: list[StudyRecord],
    *,
    fuzzy_titles: bool = True,
) -> tuple[list[StudyRecord], dict[str, Any]]:
    """Collapse duplicate records across sources.

    Args:
        records: Pooled records from every source.
        fuzzy_titles: Enable title+year matching for records with no shared ID.
            Disable for a strictly identifier-based, fully reproducible pass.

    Returns:
        (unique_records, report) where report carries the counts the PRISMA
        flow diagram needs.
    """
    unique: list[StudyRecord] = []
    # Exact-identifier indexes -> position in `unique`.
    by_id: dict[tuple[str, str], int] = {}
    # Fuzzy index keyed by year, to avoid comparing every title to every other.
    by_year: dict[int | None, list[int]] = {}

    matched_by = {"doi": 0, "pmid": 0, "pmcid": 0, "nct_id": 0, "title": 0}
    removed_duplicates: list[dict[str, Any]] = []

    for rec in records:
        rec.doi = normalise_doi(rec.doi)
        if rec.source and rec.source not in rec.sources:
            rec.sources.append(rec.source)

        hit: int | None = None
        hit_kind: str | None = None

        # --- pass 1: exact identifier match -------------------------------
        for kind in ("doi", "pmid", "pmcid", "nct_id"):
            value = getattr(rec, kind)
            if value and (kind, str(value)) in by_id:
                hit = by_id[(kind, str(value))]
                hit_kind = kind
                break

        # --- pass 2: fuzzy title match within the same year ---------------
        if hit is None and fuzzy_titles:
            norm = normalise_title(rec.title)
            if norm:
                # Compare against same year, and adjacent years to tolerate
                # the online-first vs print publication date discrepancy.
                candidates: list[int] = []
                for yr in {rec.year, (rec.year or 0) - 1, (rec.year or 0) + 1}:
                    candidates.extend(by_year.get(yr, []))
                for idx in candidates:
                    if _title_similarity(
                        norm, normalise_title(unique[idx].title)
                    ) >= TITLE_SIMILARITY_THRESHOLD:
                        hit, hit_kind = idx, "title"
                        break

        if hit is not None:
            dup_id = rec.best_id
            dup_source = rec.source or (", ".join(rec.sources) if rec.sources else "unknown")
            dup_url = rec.verification_url
            primary_before = unique[hit].best_id
            _merge(unique[hit], rec)
            matched_by[hit_kind] += 1  # type: ignore[index]
            removed_duplicates.append({
                "duplicate_id": dup_id,
                "duplicate_source": dup_source,
                "title": (rec.title or "")[:180],
                "merged_into_id": unique[hit].best_id or primary_before,
                "merged_sources": list(unique[hit].sources),
                "matched_on": hit_kind,
                "url": dup_url or unique[hit].verification_url,
            })
            # Newly merged identifiers must also become lookup keys.
            _index(unique[hit], hit, by_id)
            continue

        # --- new unique record --------------------------------------------
        unique.append(rec)
        idx = len(unique) - 1
        _index(rec, idx, by_id)
        by_year.setdefault(rec.year, []).append(idx)

    report = {
        "input_count": len(records),
        "unique_count": len(unique),
        "duplicates_removed": len(records) - len(unique),
        "matched_by": matched_by,
        "removed_duplicates": removed_duplicates,
        "records_with_doi": sum(1 for r in unique if r.doi),
        "records_with_pmid": sum(1 for r in unique if r.pmid),
        "records_without_identifier": sum(
            1 for r in unique
            if not (r.doi or r.pmid or r.pmcid or r.nct_id)
        ),
    }
    return unique, report


def _index(rec: StudyRecord, idx: int, by_id: dict[tuple[str, str], int]) -> None:
    """Register every identifier a record carries."""
    for kind in ("doi", "pmid", "pmcid", "nct_id"):
        value = getattr(rec, kind)
        if value:
            by_id.setdefault((kind, str(value)), idx)
