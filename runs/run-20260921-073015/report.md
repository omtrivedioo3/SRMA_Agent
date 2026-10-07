# Systematic Review and Meta-Analysis Report

**Clinical Question:** In adults receiving CAR-T cell therapy, does early administration of IL-6 inhibitors (such as tocilizumab) reduce the incidence of severe (Grade 3 or higher) cytokine release syndrome compared with standard or delayed treatment?
**Run ID:** `run-20260921-073015` | **Generated (UTC):** `2026-09-21T07:30:15.643728+00:00` | **Elapsed Time:** `150.8s` | **Clinical Model:** `ollama_chat/medgemma`

## 1. Structured Abstract & Executive Evidence Synthesis

- **Background & Objective:** To systematically evaluate and synthesize clinical evidence addressing **Incidence of severe (Grade 3 or higher) cytokine release syndrome** in **Adults receiving CAR-T cell therapy** receiving **Early administration of IL-6 inhibitors (such as tocilizumab)** compared with **Standard or delayed treatment**.
- **Methods (PRISMA 2020 / Cochrane Handbook):** Multi-database searches were executed across indexed biomedical repositories, clinical trial registries, and preprint servers (`531` records identified; `28` duplicates removed; `503` unique citations). Records underwent deterministic PICO relevance gating and independent dual-reviewer screening (`20` screened; `20` excluded with documented PRISMA reasons; `0` eligible). Structured arm-level extraction and 5-domain Cochrane Risk of Bias 2.0 (RoB 2) assessments were performed on `0` studies.
- **Results (Qualitative & Single-Arm Synthesis):** Fewer than 2 extracted abstracts reported complete two-arm comparative event counts or means/SDs.
- **Conclusion:** In accordance with Cochrane Handbook standards against fabricating or imputing unreported control-arm counts from abstracts, a structured qualitative synthesis of all `0` included studies is presented in **Table 1** and **Section 5** below.

## 2. PICO Protocol, Eligibility Criteria & Search Strategy

| PICOS Element | Specification |
| :--- | :--- |
| **Population (P)** | Adults receiving CAR-T cell therapy |
| **Intervention (I)** | Early administration of IL-6 inhibitors (such as tocilizumab) |
| **Comparator (C)** | Standard or delayed treatment |
| **Primary Outcome (O)** | Incidence of severe (Grade 3 or higher) cytokine release syndrome |
| **Eligible Study Designs (S)** | Randomized Controlled Trial |
| **Inclusion Criteria** | Adults receiving CAR-T cell therapy; Intervention group: Early administration of IL-6 inhibitors (such as tocilizumab); Comparator group: Standard or delayed treatment; Severe (Grade 3 or higher) cytokine release syndrome as the primary outcome |
| **Exclusion Criteria** | Animal studies; In-vitro studies; Narrative reviews; Editorials; Case reports |

**Canonical Boolean Search Strategy (PubMed / MEDLINE Syntax):**
```text
("CAR-T cell therapy"[tiab] OR "CAR T-cell Therapy"[tiab] OR CAR-T[tiab] OR "CAR T"[tiab] OR "CAR T-cell Therapy"[MeSH Terms] OR "CAR-T cell Therapy"[MeSH Terms] OR "CAR-T"[MeSH Terms] OR "CAR T"[MeSH Terms]) AND ("IL-6 inhibitors"[tiab] OR IL-6[tiab] OR tocilizumab[tiab] OR "IL-6 blockade"[tiab] OR "IL-6 inhibition"[tiab] OR "Interleukin-6"[MeSH Terms])
```

## 3. Complete PRISMA 2020 Evidence Funnel & Record Accounting

Every single record retrieved from the literature search is accounted for below:

| Funnel Phase | Step / Database Source | Record Count | Notes & Accounting Proof |
| :--- | :--- | :---: | :--- |
| **1. Identification** | Database: `clinicaltrials` | `100` | Status: `success` |
| **1. Identification** | Database: `europepmc` | `100` | Status: `success` |
| **1. Identification** | Database: `pubmed` | `100` | Status: `success` |
| **1. Identification** | Database: `crossref` | `100` | Status: `success` |
| **1. Identification** | Database: `openalex` | `100` | Status: `success` |
| **1. Identification** | Database: `semantic_scholar` | `0` | Status: `success` |
| **1. Identification** | Database: `preprints` | `31` | Status: `success` |
| **1. Identification** | **Total Records Identified** | **`531`** | Across all queried databases |
| **2. Deduplication** | Duplicates Removed | `-28` | Matched by: DOI / PMID / NCT / Title+Year (see Table 4 below) |
| **2. Deduplication** | **Unique Records After Deduplication** | **`503`** | `531 - 28 = 503` unique records |
| **3. Screening** | Unscreened (Beyond Screening Cap) | `-483` | Screening cap was set to `20` records (`SRMA_MAX_ABSTRACTS_TO_SCREEN`) |
| **3. Screening** | **Records Screened (Title & Abstract)** | **`20`** | Dual independent MedGemma reviewers (Agreement rate: `N/A`) |
| **3. Screening** | Excluded at Title/Abstract Screening | `-20` | `20` by Python Relevance Gate + `0` by Dual Reviewers (see Table 2) |
| *↳ Exclusion Breakdown* | *Wrong population* | *`20`* | *PRISMA 2020 exclusion category* |
| **3. Screening** | **Studies Approved at Screening** | **`0`** | `20 screened - 20 excluded = 0 eligible studies` |
| **4. Extraction / Full-Text** | **Studies Assessed for Data & RoB 2** | **`0`** | Full structured extraction + 5-domain Cochrane RoB 2 assessment |
| **5. Synthesis** | **Final Studies Pooled in Meta-Analysis** | **`0`** | **`0` total participants analysed quantitatively** |

## 4. Table 1: Characteristics & Extracted Evidence of Included Studies

This table documents every study that passed screening and underwent data extraction (modeled on publication tables in *Acta Oncologica* / Cochrane reviews). Click any **Study ID** to open and verify the original source record:

| Ref | Study ID & Verification Link | Author (Year) & Title | Source & Design | Target Population | Intervention Arm (`Events / N` or `Mean ± SD`) | Comparator Arm (`Events / N` or `Mean ± SD`) | Study Effect `[95% CI]` & Weight | RoB 2 Overall | Status & Key Findings |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |

## 5. Study-by-Study Evidence Proof, Dual-Reviewer Justifications & RoB 2 Audit

Below is the complete audit trail for each extracted study, including **why it passed screening**, **verbatim text quotes**, and **all 5 Cochrane RoB 2 domain judgements**:

## 6. Table 2: Excluded Articles at Title/Abstract Screening (Full Audit Log)

All **`20` articles excluded at screening** are listed below with their identifier, clickable verification link, PRISMA category, decision source, and exact reason:

| # | Article ID & Link | Title | Source DB | PRISMA Exclusion Category | Decided By | Exact Proof / Reason for Exclusion |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| `1` | [`NCT04499573`](https://clinicaltrials.gov/study/NCT04499573) | Bispecific CD19/CD22 CAR-T for Treatment of Children and Young Adults With r/r B-ALL | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `2` | [`NCT06925022`](https://clinicaltrials.gov/study/NCT06925022) | Educational Programs Based on Healthy Habits to Improve Quality of Life and Psychosocial Profile in Women With Neurodegenerative Diseases... | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (CAR-T cell therapy, CAR T-cell Therapy, CAR-T) or the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `3` | [`NCT06716164`](https://clinicaltrials.gov/study/NCT06716164) | Safety and Efficacy of Metabolically Armed CD19 CAR-T Cells (Meta10-19) in the Treatment of r/r B-NHL Clinical Research | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `4` | [`NCT07033299`](https://clinicaltrials.gov/study/NCT07033299) | The Safety, Efficacy, and Cellular Metabolic Kinetics of CT1192 in Treating Patients With Anti Neutrophil Cytoplasmic Antibody Associated... | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `5` | [`NCT06228404`](https://clinicaltrials.gov/study/NCT06228404) | Clinical Study of Safety and Efficacy of Enhanced PSMA CAR- T in Refractory CRPC | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `6` | [`NCT06106893`](https://clinicaltrials.gov/study/NCT06106893) | A Clinical Study of CD19 Universal CAR-γδT Cells in Active Systemic Lupus Erythematosus | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (CAR-T cell therapy, CAR T-cell Therapy, CAR-T) or the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `7` | [`NCT07456371`](https://clinicaltrials.gov/study/NCT07456371) | PIC1 Injection Therapy for Relapsed/Refractory B-NHL | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `8` | [`NCT06407947`](https://clinicaltrials.gov/study/NCT06407947) | Study of CT071 Injection in High Risk Newly Diagnosed Multiple Myeloma | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (CAR-T cell therapy, CAR T-cell Therapy, CAR-T) or the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `9` | [`10.1016/j.jtct.2026.05.045`](https://doi.org/10.1016/j.jtct.2026.05.045) | Clinical Study of SenL-T7 CAR T Cells in the Treatment of Relapsed and Refractory CD7+ T-cell Lymphoblastic Leukemia or T-cell Lymphoblas... | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `10` | [`NCT07563543`](https://clinicaltrials.gov/study/NCT07563543) | RN1701 Injection in the Treatment of Relapsed/Refractory B-Cell Lymphomas | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `11` | [`NCT03146533`](https://clinicaltrials.gov/study/NCT03146533) | CD19 CART Cells for Patients With Relapse and Refractory CD19+ B-cell Lymphoma. | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (CAR-T cell therapy, CAR T-cell Therapy, CAR-T) or the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `12` | [`NCT05473221`](https://clinicaltrials.gov/study/NCT05473221) | Evaluate the Safety and Efficacy of CD33 CAR-T in Patients With R/R AML | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `13` | [`NCT06987916`](https://clinicaltrials.gov/study/NCT06987916) | Efficacy and Safety Evaluation of U01(ssCART-19) in B-Cell Lymphoma | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (CAR-T cell therapy, CAR T-cell Therapy, CAR-T). |
| `14` | [`NCT05667506`](https://clinicaltrials.gov/study/NCT05667506) | A Study of CNCT19 Treatment in Children and Adolescent r/r ALL Patients(Pediatric) | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `15` | [`NCT03633773`](https://clinicaltrials.gov/study/NCT03633773) | Safety and Efficacy Evaluation of MUC-1 CART in the Treatment of Intrahepatic Cholangiocarcinoma | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `16` | [`10.1016/j.clim.2022.109030`](https://doi.org/10.1016/j.clim.2022.109030) | A Study to Evaluate the Safety and Efficacy of A2B395, an Allogeneic Logic-gated CAR T, in Participants With Solid Tumors That Express EG... | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `17` | [`NCT04546906`](https://clinicaltrials.gov/study/NCT04546906) | Safety and Efficacy Study of CD22 CAR-T Cells for Relapsed or Refractory Acute Lymphoblastic Leukemia | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `18` | [`NCT06612645`](https://clinicaltrials.gov/study/NCT06612645) | Safety and Efficacy of CMD03 CAR T Cell in Children With Relapse or Refractory Solid Tumors | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `19` | [`NCT07078929`](https://clinicaltrials.gov/study/NCT07078929) | Clinical Trial of CMD63 Chimeric Antigen Receptor T-cell (CAR T-cell) in Children With Acute Lymphoblastic Leukemia (ALL) | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |
| `20` | [`NCT06481735`](https://clinicaltrials.gov/study/NCT06481735) | TCR Reserved and Power3 (SPPL3) Gene Knock-out Allogeneic CD19-targeting CAR-T Cell Therapy in r/r B-ALL | `Database` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (IL-6 inhibitors, IL-6, tocilizumab). |

## 7. Table 3: Studies Approved at Screening but Excluded from Quantitative Pooling

*Every study approved at screening was extracted and pooled in the quantitative meta-analysis.*

## 8. Table 4: Deduplication Audit Log (Removed Duplicate Records)

A total of **`28` duplicate records** were identified across databases and merged into a single canonical study record before screening:

| # | Removed Duplicate ID & Link | Duplicate Source DB | Merged Into Primary Study ID | Matched By | Article Title |
| :---: | :--- | :--- | :--- | :---: | :--- |
| `1` | [`NCT04499573`](https://clinicaltrials.gov/study/NCT04499573) | `europepmc` | [`NCT04499573`](https://clinicaltrials.gov/study/NCT04499573) | `nct_id` | Bispecific CD19/CD22 CAR-T for Treatment of Children and Young Adults With r/r B-ALL |
| `2` | [`NCT06925022`](https://clinicaltrials.gov/study/NCT06925022) | `pubmed` | [`NCT06925022`](https://clinicaltrials.gov/study/NCT06925022) | `nct_id` | Educational Programs Based on Healthy Habits to Improve Quality of Life and Psychosocial Profile in Women With Neurod... |
| `3` | [`NCT06716164`](https://clinicaltrials.gov/study/NCT06716164) | `crossref` | [`NCT06716164`](https://clinicaltrials.gov/study/NCT06716164) | `nct_id` | Safety and Efficacy of Metabolically Armed CD19 CAR-T Cells (Meta10-19) in the Treatment of r/r B-NHL Clinical Research |
| `4` | [`NCT07033299`](https://clinicaltrials.gov/study/NCT07033299) | `openalex` | [`NCT07033299`](https://clinicaltrials.gov/study/NCT07033299) | `nct_id` | The Safety, Efficacy, and Cellular Metabolic Kinetics of CT1192 in Treating Patients With Anti Neutrophil Cytoplasmic... |
| `5` | [`NCT06228404`](https://clinicaltrials.gov/study/NCT06228404) | `semantic_scholar` | [`NCT06228404`](https://clinicaltrials.gov/study/NCT06228404) | `nct_id` | Clinical Study of Safety and Efficacy of Enhanced PSMA CAR- T in Refractory CRPC |
| `6` | [`NCT06106893`](https://clinicaltrials.gov/study/NCT06106893) | `preprints` | [`NCT06106893`](https://clinicaltrials.gov/study/NCT06106893) | `nct_id` | A Clinical Study of CD19 Universal CAR-γδT Cells in Active Systemic Lupus Erythematosus |
| `7` | [`NCT07456371`](https://clinicaltrials.gov/study/NCT07456371) | `clinicaltrials` | [`NCT07456371`](https://clinicaltrials.gov/study/NCT07456371) | `nct_id` | PIC1 Injection Therapy for Relapsed/Refractory B-NHL |
| `8` | [`NCT06407947`](https://clinicaltrials.gov/study/NCT06407947) | `europepmc` | [`NCT06407947`](https://clinicaltrials.gov/study/NCT06407947) | `nct_id` | Study of CT071 Injection in High Risk Newly Diagnosed Multiple Myeloma |
| `9` | [`10.1016/j.jtct.2026.05.045`](https://doi.org/10.1016/j.jtct.2026.05.045) | `pubmed` | [`10.1016/j.jtct.2026.05.045`](https://doi.org/10.1016/j.jtct.2026.05.045) | `doi` | Clinical Study of SenL-T7 CAR T Cells in the Treatment of Relapsed and Refractory CD7+ T-cell Lymphoblastic Leukemia... |
| `10` | [`NCT07563543`](https://clinicaltrials.gov/study/NCT07563543) | `crossref` | [`NCT07563543`](https://clinicaltrials.gov/study/NCT07563543) | `nct_id` | RN1701 Injection in the Treatment of Relapsed/Refractory B-Cell Lymphomas |
| `11` | [`NCT03146533`](https://clinicaltrials.gov/study/NCT03146533) | `openalex` | [`NCT03146533`](https://clinicaltrials.gov/study/NCT03146533) | `nct_id` | CD19 CART Cells for Patients With Relapse and Refractory CD19+ B-cell Lymphoma. |
| `12` | [`NCT05473221`](https://clinicaltrials.gov/study/NCT05473221) | `semantic_scholar` | [`NCT05473221`](https://clinicaltrials.gov/study/NCT05473221) | `nct_id` | Evaluate the Safety and Efficacy of CD33 CAR-T in Patients With R/R AML |
| `13` | [`NCT06987916`](https://clinicaltrials.gov/study/NCT06987916) | `preprints` | [`NCT06987916`](https://clinicaltrials.gov/study/NCT06987916) | `nct_id` | Efficacy and Safety Evaluation of U01(ssCART-19) in B-Cell Lymphoma |
| `14` | [`NCT05667506`](https://clinicaltrials.gov/study/NCT05667506) | `clinicaltrials` | [`NCT05667506`](https://clinicaltrials.gov/study/NCT05667506) | `nct_id` | A Study of CNCT19 Treatment in Children and Adolescent r/r ALL Patients(Pediatric) |
| `15` | [`NCT03633773`](https://clinicaltrials.gov/study/NCT03633773) | `europepmc` | [`NCT03633773`](https://clinicaltrials.gov/study/NCT03633773) | `nct_id` | Safety and Efficacy Evaluation of MUC-1 CART in the Treatment of Intrahepatic Cholangiocarcinoma |
| `16` | [`10.1016/j.clim.2022.109030`](https://doi.org/10.1016/j.clim.2022.109030) | `pubmed` | [`10.1016/j.clim.2022.109030`](https://doi.org/10.1016/j.clim.2022.109030) | `doi` | A Study to Evaluate the Safety and Efficacy of A2B395, an Allogeneic Logic-gated CAR T, in Participants With Solid Tu... |
| `17` | [`NCT04546906`](https://clinicaltrials.gov/study/NCT04546906) | `crossref` | [`NCT04546906`](https://clinicaltrials.gov/study/NCT04546906) | `nct_id` | Safety and Efficacy Study of CD22 CAR-T Cells for Relapsed or Refractory Acute Lymphoblastic Leukemia |
| `18` | [`NCT06612645`](https://clinicaltrials.gov/study/NCT06612645) | `openalex` | [`NCT06612645`](https://clinicaltrials.gov/study/NCT06612645) | `nct_id` | Safety and Efficacy of CMD03 CAR T Cell in Children With Relapse or Refractory Solid Tumors |
| `19` | [`NCT07078929`](https://clinicaltrials.gov/study/NCT07078929) | `semantic_scholar` | [`NCT07078929`](https://clinicaltrials.gov/study/NCT07078929) | `nct_id` | Clinical Trial of CMD63 Chimeric Antigen Receptor T-cell (CAR T-cell) in Children With Acute Lymphoblastic Leukemia (... |
| `20` | [`NCT06481735`](https://clinicaltrials.gov/study/NCT06481735) | `preprints` | [`NCT06481735`](https://clinicaltrials.gov/study/NCT06481735) | `nct_id` | TCR Reserved and Power3 (SPPL3) Gene Knock-out Allogeneic CD19-targeting CAR-T Cell Therapy in r/r B-ALL |
| `21` | [`NCT04499573`](https://clinicaltrials.gov/study/NCT04499573) | `clinicaltrials` | [`NCT04499573`](https://clinicaltrials.gov/study/NCT04499573) | `nct_id` | Bispecific CD19/CD22 CAR-T for Treatment of Children and Young Adults With r/r B-ALL |
| `22` | [`NCT06925022`](https://clinicaltrials.gov/study/NCT06925022) | `europepmc` | [`NCT06925022`](https://clinicaltrials.gov/study/NCT06925022) | `nct_id` | Educational Programs Based on Healthy Habits to Improve Quality of Life and Psychosocial Profile in Women With Neurod... |
| `23` | [`NCT06716164`](https://clinicaltrials.gov/study/NCT06716164) | `pubmed` | [`NCT06716164`](https://clinicaltrials.gov/study/NCT06716164) | `nct_id` | Safety and Efficacy of Metabolically Armed CD19 CAR-T Cells (Meta10-19) in the Treatment of r/r B-NHL Clinical Research |
| `24` | [`NCT07033299`](https://clinicaltrials.gov/study/NCT07033299) | `crossref` | [`NCT07033299`](https://clinicaltrials.gov/study/NCT07033299) | `nct_id` | The Safety, Efficacy, and Cellular Metabolic Kinetics of CT1192 in Treating Patients With Anti Neutrophil Cytoplasmic... |
| `25` | [`NCT06228404`](https://clinicaltrials.gov/study/NCT06228404) | `openalex` | [`NCT06228404`](https://clinicaltrials.gov/study/NCT06228404) | `nct_id` | Clinical Study of Safety and Efficacy of Enhanced PSMA CAR- T in Refractory CRPC |
| `26` | [`NCT06106893`](https://clinicaltrials.gov/study/NCT06106893) | `semantic_scholar` | [`NCT06106893`](https://clinicaltrials.gov/study/NCT06106893) | `nct_id` | A Clinical Study of CD19 Universal CAR-γδT Cells in Active Systemic Lupus Erythematosus |
| `27` | [`NCT07456371`](https://clinicaltrials.gov/study/NCT07456371) | `preprints` | [`NCT07456371`](https://clinicaltrials.gov/study/NCT07456371) | `nct_id` | PIC1 Injection Therapy for Relapsed/Refractory B-NHL |
| `28` | [`NCT06407947`](https://clinicaltrials.gov/study/NCT06407947) | `clinicaltrials` | [`NCT06407947`](https://clinicaltrials.gov/study/NCT06407947) | `nct_id` | Study of CT071 Injection in High Risk Newly Diagnosed Multiple Myeloma |

## 9. Statistical Meta-Analysis, Sensitivity Analysis & GRADE Evidence Profile

### 9.4 Reproducible R Verification Script (`meta` / `metafor`)

```r
# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20260921-073015
# Outcome: Incidence of severe (Grade 3 or higher) cytokine release syndrome
# Generated per PRISMA 2020 & Cochrane Handbook specifications
# ============================================================================
library(meta)
library(metafor)

# Fewer than 2 studies reported comparative arm-level event counts or means/SDs
# in the retrieved abstracts. Populate m_data below after full-text extraction:
m_data <- data.frame(
  study   = c("Study_1", "Study_2"),
  event_e = c(NA, NA), n_e = c(NA, NA),
  event_c = c(NA, NA), n_c = c(NA, NA)
)
```

## 10. Complete Bibliography & Direct Verification Links

- **[E1]** **NCT04499573** *Bispecific CD19/CD22 CAR-T for Treatment of Children and Young Adults With r/r B-ALL* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT04499573) (`https://clinicaltrials.gov/study/NCT04499573`)
- **[E2]** **NCT06925022** *Educational Programs Based on Healthy Habits to Improve Quality of Life and Psychosocial Profile in Women With Neurodegenerative Diseases: The ADVICE Protocol Study (Phase 1)* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06925022) (`https://clinicaltrials.gov/study/NCT06925022`)
- **[E3]** **NCT06716164** *Safety and Efficacy of Metabolically Armed CD19 CAR-T Cells (Meta10-19) in the Treatment of r/r B-NHL Clinical Research* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06716164) (`https://clinicaltrials.gov/study/NCT06716164`)
- **[E4]** **NCT07033299** *The Safety, Efficacy, and Cellular Metabolic Kinetics of CT1192 in Treating Patients With Anti Neutrophil Cytoplasmic Antibody Associated Vasculitis* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT07033299) (`https://clinicaltrials.gov/study/NCT07033299`)
- **[E5]** **NCT06228404** *Clinical Study of Safety and Efficacy of Enhanced PSMA CAR- T in Refractory CRPC* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06228404) (`https://clinicaltrials.gov/study/NCT06228404`)
- **[E6]** **NCT06106893** *A Clinical Study of CD19 Universal CAR-γδT Cells in Active Systemic Lupus Erythematosus* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06106893) (`https://clinicaltrials.gov/study/NCT06106893`)
- **[E7]** **NCT07456371** *PIC1 Injection Therapy for Relapsed/Refractory B-NHL* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT07456371) (`https://clinicaltrials.gov/study/NCT07456371`)
- **[E8]** **NCT06407947** *Study of CT071 Injection in High Risk Newly Diagnosed Multiple Myeloma* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06407947) (`https://clinicaltrials.gov/study/NCT06407947`)
- **[E9]** **10.1016/j.jtct.2026.05.045** *Clinical Study of SenL-T7 CAR T Cells in the Treatment of Relapsed and Refractory CD7+ T-cell Lymphoblastic Leukemia or T-cell Lymphoblastic Lymphoma* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://doi.org/10.1016/j.jtct.2026.05.045) (`https://doi.org/10.1016/j.jtct.2026.05.045`)
- **[E10]** **NCT07563543** *RN1701 Injection in the Treatment of Relapsed/Refractory B-Cell Lymphomas* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT07563543) (`https://clinicaltrials.gov/study/NCT07563543`)
- **[E11]** **NCT03146533** *CD19 CART Cells for Patients With Relapse and Refractory CD19+ B-cell Lymphoma.* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT03146533) (`https://clinicaltrials.gov/study/NCT03146533`)
- **[E12]** **NCT05473221** *Evaluate the Safety and Efficacy of CD33 CAR-T in Patients With R/R AML* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT05473221) (`https://clinicaltrials.gov/study/NCT05473221`)
- **[E13]** **NCT06987916** *Efficacy and Safety Evaluation of U01(ssCART-19) in B-Cell Lymphoma* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06987916) (`https://clinicaltrials.gov/study/NCT06987916`)
- **[E14]** **NCT05667506** *A Study of CNCT19 Treatment in Children and Adolescent r/r ALL Patients(Pediatric)* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT05667506) (`https://clinicaltrials.gov/study/NCT05667506`)
- **[E15]** **NCT03633773** *Safety and Efficacy Evaluation of MUC-1 CART in the Treatment of Intrahepatic Cholangiocarcinoma* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT03633773) (`https://clinicaltrials.gov/study/NCT03633773`)
- **[E16]** **10.1016/j.clim.2022.109030** *A Study to Evaluate the Safety and Efficacy of A2B395, an Allogeneic Logic-gated CAR T, in Participants With Solid Tumors That Express EGFR and Have Lost HLA-A*02 Expression* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://doi.org/10.1016/j.clim.2022.109030) (`https://doi.org/10.1016/j.clim.2022.109030`)
- **[E17]** **NCT04546906** *Safety and Efficacy Study of CD22 CAR-T Cells for Relapsed or Refractory Acute Lymphoblastic Leukemia* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT04546906) (`https://clinicaltrials.gov/study/NCT04546906`)
- **[E18]** **NCT06612645** *Safety and Efficacy of CMD03 CAR T Cell in Children With Relapse or Refractory Solid Tumors* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06612645) (`https://clinicaltrials.gov/study/NCT06612645`)
- **[E19]** **NCT07078929** *Clinical Trial of CMD63 Chimeric Antigen Receptor T-cell (CAR T-cell) in Children With Acute Lymphoblastic Leukemia (ALL)* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT07078929) (`https://clinicaltrials.gov/study/NCT07078929`)
- **[E20]** **NCT06481735** *TCR Reserved and Power3 (SPPL3) Gene Knock-out Allogeneic CD19-targeting CAR-T Cell Therapy in r/r B-ALL* [Source: `` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://clinicaltrials.gov/study/NCT06481735) (`https://clinicaltrials.gov/study/NCT06481735`)

## 11. Generated Manuscript & Visual Figures

- **Publication Manuscript (PDF):** `runs/run-20260921-073015/manuscript.pdf`

## 12. Pipeline Warnings & Notes

- No record survived screening. The eligibility criteria may be too strict, or the search may have retrieved the wrong literature. See screening.excluded_records for the reasons.

---
*Disclaimer: This report was generated by the SRMA Agent for clinical research synthesis and decision support. Every statistical value was computed deterministically in Python (NumPy/SciPy) from extracted study data. Verify primary clinical records via the links above before clinical or regulatory use.*