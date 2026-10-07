#!/usr/bin/env python
"""Fast offline tests for query rendering and the screening relevance gate.

No model and no network are needed, so this runs in well under a second and
can be used as a pre-commit check. It exists because both components it
covers failed silently in production rather than raising: a query in the
wrong dialect returns an empty result set that is indistinguishable from
"no such literature exists", and a relevance gate that is too loose produces
a review of the wrong subject while reporting success.

    ./.venv/bin/python scripts/test_query_and_gate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from srma_agent import screening                      # noqa: E402
from srma_agent.schemas import StudyRecord            # noqa: E402
from srma_agent.tools import query as q               # noqa: E402

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}\n          got  {got!r}\n          want {want!r}")
        failures.append(label)


def check_true(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f"\n          {detail}" if detail else ""))
        failures.append(label)


# ==========================================================================
print("\nTERM NORMALISATION")
print("=" * 72)
# The model reliably returns PICO sentences when asked for search terms.
# Quoted as phrases these match zero records, so they must be repaired or
# dropped before they reach a database.
for source, want in [
    ("Adults with a prior myocardial infarction", "myocardial infarction"),
    ("Patients who had a heart attack", "heart attack"),
    ("Women with a history of breast cancer", "breast cancer"),
    ("people presenting with acute coronary syndrome",
     "acute coronary syndrome"),
    # "acute" is part of the diagnosis and must survive; an earlier regex ate
    # the leading "a" and produced "cute coronary syndrome".
    ("Children with asthma", "asthma"),
    # Already clean: must pass through untouched.
    ("myocardial infarction", "myocardial infarction"),
    ("chronic obstructive pulmonary disease",
     "chronic obstructive pulmonary disease"),
    ("post-MI", "post-MI"),
    ("STEMI", "STEMI"),
    # Pure cohort descriptors carry no clinical concept and would match the
    # entire literature inside an AND chain.
    ("Adults", ""),
    ("Patients", ""),
    # Prose is not a search term.
    ("A long rambling sentence describing the eligible cohort here", ""),
]:
    check(f"{source[:52]!r}", q.normalise_term(source), want)


# ==========================================================================
print("\nPER-DATABASE QUERY RENDERING")
print("=" * 72)
sq = q.StructuredQuery(
    population=q.Concept("population",
                         ["Adults with a prior myocardial infarction"],
                         ["Myocardial Infarction"]),
    intervention=q.Concept("intervention",
                           ["Aspirin", "acetylsalicylic acid", "ASA"],
                           ["Aspirin"]),
    outcome=q.Concept("outcome", ["Mortality"], []),
    fallback_text="myocardial infarction aspirin",
)

pubmed = sq.render("pubmed")
check_true("pubmed uses [tiab] and [MeSH Terms]",
           "[tiab]" in pubmed and "[MeSH Terms]" in pubmed, pubmed)

epmc = sq.render("europepmc")
check_true("europepmc uses TITLE_ABS: and MESH:",
           "TITLE_ABS:" in epmc and "MESH:" in epmc, epmc)
check_true("europepmc carries no PubMed field tags",
           "[tiab]" not in epmc and "[MeSH" not in epmc, epmc)

# preprints.py wraps the Europe PMC endpoint, so it must speak that grammar.
check("preprints inherits the europepmc dialect", sq.render("preprints"), epmc)

ct = sq.render("clinicaltrials")
check_true("clinicaltrials has no field tags (400 Bad Request otherwise)",
           "[" not in ct and "]" not in ct, ct)
check_true("clinicaltrials keeps Boolean structure",
           " AND " in ct and " OR " in ct, ct)

oa = sq.render("openalex")
check_true("openalex has no field tags", "[" not in oa, oa)
check_true("openalex keeps Boolean structure", " AND " in oa, oa)

# Crossref scores "AND" as a word to match, so operators actively hurt.
for name in ("crossref", "semantic_scholar"):
    rendered = sq.render(name)
    check_true(f"{name} emits no Boolean operators",
               not any(op in f" {rendered} "
                       for op in (" AND ", " OR ", " NOT ")), rendered)
    check_true(f"{name} emits no field tags or brackets",
               "[" not in rendered and "(" not in rendered, rendered)
    check_true(f"{name} mentions both concepts",
               "myocardial" in rendered.lower()
               and "aspirin" in rendered.lower(), rendered)

# The sentence must have been repaired everywhere, not just in PubMed.
for name in ("pubmed", "europepmc", "clinicaltrials", "openalex", "crossref"):
    check_true(f"{name} contains no PICO sentence fragment",
               "adults with" not in sq.render(name).lower(), sq.render(name))

# A one-concept query has no AND chain and would return everything about that
# concept. Falling back to plain text is honest; shipping it as a strategy is
# not.
thin = q.StructuredQuery(
    population=q.Concept("population", ["Adults"], []),
    intervention=q.Concept("intervention", ["Aspirin"], []),
    fallback_text="FALLBACK",
)
check("single-concept query falls back", thin.render("pubmed"), "FALLBACK")
check_true("single-concept query reports itself unusable", not thin.is_usable())


# ==========================================================================
print("\nRAW QUERY ADAPTATION (the ADK tool still accepts a Boolean string)")
print("=" * 72)
raw = '("myocardial infarction"[tiab] OR "Aspirin"[MeSH Terms]) AND aspirin[tiab]'
check("pubmed passes a raw query through unchanged",
      q.adapt_raw_query(raw, "pubmed"), raw)
check_true("openalex strips field tags from a raw query",
           "[tiab]" not in q.adapt_raw_query(raw, "openalex"))
check_true("crossref strips operators from a raw query",
           " AND " not in f" {q.adapt_raw_query(raw, 'crossref')} ")


# ==========================================================================
print("\nRELEVANCE GATE")
print("=" * 72)
POP = ["myocardial infarction", "heart attack", "Myocardial Infarction"]
INT = ["Aspirin", "acetylsalicylic acid", "ASA"]

# The first four are verbatim from a real run in which all six were included.
for title, abstract, want in [
    ("Canadian Consensus Conference on Diagnosis and Treatment of Dementia",
     "Reviewed evidence for cholinesterase inhibitors in Alzheimer disease.",
     False),
    ("UEG Week 2023 Poster Presentations",
     "Abstracts covering endoscopy, hepatology and inflammatory bowel disease.",
     False),
    ("21st Congress of the European Hematology Association",
     "Abstracts covering leukaemia, lymphoma and transfusion medicine.",
     False),
    ("Myocardial infarction and left ventricular remodeling: CAPTOPRIL",
     "Patients after myocardial infarction randomised to captopril or placebo.",
     False),
    ("Randomised trial of streptokinase, oral aspirin, both, or neither: ISIS-2",
     "17187 patients with suspected acute myocardial infarction randomised to "
     "aspirin 162mg daily or placebo. Vascular mortality was reduced.",
     True),
    ("Aspirin in the primary and secondary prevention of vascular disease",
     "Patients with prior myocardial infarction, stroke or vascular disease.",
     True),
    # No abstract: one concept in the title is enough, because a title is too
    # short to demand both without discarding legitimate trials.
    ("Aspirin after heart attack", "", True),
    ("Conference proceedings volume 12", "", False),
]:
    passed, _ = screening.relevance_gate(
        StudyRecord(title=title, abstract=abstract), POP, INT)
    check(f"{'keep' if want else 'drop'}: {title[:48]!r}", passed, want)

# Word boundaries: a substring search for "ASA" matches "disaster" and
# "assay", which would wave through exactly what the gate exists to stop.
passed, _ = screening.relevance_gate(
    StudyRecord(title="Disaster assay in myocardial infarction",
                abstract="Assay of myocardial infarction after a disaster."),
    POP, INT)
check_true("'ASA' does not match 'disaster' or 'assay'", not passed)

# MeSH headings are searched too: an indexer may tag "Myocardial Infarction"
# on a paper whose abstract only says "heart attack".
passed, _ = screening.relevance_gate(
    StudyRecord(title="A trial of acetylsalicylic acid",
                abstract="Patients were randomised to treatment or placebo.",
                mesh_terms=["Myocardial Infarction"]),
    POP, INT)
check_true("MeSH headings satisfy the gate", passed)

# With no vocabulary the gate must disable itself rather than reject the
# entire search.
passed, _ = screening.relevance_gate(
    StudyRecord(title="Anything at all", abstract="Nothing relevant here."),
    [], [])
check_true("empty vocabulary disables the gate", passed)


# ==========================================================================
print("\n" + "=" * 72)
if failures:
    print(f"RESULT: {len(failures)} FAILED")
    for name in failures:
        print(f"  - {name}")
    raise SystemExit(1)
print("RESULT: all checks passed")
raise SystemExit(0)
