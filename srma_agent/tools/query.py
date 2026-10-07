"""Structured search queries, rendered into each database's own dialect.

WHY THIS MODULE EXISTS

The first working version of this pipeline built one PubMed-syntax string and
sent it to all seven databases:

    ("Adults with a prior myocardial infarction"[tiab]
     OR "Myocardial Infarction"[MeSH Terms])
    AND (Aspirin[tiab] OR ASA[tiab] OR "Aspirin"[MeSH Terms])

`[tiab]` and `[MeSH Terms]` are PubMed inventions. Nobody else understands
them, and the failure is silent in the worst way — most APIs do not reject an
unparseable query, they just score it badly and hand back whatever ranked
highest. A measured run gave:

    pubmed           10   correct, native syntax
    europepmc         4   partially tolerant
    crossref         10   tags ignored, matched conference programme books
    openalex          0
    semantic_scholar  0
    preprints         0
    clinicaltrials    0   HTTP 400, rejected outright

Five of seven sources contributed nothing, and the one that did contribute
returned "UEG Week 2023 Poster Presentations" for a cardiology question.

So a query is represented here as *concepts*, not as text. Each concept holds
its synonyms and its controlled-vocabulary headings. Rendering to a specific
database happens at the last possible moment, by a function that knows that
database's grammar. Adding a source means adding a renderer, not hoping the
source tolerates PubMed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Term hygiene
# --------------------------------------------------------------------------

# Characters that unbalance a Boolean expression. A query with an unmatched
# quote or bracket usually returns zero results rather than an error, which
# is indistinguishable from "no such literature exists".
_UNSAFE = re.compile(r'["\[\]()]')

# Models routinely answer "give me population search terms" with the PICO
# sentence itself: "Adults with a prior myocardial infarction". Quoted as a
# phrase that matches zero papers, because no author writes that sentence.
# The searchable concept is the tail: "myocardial infarction".
#
# Every alternation below ends at a word boundary. Without \b after the
# article group, "Children with asthma" lost the leading "a" of "asthma" and
# became "sthma" - a silent corruption that still looks like a plausible
# search term.
_LEADING_COHORT = re.compile(
    r"^\s*(?:adult|patient|people|person|participant|subject|individual|"
    r"men|women|child|children|infant|elderly|population)s?\b"
    r"(?:\s+(?:who\s+(?:have|had|are|were)|with|having|after|following|"
    r"post|presenting\s+with|diagnosed\s+with|aged))?\b"
    r"(?:\s+(?:a|an|the))?\b"
    # Only framing words are stripped here. Clinical adjectives such as
    # "acute" and "chronic" are part of the diagnosis - "acute coronary
    # syndrome" is not the same concept as "coronary syndrome" - so they
    # stay.
    r"(?:\s+(?:prior|previous|past|known|a\s+history\s+of|history\s+of))?"
    r"\s*",
    re.IGNORECASE,
)

# Beyond this, a "term" is a sentence fragment, not something an author would
# put in a title. Five words admits "chronic obstructive pulmonary disease
# exacerbation" while rejecting most prose.
_MAX_TERM_WORDS = 5


def normalise_term(term: str) -> str:
    """Reduce a model-supplied phrase to something a paper might contain.

    Strips unsafe punctuation, then removes a leading cohort description so
    "Adults with a prior myocardial infarction" becomes "myocardial
    infarction". Returns "" when nothing searchable survives, which the
    caller must treat as "drop this term".
    """
    cleaned = _UNSAFE.sub(" ", str(term or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    match = _LEADING_COHORT.match(cleaned)
    if match:
        remainder = cleaned[match.end():].strip()
        if not remainder:
            # The whole term was a cohort descriptor - "Adults", "Patients".
            # Searching for it would match the entire clinical literature, so
            # it is worse than useless in an AND chain.
            return ""
        cleaned = remainder

    if len(cleaned.split()) > _MAX_TERM_WORDS:
        return ""
    return cleaned


def _quote(term: str) -> str:
    """Quote multi-word terms; most engines AND the words otherwise."""
    return f'"{term}"' if " " in term else term


@dataclass
class Concept:
    """One PICO element and every way a paper might express it."""

    name: str
    terms: list[str] = field(default_factory=list)
    mesh: list[str] = field(default_factory=list)

    def clean_terms(self) -> list[str]:
        return _dedupe(normalise_term(t) for t in self.terms)

    def clean_mesh(self) -> list[str]:
        # MeSH headings are a controlled vocabulary: they are already short
        # noun phrases, so they get punctuation stripping but not the cohort
        # rewrite, which would corrupt legitimate headings.
        return _dedupe(
            re.sub(r"\s+", " ", _UNSAFE.sub(" ", str(m))).strip()
            for m in self.mesh
        )

    def is_empty(self) -> bool:
        return not (self.clean_terms() or self.clean_mesh())


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
    return out


# --------------------------------------------------------------------------
# Renderers, one per grammar
# --------------------------------------------------------------------------


def _render_pubmed(concepts: list[Concept]) -> str:
    """PubMed / NCBI E-utilities. Field tags in square brackets."""
    blocks = []
    for concept in concepts:
        parts = [f"{_quote(t)}[tiab]" for t in concept.clean_terms()]
        parts += [f'"{m}"[MeSH Terms]' for m in concept.clean_mesh()]
        if parts:
            blocks.append("(" + " OR ".join(parts) + ")")
    return " AND ".join(blocks)


def _render_europepmc(concepts: list[Concept]) -> str:
    """Europe PMC. Prefixed field names, colon-separated, not bracketed."""
    blocks = []
    for concept in concepts:
        parts = [f"TITLE_ABS:{_quote(t)}" for t in concept.clean_terms()]
        parts += [f'MESH:"{m}"' for m in concept.clean_mesh()]
        if parts:
            blocks.append("(" + " OR ".join(parts) + ")")
    return " AND ".join(blocks)


def _render_essie(concepts: list[Concept]) -> str:
    """ClinicalTrials.gov v2 `query.term`, which uses Essie expressions.

    Essie understands AND/OR and quoted phrases but has no concept of MeSH
    headings, and rejects PubMed field tags with HTTP 400 rather than
    ignoring them. MeSH headings are still emitted, as plain text: a heading
    like "Myocardial Infarction" is also a perfectly good free-text phrase.
    """
    blocks = []
    for concept in concepts:
        parts = [_quote(t) for t in concept.clean_terms()]
        parts += [_quote(m) for m in concept.clean_mesh()]
        if parts:
            blocks.append("(" + " OR ".join(_dedupe(parts)) + ")")
    return " AND ".join(blocks)


def _render_boolean_plain(concepts: list[Concept]) -> str:
    """OpenAlex `search`: Boolean operators, no field tags, no MeSH."""
    blocks = []
    for concept in concepts:
        parts = [_quote(t) for t in concept.clean_terms()]
        parts += [_quote(m) for m in concept.clean_mesh()]
        if parts:
            blocks.append("(" + " OR ".join(_dedupe(parts)) + ")")
    return " AND ".join(blocks)


# How many synonyms per concept survive into a relevance-ranked bag of words.
# These engines have no Boolean AND, so every extra synonym is a term the
# ranker may match *instead of* the ones that matter, not in addition. Two
# keeps the primary phrase plus one common alternative.
_KEYWORDS_PER_CONCEPT = 2


def _render_keywords(concepts: list[Concept]) -> str:
    """Crossref `query.bibliographic` and Semantic Scholar `query`.

    Neither supports Boolean logic. Crossref in particular treats "AND" as a
    word to match, so emitting operators actively harms precision. The best
    available strategy is a short, specific bag of words: the most
    distinctive phrase from each concept, ANDed implicitly by the ranker.
    """
    parts: list[str] = []
    for concept in concepts:
        available = concept.clean_terms() or concept.clean_mesh()
        parts.extend(available[:_KEYWORDS_PER_CONCEPT])
    return " ".join(_dedupe(parts))


# Which grammar each connector speaks. Keyed by the source name registered in
# search.py, so a mismatch here silently reverts a source to keyword search
# rather than breaking it.
_DIALECT_BY_SOURCE = {
    "pubmed": _render_pubmed,
    "europepmc": _render_europepmc,
    # preprints.py wraps the Europe PMC endpoint with an "AND (SRC:PPR)"
    # filter, so it inherits Europe PMC's grammar.
    "preprints": _render_europepmc,
    "clinicaltrials": _render_essie,
    "openalex": _render_boolean_plain,
    "crossref": _render_keywords,
    "semantic_scholar": _render_keywords,
}

DEFAULT_RENDERER = _render_keywords


# --------------------------------------------------------------------------
# Study-design filters, one per grammar
# --------------------------------------------------------------------------
# WHY A SECOND, FILTERED SEARCH EXISTS
#
# A broad population AND intervention query on a heavily published topic
# matches tens of thousands of records. Every connector returns only its top
# N by its own ranking, and that ranking does not know we want trials. On
# run-20261007-093214 (DOACs vs warfarin, 966 unique records retrieved) not
# one of the four landmark RCTs - RE-LY, ROCKET AF, ARISTOTLE, ENGAGE AF -
# was in the result set. Cost-effectiveness analyses and 2026 cohort papers
# crowded them out. No amount of screening accuracy can recover a study the
# search never returned.
#
# The fix is the standard information-specialist one: run a precision tier
# that ANDs a validated randomised-trial filter (and the named comparator
# when there is one) so the primary trials rank first, and a recall tier
# without it so nothing is lost. Both go through the same deduplication.
#
# The PubMed filter is deliberately the *strict* publication-type filter,
# not the Cochrane Highly Sensitive Search Strategy. Measured live on the
# DOAC-vs-warfarin question (2026-10-07):
#
#   Cochrane sensitivity filter  3,869 hits  -> only ARISTOTLE in the top 200
#   randomized controlled trial[pt]  392 hits  -> RE-LY #4, ROCKET #2,
#                                                 ARISTOTLE #1, ENGAGE #3
#
# The sensitivity filter belongs in a recall strategy; here it defeats the
# purpose of the tier because PubMed's relevance ranking still has thousands
# of candidates to shuffle. Precision must be precise. Nothing is lost - the
# recall tier below has no design filter at all and goes through the same
# deduplication.

_RCT_FILTER_PUBMED = (
    '(randomized controlled trial[pt] OR controlled clinical trial[pt]) '
    'NOT (animals[mh] NOT humans[mh])'
)
_RCT_FILTER_EUROPEPMC = (
    '(PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Clinical Trial")'
)
_RCT_FILTER_PLAIN = '(randomized OR randomised) AND trial'
_RCT_FILTER_KEYWORDS = "randomized trial"

_RCT_FILTER_BY_SOURCE = {
    "pubmed": _RCT_FILTER_PUBMED,
    "europepmc": _RCT_FILTER_EUROPEPMC,
    "preprints": _RCT_FILTER_EUROPEPMC,
    # ClinicalTrials.gov only indexes trials; a design filter is redundant
    # and Essie does not support publication-type fields anyway.
    "clinicaltrials": "",
    "openalex": _RCT_FILTER_PLAIN,
    "crossref": _RCT_FILTER_KEYWORDS,
    "semantic_scholar": _RCT_FILTER_KEYWORDS,
}


@dataclass
class StructuredQuery:
    """A search expressed as concepts, renderable into any supported dialect.

    Two tiers are rendered from the same vocabulary:

      recall     population AND intervention
      precision  population AND intervention [AND comparator] AND rct-filter

    The outcome concept is held but deliberately not rendered into either
    AND chain. Trials frequently do not name their outcomes in the title or
    abstract, so requiring an outcome term is a well-documented way to lose
    eligible studies; Cochrane advises searching population and intervention
    only. It is retained because the reproducibility appendix must show the
    full vocabulary that was considered, not just what was used.

    The comparator is only ANDed in the precision tier, and only when the
    strategy supplied one - i.e. it is a named active treatment. A placebo
    or usual-care comparator is left empty by the prompt and so is never
    searched as a term.
    """

    population: Concept
    intervention: Concept
    outcome: Concept | None = None
    comparator: Concept | None = None
    fallback_text: str = ""

    def searchable_concepts(self) -> list[Concept]:
        return [c for c in (self.population, self.intervention)
                if c and not c.is_empty()]

    def has_comparator(self) -> bool:
        return bool(self.comparator and not self.comparator.is_empty())

    def render(self, source: str, tier: str = "recall") -> str:
        """Render for one named source, falling back to plain keywords.

        Args:
            source: Connector name registered in search.py.
            tier: "recall" (default) or "precision".
        """
        concepts = self.searchable_concepts()

        # A single concept means the AND chain has collapsed and the search
        # would return everything about that one idea. That is not a search
        # strategy, so we would rather send the raw PICO text and say so.
        if len(concepts) < 2:
            return self.fallback_text

        if tier == "precision" and self.has_comparator():
            concepts = concepts + [self.comparator]

        renderer = _DIALECT_BY_SOURCE.get(source, DEFAULT_RENDERER)
        rendered = renderer(concepts)
        if not rendered:
            return self.fallback_text

        if tier == "precision":
            design = _RCT_FILTER_BY_SOURCE.get(source, _RCT_FILTER_KEYWORDS)
            if design:
                if renderer is _render_keywords:
                    rendered = f"{rendered} {design}"
                else:
                    rendered = f"{rendered} AND {design}"
        return rendered

    def render_all(self, sources: list[str], tier: str = "recall") -> dict[str, str]:
        return {source: self.render(source, tier) for source in sources}

    def is_usable(self) -> bool:
        return len(self.searchable_concepts()) >= 2

    def describe(self) -> dict:
        """Full vocabulary, for the reproducibility appendix."""
        return {
            "population_terms": self.population.clean_terms(),
            "population_mesh": self.population.clean_mesh(),
            "intervention_terms": self.intervention.clean_terms(),
            "intervention_mesh": self.intervention.clean_mesh(),
            "comparator_terms": (self.comparator.clean_terms()
                                 if self.comparator else []),
            "comparator_mesh": (self.comparator.clean_mesh()
                                if self.comparator else []),
            "comparator_in_precision_tier": self.has_comparator(),
            "outcome_terms": (self.outcome.clean_terms()
                              if self.outcome else []),
            "outcome_excluded_from_query": True,
            "outcome_exclusion_rationale": (
                "Trials often omit outcome names from the title and abstract. "
                "Requiring an outcome term in the Boolean AND chain is a "
                "known cause of missed eligible studies (Cochrane Handbook)."
            ),
            "tiers": {
                "precision": "population AND intervention"
                             + (" AND comparator" if self.has_comparator() else "")
                             + " AND randomised-trial design filter "
                               "(Cochrane HSSS on PubMed)",
                "recall": "population AND intervention",
            },
        }


# --------------------------------------------------------------------------
# Legacy path
# --------------------------------------------------------------------------

# Matches PubMed field tags: [tiab], [MeSH Terms], [Title/Abstract], [pt] ...
_FIELD_TAG = re.compile(r"\[[^\]]{1,40}\]")


def strip_field_tags(query: str) -> str:
    """Remove PubMed field tags from a hand-written query string.

    The ADK tool surface still accepts a raw Boolean string, because a
    reviewer pasting a query they already trust is a legitimate workflow.
    That string is PubMed-flavoured by convention, so every other source
    needs the tags removed before it sees it - otherwise Crossref tries to
    match the literal word "tiab".
    """
    cleaned = _FIELD_TAG.sub(" ", query or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_boolean_operators(query: str) -> str:
    """Reduce a Boolean string to a bag of words, for engines without logic."""
    cleaned = strip_field_tags(query)
    cleaned = re.sub(r"\b(AND|OR|NOT)\b", " ", cleaned)
    cleaned = re.sub(r'[()"]', " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def adapt_raw_query(query: str, source: str) -> str:
    """Best-effort adaptation of a raw PubMed-style string for one source."""
    renderer = _DIALECT_BY_SOURCE.get(source, DEFAULT_RENDERER)
    if renderer is _render_pubmed:
        return query
    if renderer is _render_keywords:
        return strip_boolean_operators(query)
    return strip_field_tags(query)
