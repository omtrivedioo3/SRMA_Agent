"""Canonical data shapes for the SRMA pipeline.

Every literature source returns wildly different JSON. They all get
normalised into `StudyRecord` so that deduplication, screening, and
extraction can treat them uniformly.

Plain dataclasses are used rather than pydantic for the record types because
ADK tools must return JSON-serialisable dicts, and dataclasses convert
cleanly with `asdict`. Pydantic models are used only where ADK needs a
schema for structured LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LlmOutput(BaseModel):
    """Base for models the LLM fills in without constrained decoding.

    Ollama enforces the schema at the sampler, so `null` never appears in a
    non-nullable slot. The Vertex chatCompletions endpoint has no such
    guard: MedGemma routinely writes `"verification_url": null` or
    `"design": null` when it has nothing to say. Pydantic's default answer
    is to reject the entire object - which on run-20261007-103635 threw
    away otherwise perfect extractions of RE-LY and ROCKET AF over a field
    the pipeline overwrites deterministically two lines later.

    The rule here: if the model says `null` for a field that has a default
    and is not declared Optional, substitute the default. Fields that are
    genuinely required (no default) still fail loudly.
    """

    @model_validator(mode="before")
    @classmethod
    def _null_to_default(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        cleaned = dict(data)
        for name, info in cls.model_fields.items():
            if name in cleaned and cleaned[name] is None and not info.is_required():
                # Only substitute when None is not itself a legal value,
                # i.e. the annotation is not Optional / `X | None`.
                ann = info.annotation
                allows_none = (
                    ann is type(None)
                    or (hasattr(ann, "__args__") and type(None) in getattr(ann, "__args__", ()))
                )
                if not allows_none:
                    cleaned[name] = info.get_default(call_default_factory=True)
        return cleaned


# ==========================================================================
# Literature records
# ==========================================================================


@dataclass
class StudyRecord:
    """One bibliographic record, normalised across all sources."""

    # --- identity (used for deduplication, in priority order) ---
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    nct_id: str | None = None          # ClinicalTrials.gov registration
    openalex_id: str | None = None

    # --- bibliographic ---
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: int | None = None
    publication_types: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    # --- access ---
    url: str = ""
    is_open_access: bool = False
    full_text_url: str | None = None

    # --- provenance (spec: traceability) ---
    source: str = ""                    # which API returned it
    sources: list[str] = field(default_factory=list)  # all, after dedup merge
    retrieved_query: str = ""           # exact query string used

    # --- enrichment ---
    cited_by_count: int | None = None
    references: list[str] = field(default_factory=list)  # DOIs

    # --- registry-specific (ClinicalTrials.gov) ---
    trial_status: str | None = None
    enrollment: int | None = None
    has_results: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["best_id"] = self.best_id
        data["verification_url"] = self.verification_url
        data["citation"] = self.citation
        return data

    @property
    def best_id(self) -> str:
        """Most stable identifier available, for logging and citation."""
        for candidate in (self.doi, self.pmid, self.pmcid,
                          self.nct_id, self.openalex_id):
            if candidate:
                return str(candidate)
        return self.title[:80] or "<unidentified>"

    @property
    def verification_url(self) -> str:
        """Direct clickable URL for human verification of the source record."""
        if self.pmid:
            return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"
        if self.doi:
            clean_doi = self.doi.strip()
            if clean_doi.startswith("http"):
                return clean_doi
            return f"https://doi.org/{clean_doi}"
        if self.nct_id:
            return f"https://clinicaltrials.gov/study/{self.nct_id}"
        if self.pmcid:
            return f"https://pmc.ncbi.nlm.nih.gov/articles/{self.pmcid}/"
        return self.url or self.full_text_url or ""

    @property
    def citation(self) -> str:
        """Short human-readable citation with a traceable identifier."""
        first = "Anon"
        is_org = False
        if self.authors:
            raw_first = self.authors[0].strip()
            org_keywords = (
                "university", "hospital", "center", "centre", "institute",
                "inc", "ltd", "corp", "pharma", "therapeutics", "biotech",
                "group", "foundation", "college", "school", "clinic",
                "medical", "national", "cancer", "research", "company",
                "llc", "gmbh", "co.", "ministry", "department", "society",
            )
            lower_first = raw_first.lower()
            if any(k in lower_first for k in org_keywords):
                is_org = True
                # Strip trailing corporate noise like "Co., Ltd." or "Inc."
                cleaned = raw_first
                for suffix in (", Ltd.", " Co., Ltd.", " Co.,Ltd.", ", Inc.",
                               " Inc.", " Ltd.", " LLC", " Corp."):
                    if cleaned.endswith(suffix):
                        cleaned = cleaned[:-len(suffix)].strip()
                first = cleaned[:45].strip(" ,.")
            elif "," in raw_first:
                first = raw_first.split(",")[0].strip()
            else:
                parts = raw_first.split()
                if len(parts) >= 2 and parts[-1].isupper() and len(parts[-1]) <= 3:
                    # PubMed style: "Smith JA" -> "Smith"
                    first = parts[0]
                elif parts:
                    # Standard style: "John A Smith" -> "Smith"
                    first = parts[-1]
        etal = " et al." if (len(self.authors) > 1 and not is_org) else ""
        year = self.year or "n.d."
        ident = f"PMID:{self.pmid}" if self.pmid else (
            f"DOI:{self.doi}" if self.doi else self.best_id)
        return f"{first}{etal} ({year}). {ident}"


# ==========================================================================
# PRISMA flow accounting
# ==========================================================================


@dataclass
class PrismaFlow:
    """Live record counts for the PRISMA 2020 flow diagram."""

    identified_by_source: dict[str, int] = field(default_factory=dict)
    total_identified: int = 0
    duplicates_removed: int = 0
    records_screened: int = 0
    excluded_at_screening: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    full_text_assessed: int = 0
    excluded_at_full_text: int = 0
    full_text_exclusion_reasons: dict[str, int] = field(default_factory=dict)
    studies_included: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ==========================================================================
# Structured LLM outputs
# ==========================================================================


class PicoProtocol(LlmOutput):
    """Phase 1 output: the review protocol."""

    population: str = Field(description="Who is being studied")
    intervention: str = Field(description="The treatment under investigation")
    comparator: str = Field(description="What it is compared against")
    primary_outcome: str = Field(description="Main endpoint measured")
    secondary_outcomes: list[str] = Field(default_factory=list)
    study_designs: list[str] = Field(
        default_factory=list,
        description="Eligible designs, e.g. 'Randomized Controlled Trial'")
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Free-text terms and synonyms for search string building")
    mesh_terms: list[str] = Field(
        default_factory=list,
        description="Controlled-vocabulary MeSH descriptors")


class SearchStrategy(LlmOutput):
    """Phase 2 output: search vocabulary, grouped into Boolean blocks.

    The model supplies only the terms. Python assembles the actual query
    string (see pipeline._build_query). Letting a model emit raw Boolean
    syntax produces unbalanced parentheses and invented field tags, and the
    failure is silent: a malformed PubMed query returns zero results rather
    than an error, which looks like "no evidence exists".
    """

    population_terms: list[str] = Field(
        default_factory=list,
        description="Free-text synonyms for the CONDITION or population "
                    "only. Do not put the drug here.")
    population_mesh: list[str] = Field(
        default_factory=list,
        description="MeSH descriptors for the condition or population "
                    "only, e.g. 'Myocardial Infarction'")
    intervention_terms: list[str] = Field(
        default_factory=list,
        description="Free-text synonyms for the INTERVENTION only: generic "
                    "name, brand names, drug class, abbreviations. Do not "
                    "put the disease here.")
    intervention_mesh: list[str] = Field(
        default_factory=list,
        description="MeSH descriptors for the intervention only, "
                    "e.g. 'Aspirin'")
    outcome_terms: list[str] = Field(
        default_factory=list,
        description="Synonyms for the primary outcome. May be left empty: "
                    "constraining on outcome terms loses trials that do not "
                    "name the outcome in the abstract")
    comparator_terms: list[str] = Field(
        default_factory=list,
        description="Free-text synonyms for the COMPARATOR, but ONLY when it "
                    "is a specific named active treatment (a drug such as "
                    "'warfarin', a procedure, a device). Leave EMPTY when the "
                    "comparator is placebo, usual care, standard care, no "
                    "treatment or sham: those are not searched as terms.")
    comparator_mesh: list[str] = Field(
        default_factory=list,
        description="MeSH descriptors for a named active comparator only, "
                    "e.g. 'Warfarin'. Empty for placebo / usual care.")


class ScreeningDecision(str, Enum):
    INCLUDE = "Include"
    EXCLUDE = "Exclude"


class ReviewerVote(LlmOutput):
    """One reviewer's independent judgement on one record.

    `exclusion_category` is carried on the individual vote, not only on the
    combined result, because the two reviewers can exclude for different
    reasons. Consensus logic needs to see each reviewer's own category to
    decide which PRISMA bucket the record belongs in.
    """

    decision: ScreeningDecision
    reason: str = Field(description="Justification citing the abstract text")
    exclusion_category: str = Field(
        default="",
        description="PRISMA exclusion bucket, e.g. 'Wrong population'. "
                    "Empty string when the decision is Include.")


class DualScreenResult(LlmOutput):
    """Phase 3 output: two-reviewer screening with consensus.

    The consensus is computed in Python (see screening.py), not by the
    model. Asking a model to adjudicate its own disagreement reintroduces
    the correlation that running two separate calls was meant to remove.
    """

    reviewer_1: ReviewerVote
    reviewer_2: ReviewerVote
    consensus: ScreeningDecision
    conflict_resolution: str = Field(
        default="",
        description="How disagreement was resolved; empty if reviewers agreed")
    exclusion_category: str = Field(
        default="",
        description="Agreed PRISMA exclusion bucket; empty when included")


class RobLevel(str, Enum):
    LOW = "Low risk"
    SOME = "Some concerns"
    HIGH = "High risk"


class RobDomain(LlmOutput):
    domain: str
    judgement: RobLevel
    justification: str = Field(description="Must quote the source methods text")


class ArmData(LlmOutput):
    """Numeric outcome data for one trial arm.

    Every field is optional. The specification is explicit: missing data is
    flagged, never inferred.
    """

    label: str = Field(description="e.g. 'Intervention' or 'Control'")
    n_total: int | None = None
    n_events: int | None = None
    mean: float | None = None
    sd: float | None = None


class ReportedEffect(LlmOutput):
    """A summary effect estimate as published, with its confidence interval.

    Most trial abstracts do not give arm-level event counts; they give a
    hazard ratio, risk ratio or odds ratio with a 95% CI. That is enough to
    pool with the generic inverse-variance method (Cochrane Handbook 6.3),
    which is how published meta-analyses of time-to-event trials are done.
    Arm counts remain the preferred input whenever they are present.
    """

    measure: str = Field(
        description="One of 'HR', 'RR', 'OR', 'MD', 'SMD' exactly as the text names it")
    estimate: float = Field(description="Point estimate as printed")
    ci_lower: float | None = Field(default=None, description="Lower CI bound as printed")
    ci_upper: float | None = Field(default=None, description="Upper CI bound as printed")
    ci_level: float = Field(default=95.0, description="CI level in percent, usually 95")
    comparison: str = Field(
        default="",
        description="Which arms the estimate compares, e.g. 'dabigatran 150 mg vs warfarin'")
    quote: str = Field(
        default="",
        description="Verbatim sentence from the text containing the estimate")


class StudyExtraction(LlmOutput):
    """Phase 4+5 output: extracted data plus risk-of-bias assessment."""

    study_id: str = Field(description="PMID, DOI or NCT number")
    study_label: str = Field(description="e.g. 'Smith 2019'")
    title: str = Field(default="", description="Full article or trial title")
    source_db: str = Field(default="", description="Database source(s)")
    verification_url: str = Field(default="", description="Direct URL to verify the study")
    year: int | None = None
    design: str = Field(
        default="",
        description="Study design stated in the text, e.g. 'Randomized Controlled Trial', 'Cohort', 'Phase 1/2 single-arm'")
    population_description: str = Field(
        default="",
        description="Brief description of the enrolled patient population/cohort as stated in the text")
    intervention_description: str = Field(
        default="",
        description="Brief description of the specific intervention, dose or model evaluated")
    comparator_description: str = Field(
        default="",
        description="Brief description of the comparator or control group")
    key_findings_summary: str = Field(
        default="",
        description="1-2 factual sentences summarising the main outcome finding or trial status reported in the text")
    evidence_quote: str = Field(
        default="",
        description="Direct verbatim quote from the text where the outcome numbers or trial status are stated")
    intervention_arm: ArmData
    control_arm: ArmData
    reported_effect: ReportedEffect | None = Field(
        default=None,
        description="Published HR/RR/OR/MD with CI for the target outcome, if the text states one")
    outcome_name: str = ""
    rob_domains: list[RobDomain] = Field(default_factory=list)
    rob_overall: RobLevel | None = None
    missing_data_flags: list[str] = Field(
        default_factory=list,
        description="Fields the source did not report")



class GradeRating(str, Enum):
    HIGH = "High"
    MODERATE = "Moderate"
    LOW = "Low"
    VERY_LOW = "Very low"


class GradeDomain(LlmOutput):
    """One of the five GRADE downgrading considerations."""

    judgement: str = Field(
        description="'Not serious', 'Serious' or 'Very serious'")
    downgrade_levels: int = Field(
        default=0, ge=0, le=2,
        description="0 for not serious, 1 for serious, 2 for very serious")
    rationale: str = Field(description="Reason, citing the supplied statistics")


class GradeAssessment(LlmOutput):
    """Phase 8 output: certainty of evidence.

    Each domain is a separate field rather than a free-text paragraph so the
    final rating can be recomputed arithmetically in Python and compared
    against `final_rating`. A model that downgrades twice but then reports
    "Moderate" is caught instead of believed.
    """

    outcome: str = Field(description="The outcome this rating applies to")
    starting_rating: GradeRating = Field(
        default=GradeRating.HIGH,
        description="High for RCT bodies of evidence, Low for observational")

    risk_of_bias: GradeDomain
    inconsistency: GradeDomain
    indirectness: GradeDomain
    imprecision: GradeDomain
    publication_bias: GradeDomain

    final_rating: GradeRating
    summary: str = Field(
        description="One plain-language sentence on what the evidence shows "
                    "and how confident a reader should be in it")

