"""Normalisation helpers shared by every source connector.

These live in one place because deduplication only works if all nine sources
agree on exactly what a "DOI" or a "year" looks like. A DOI that differs only
by case or by an `https://doi.org/` prefix would otherwise survive dedup and
be double-counted in the meta-analysis, which is a correctness bug, not a
cosmetic one.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .. import config

# Matches every prefix form publishers use to express a DOI as a URL.
_DOI_PREFIX = re.compile(
    r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi:|info:doi/)\s*", re.IGNORECASE
)
_WHITESPACE = re.compile(r"\s+")
# Deliberately narrow: `<[^>]+>` would swallow real text such as
# "p<0.05 and n>10", which is common in clinical abstracts and would
# silently delete an effect estimate.
_JATS_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9:_.-]*(?:\s[^<>]*?)?/?>")
_YEAR = re.compile(r"(1[6-9]\d{2}|20\d{2}|21\d{2})")


def normalise_doi(value: Any) -> str | None:
    """Return a bare, lowercase DOI, or None if `value` is not a DOI.

    Case-folding is safe: the DOI handbook declares DOIs case-insensitive.
    """
    if not value:
        return None
    doi = _DOI_PREFIX.sub("", str(value)).strip().rstrip(".").lower()
    # Strip stray angle brackets and trailing punctuation from scraped text.
    doi = doi.strip("<>").strip()
    return doi if doi.startswith("10.") and "/" in doi else None


def normalise_pmid(value: Any) -> str | None:
    """Return a bare numeric PMID string."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits or None


def normalise_pmcid(value: Any) -> str | None:
    """Return a PMCID in canonical `PMC1234567` form."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return f"PMC{digits}" if digits else None


def normalise_nct(value: Any) -> str | None:
    """Return a trial registration id in canonical `NCT00000000` form."""
    if not value:
        return None
    match = re.search(r"NCT\s*0*?(\d{8})", str(value), re.IGNORECASE)
    return f"NCT{match.group(1)}" if match else None


def clean_text(value: Any) -> str:
    """Flatten markup and whitespace so screening prompts stay readable.

    Crossref and Europe PMC return JATS-tagged abstracts; the LLM does not
    need the tags and they waste context window.
    """
    if not value:
        return ""
    text = _JATS_TAG.sub(" ", str(value))
    text = (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"')
                .replace("&apos;", "'").replace("&#x2019;", "'"))
    return _WHITESPACE.sub(" ", text).strip()


def parse_year(value: Any) -> int | None:
    """Extract a four-digit publication year from any date representation."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1600 < value < 2200 else None
    match = _YEAR.search(str(value))
    return int(match.group(1)) if match else None


def resolve_limit(max_results: int | None) -> int:
    """Apply the configured per-source cap when the caller gives no limit."""
    if max_results is None or max_results <= 0:
        return config.MAX_RECORDS_PER_SOURCE
    return min(int(max_results), config.MAX_RECORDS_PER_SOURCE)


def dedupe_preserving_order(values: Iterable[str]) -> list[str]:
    """Stable de-duplication; ordering matters for reproducible reports."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    """Split a list into fixed-size batches for batched API endpoints."""
    return [items[i:i + size] for i in range(0, len(items), size)]
