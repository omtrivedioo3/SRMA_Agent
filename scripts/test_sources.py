#!/usr/bin/env python3
"""Live smoke test for every data-source connector.

Run with the project venv:

    ./.venv/bin/python scripts/test_sources.py
    ./.venv/bin/python scripts/test_sources.py --query "statins stroke" -n 3

This hits the real APIs on purpose. Mocked tests would not catch the things
that actually break these connectors: silently renamed JSON fields, changed
paging tokens, and rate-limit responses.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Callable

# Allow `python scripts/test_sources.py` from a clean checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from srma_agent.schemas import StudyRecord            # noqa: E402
from srma_agent.tools import (                        # noqa: E402
    clinicaltrials,
    crossref,
    europepmc,
    openalex,
    openfda,
    preprints,
    pubmed,
    semantic_scholar,
    unpaywall,
)
from srma_agent.tools import http                     # noqa: E402

DEFAULT_QUERY = "aspirin myocardial infarction"

# Unpaywall is DOI-keyed, so it gets a DOI instead of a phrase.
_ASPIRIN_DOI = "10.1056/nejmoa1805819"

SEARCHES: list[tuple[str, Callable[[str, int], list[StudyRecord]]]] = [
    ("pubmed", pubmed.search),
    ("europepmc", europepmc.search),
    ("clinicaltrials", clinicaltrials.search),
    ("openalex", openalex.search),
    ("crossref", crossref.search),
    ("semantic_scholar", semantic_scholar.search),
    ("preprints", preprints.search),
    ("openfda", openfda.search),
    ("unpaywall", unpaywall.search),
]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def check_contract(name: str, records: list[StudyRecord],
                   query: str) -> list[str]:
    """Verify the conventions every connector is required to honour."""
    problems: list[str] = []
    if not records:
        return problems

    for record in records:
        if not isinstance(record, StudyRecord):
            problems.append(f"returned {type(record).__name__}, not StudyRecord")
            break
        if record.source != name:
            problems.append(f"source={record.source!r} (expected {name!r})")
            break
        if record.sources != [name]:
            problems.append(f"sources={record.sources!r}")
            break
        if not record.retrieved_query:
            problems.append("retrieved_query empty")
            break
        if record.doi and (record.doi != record.doi.lower()
                           or record.doi.startswith("http")):
            problems.append(f"unnormalised DOI {record.doi!r}")
            break

    if not any(r.title for r in records):
        problems.append("no record has a title")
    return problems


def field_coverage(records: list[StudyRecord]) -> str:
    """Compact indicator of which key fields actually got populated."""
    if not records:
        return "-"
    total = len(records)

    def pct(predicate: Callable[[StudyRecord], Any]) -> int:
        return round(100 * sum(1 for r in records if predicate(r)) / total)

    return (f"abs {pct(lambda r: r.abstract):>3}% "
            f"doi {pct(lambda r: r.doi):>3}% "
            f"yr {pct(lambda r: r.year):>3}% "
            f"auth {pct(lambda r: r.authors):>3}%")


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run_searches(query: str, n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, fn in SEARCHES:
        search_input = _ASPIRIN_DOI if name == "unpaywall" else query
        started = time.monotonic()
        result = http.safe_call(name, fn, search_input, n)
        elapsed = time.monotonic() - started

        records: list[StudyRecord] = result["records"]
        problems = check_contract(name, records, search_input)
        if result["status"] == "error":
            problems.insert(0, result.get("error", "unknown error"))

        rows.append({
            "source": name,
            "count": result["count"],
            "seconds": elapsed,
            "coverage": field_coverage(records),
            "title": records[0].title if records else "",
            "problems": problems,
            "records": records,
        })
        print(f"  {name:<17} {result['count']:>4} record(s) "
              f"in {elapsed:5.1f}s"
              + ("  [ISSUES]" if problems else ""))
    return rows


def run_capability_checks(query: str) -> list[tuple[str, str]]:
    """Exercise the non-search features the spec explicitly requires."""
    checks: list[tuple[str, str]] = []

    # --- OpenAlex bidirectional citation tracking -------------------------
    try:
        seeds = openalex.search(query, 1)
        if seeds and seeds[0].openalex_id:
            seed_id = seeds[0].openalex_id
            forward = openalex.cited_by(seed_id, 5)
            backward = openalex.references_of(seed_id, 5)
            audit = openalex.citation_audit([seed_id], max_per_work=5)
            checks.append((
                "openalex citation tracking",
                f"seed {seed_id}: {len(forward)} forward, "
                f"{len(backward)} backward, "
                f"audit {len(audit['forward'])}/{len(audit['backward'])}"))
        else:
            checks.append(("openalex citation tracking", "no seed work found"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("openalex citation tracking", f"FAILED: {exc}"))

    # --- OpenAlex abstract reconstruction ---------------------------------
    rebuilt = openalex.reconstruct_abstract(
        {"Aspirin": [0], "reduces": [1], "infarction": [2]})
    checks.append(("openalex abstract reconstruction",
                   "ok" if rebuilt == "Aspirin reduces infarction"
                   else f"FAILED: {rebuilt!r}"))

    # --- Europe PMC open-access full text ---------------------------------
    try:
        oa = europepmc.search(f"({query}) AND (OPEN_ACCESS:y)", 5)
        pmcids = [r.pmcid for r in oa if r.pmcid]
        text = europepmc.fetch_full_text_xml(pmcids[0]) if pmcids else None
        checks.append((
            "europepmc full text",
            f"{pmcids[0]}: {len(text)} chars of JATS XML" if text
            else "no OA full text available for sample"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("europepmc full text", f"FAILED: {exc}"))

    # --- Crossref DOI resolution + references -----------------------------
    try:
        record = crossref.fetch_doi(_ASPIRIN_DOI)
        refs = crossref.fetch_references(_ASPIRIN_DOI)
        checks.append((
            "crossref doi resolution",
            f"{_ASPIRIN_DOI} -> {(record.title[:50] + '...') if record else 'None'}"
            f" | {len(refs)} reference DOIs"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("crossref doi resolution", f"FAILED: {exc}"))

    # --- Unpaywall OA location -------------------------------------------
    try:
        url = unpaywall.find_full_text(_ASPIRIN_DOI)
        enriched = unpaywall.enrich(
            [StudyRecord(doi="10.1136/bmj.j5855", title="probe")])
        checks.append((
            "unpaywall oa lookup",
            f"best url: {(url or 'none')[:60]} | "
            f"enrich set oa={enriched[0].is_open_access}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("unpaywall oa lookup", f"FAILED: {exc}"))

    # --- PubMed MeSH / publication types ----------------------------------
    try:
        pm = pubmed.search(query, 5)
        with_mesh = sum(1 for r in pm if r.mesh_terms)
        with_types = sum(1 for r in pm if r.publication_types)
        checks.append((
            "pubmed mesh + pubtypes",
            f"{with_mesh}/{len(pm)} have MeSH, "
            f"{with_types}/{len(pm)} have PublicationTypes"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("pubmed mesh + pubtypes", f"FAILED: {exc}"))

    # --- ClinicalTrials registry specifics --------------------------------
    try:
        trials = clinicaltrials.search(query, 5)
        with_results = sum(1 for t in trials if t.has_results)
        with_enrol = sum(1 for t in trials if t.enrollment)
        linked = sum(1 for t in trials if t.pmid or t.references)
        checks.append((
            "clinicaltrials registry fields",
            f"{len(trials)} trials, {with_results} with posted results, "
            f"{with_enrol} with enrollment, {linked} with linked publications"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("clinicaltrials registry fields", f"FAILED: {exc}"))

    # --- Preprints: native CSH API ----------------------------------------
    try:
        native = preprints.scan_by_date(
            ["aspirin"], server="medrxiv", max_results=2, max_pages=3)
        checks.append((
            "preprints native csh api",
            f"date scan matched {len(native)} medRxiv preprint(s)"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("preprints native csh api", f"FAILED: {exc}"))

    # --- openFDA aggregation ----------------------------------------------
    try:
        signal = openfda.reaction_signal("aspirin", top_n=5)
        labels = openfda.search_labels("aspirin", 2)
        top = ", ".join(f"{k} ({v})" for k, v in list(signal.items())[:3])
        checks.append((
            "openfda signals + labels",
            f"top reactions: {top or 'none'} | {len(labels)} label(s)"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("openfda signals + labels", f"FAILED: {exc}"))

    # --- Semantic Scholar graceful degradation ----------------------------
    try:
        edges = semantic_scholar.references(_ASPIRIN_DOI, 5)
        checks.append((
            "semantic scholar edges",
            f"{len(edges)} reference(s) "
            f"{'(degraded to empty, as designed)' if not edges else ''}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("semantic scholar edges",
                       f"FAILED - must never raise: {exc}"))

    return checks


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def print_table(rows: list[dict[str, Any]]) -> None:
    header = (f"{'SOURCE':<17} {'COUNT':>5} {'SECS':>6}  "
              f"{'FIELD COVERAGE':<30} SAMPLE TITLE")
    print(header)
    print("-" * len(header))
    for row in rows:
        title = row["title"] or ("<no records>" if not row["problems"]
                                 else "<failed>")
        print(f"{row['source']:<17} {row['count']:>5} {row['seconds']:>6.1f}  "
              f"{row['coverage']:<30} {textwrap.shorten(title, 60)}")


def print_problems(rows: list[dict[str, Any]]) -> None:
    failing = [r for r in rows if r["problems"]]
    if not failing:
        print("\nAll connectors satisfied the contract.")
        return
    print("\nISSUES")
    print("-" * 70)
    for row in failing:
        for problem in row["problems"]:
            print(f"  {row['source']:<17} {textwrap.shorten(problem, 110)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("-n", "--max-results", type=int, default=5)
    parser.add_argument("--skip-capabilities", action="store_true",
                        help="only run the search functions")
    args = parser.parse_args()

    print(f"SRMA source connector smoke test\nquery: {args.query!r}  "
          f"max_results: {args.max_results}\n")

    print("Running searches...")
    rows = run_searches(args.query, args.max_results)

    print("\n" + "=" * 100)
    print_table(rows)
    print_problems(rows)

    if not args.skip_capabilities:
        print("\n" + "=" * 100)
        print("CAPABILITY CHECKS")
        print("-" * 100)
        for name, outcome in run_capability_checks(args.query):
            print(f"  {name:<32} {outcome}")

    summary = http.AUDIT.summary()
    print("\n" + "=" * 100)
    print(f"Audit log: {summary['total_queries']} HTTP call(s), "
          f"{summary['failures']} failure(s)")
    for source, count in sorted(summary["queries_by_source"].items()):
        print(f"  {source:<17} {count}")

    working = sum(1 for r in rows if r["count"] > 0 and not r["problems"])
    print(f"\n{working}/{len(rows)} connectors returned valid records.")
    # Semantic Scholar is allowed to return nothing; it degrades by design.
    hard_failures = [r["source"] for r in rows
                     if r["problems"] and r["source"] != "semantic_scholar"]
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
