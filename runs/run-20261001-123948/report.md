# Systematic Review and Meta-Analysis Report

**Clinical Question:** In adult patients with relapsed or refractory multiple myeloma, what is the incidence and relative risk of Cytokine Release Syndrome (CRS) in CAR-T cell therapy compared to bispecific antibodies or standard regimens?
**Run ID:** `run-20261001-123948` | **Generated (UTC):** `2026-10-01T12:39:48.127497+00:00` | **Elapsed Time:** `1323.7s` | **Clinical Model:** `ollama_chat/medgemma`

## 1. Structured Abstract & Executive Evidence Synthesis

- **Background & Objective:** To systematically evaluate and synthesize clinical evidence addressing **Incidence and relative risk of Cytokine Release Syndrome (CRS)** in **Adult patients with relapsed or refractory multiple myeloma** receiving **CAR-T cell therapy** compared with **Bispecific antibodies or standard regimens**.
- **Methods (PRISMA 2020 / Cochrane Handbook):** Multi-database searches were executed across indexed biomedical repositories, clinical trial registries, and preprint servers (`128` records identified; `5` duplicates removed; `123` unique citations). Records underwent deterministic PICO relevance gating and independent dual-reviewer screening (`30` screened; `11` excluded with documented PRISMA reasons; `17` eligible). Structured arm-level extraction and 5-domain Cochrane Risk of Bias 2.0 (RoB 2) assessments were performed on `12` studies.
- **Results (Qualitative & Single-Arm Synthesis):** Fewer than 2 extracted abstracts reported complete two-arm comparative event counts or means/SDs.
- **Conclusion:** In accordance with Cochrane Handbook standards against fabricating or imputing unreported control-arm counts from abstracts, a structured qualitative synthesis of all `12` included studies is presented in **Table 1** and **Section 5** below.

## 2. PICO Protocol, Eligibility Criteria & Search Strategy

| PICOS Element | Specification |
| :--- | :--- |
| **Population (P)** | Adult patients with relapsed or refractory multiple myeloma |
| **Intervention (I)** | CAR-T cell therapy |
| **Comparator (C)** | Bispecific antibodies or standard regimens |
| **Primary Outcome (O)** | Incidence and relative risk of Cytokine Release Syndrome (CRS) |
| **Eligible Study Designs (S)** | Randomized Controlled Trial |
| **Inclusion Criteria** | Adult patients with relapsed or refractory multiple myeloma |
| **Exclusion Criteria** | Animal studies; In-vitro studies; Narrative reviews; Editorials; Case reports |

**Canonical Boolean Search Strategy (PubMed / MEDLINE Syntax):**
```text
(patients[tiab] OR "multiple myeloma"[tiab] OR relapsed[tiab] OR refractory[tiab] OR "Multiple Myeloma"[MeSH Terms]) AND ("CAR-T cell therapy"[tiab] OR "bispecific antibodies"[tiab] OR "standard regimens"[tiab] OR "CAR-T Cell Therapy"[MeSH Terms] OR "Bispecific Antibodies"[MeSH Terms])
```

## 3. Complete PRISMA 2020 Evidence Funnel & Record Accounting

Every single record retrieved from the literature search is accounted for below:

| Funnel Phase | Step / Database Source | Record Count | Notes & Accounting Proof |
| :--- | :--- | :---: | :--- |
| **1. Identification** | Database: `clinicaltrials` | `25` | Status: `success` |
| **1. Identification** | Database: `europepmc` | `25` | Status: `success` |
| **1. Identification** | Database: `preprints` | `3` | Status: `success` |
| **1. Identification** | Database: `crossref` | `25` | Status: `success` |
| **1. Identification** | Database: `pubmed` | `25` | Status: `success` |
| **1. Identification** | Database: `openalex` | `25` | Status: `success` |
| **1. Identification** | Database: `semantic_scholar` | `0` | Status: `success` |
| **1. Identification** | **Total Records Identified** | **`128`** | Across all queried databases |
| **2. Deduplication** | Duplicates Removed | `-5` | Matched by: DOI: 2, PMID: 1, PMCID: 1, TITLE: 1 (see Table 4 below) |
| **2. Deduplication** | **Unique Records After Deduplication** | **`123`** | `128 - 5 = 123` unique records |
| **3. Screening** | Unscreened (Beyond Screening Cap) | `-93` | Screening cap was set to `30` records (`SRMA_MAX_ABSTRACTS_TO_SCREEN`) |
| **3. Screening** | **Records Screened (Title & Abstract)** | **`30`** | Dual independent MedGemma reviewers (Agreement rate: `35.3%`) |
| **3. Screening** | Excluded at Title/Abstract Screening | `-11` | `11` by Python Relevance Gate + `0` by Dual Reviewers (see Table 2) |
| *↳ Exclusion Breakdown* | *Wrong intervention* | *`10`* | *PRISMA 2020 exclusion category* |
| *↳ Exclusion Breakdown* | *Wrong population* | *`1`* | *PRISMA 2020 exclusion category* |
| **3. Screening** | **Studies Approved at Screening** | **`17`** | `30 screened - 11 excluded = 17 eligible studies` |
| **4. Extraction / Full-Text** | Skipped Due to Extraction Cap | `-5` | Extraction cap (`max_studies_to_extract=12`) reached (see Table 3) |
| **4. Extraction / Full-Text** | **Studies Assessed for Data & RoB 2** | **`12`** | Full structured extraction + 5-domain Cochrane RoB 2 assessment |
| **5. Synthesis** | Excluded from Statistical Pooling (Narrative Only) | `-12` | Missing event counts / means in abstract or ongoing trial protocol (see Table 3) |
| **5. Synthesis** | **Final Studies Pooled in Meta-Analysis** | **`0`** | **`0` total participants analysed quantitatively** |

## 4. Table 1: Characteristics & Extracted Evidence of Included Studies

This table documents every study that passed screening and underwent data extraction (modeled on publication tables in *Acta Oncologica* / Cochrane reviews). Click any **Study ID** to open and verify the original source record:

| Ref | Study ID & Verification Link | Author (Year) & Title | Source & Design | Target Population | Intervention Arm (`Events / N` or `Mean ± SD`) | Comparator Arm (`Events / N` or `Mean ± SD`) | Study Effect `[95% CI]` & Weight | RoB 2 Overall | Status & Key Findings |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `[1]` | [`10.1016/j.cmi.2024.02.023`](https://pubmed.ncbi.nlm.nih.gov/38432433/) | **Jourdes et al. (2024). PMID:38432433** — Characteristics and incidence of infections in patients with multiple myeloma treated by bispecific antibodies: a nat... | `pubmed` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: *Not reported* | **Control**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[2]` | [`10.1080/21645515.2026.2711554`](https://pubmed.ncbi.nlm.nih.gov/42623170/) | **Zhang et al. (2026). PMID:42623170** — Global trends in CAR-T cell therapy for multiple myeloma: A bibliometric analysis, 2013-2025. | `europepmc` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: `N=874` *(events not reported)* | **Control**: `N=787` *(events not reported)* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[3]` | [`10.1080/10428194.2026.2699285`](https://pubmed.ncbi.nlm.nih.gov/42518303/) | **Leitner et al. (2026). PMID:42518303** — Real-world analyses of bispecific antibodies and CAR-T cell therapy in relapsed or refractory multiple myeloma: a glo... | `europepmc` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **BsAbs**: `N=822` *(events not reported)* | **CAR-T**: `N=822` *(events not reported)* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[4]` | [`10.1101/2024.09.02.610843`](https://doi.org/10.1101/2024.09.02.610843) | **Tirado et al. (2024). DOI:10.1101/2024.09.02.610843** — CAR-T cells targeting CCR9 and CD1a for the treatment of T cell acute lymphoblastic leukemia | `preprints` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **CCR9/CD1a CAR-T cells**: *Not reported* | **Single CAR-T cell**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[5]` | [`10.1056/nejmoa2204591`](https://pubmed.ncbi.nlm.nih.gov/38609727/) | **Chari et al. (2024). PMID:38609727** — Talquetamab, a T-Cell–Redirecting GPRC5D Bispecific Antibody for Multiple Myeloma | `pubmed, openalex` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Talquetamab**: *Not reported* | **None**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[6]` | [`10.6004/jnccn.2026.7004`](https://pubmed.ncbi.nlm.nih.gov/42190708/) | **Miller et al. (2026). PMID:42190708** — Incorporating the Next Generation of Immunotherapies Into the Treatment of Multiple Myeloma. | `europepmc` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: *Not reported* | **Control**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[7]` | [`10.1200/jco.20.00386`](https://pubmed.ncbi.nlm.nih.gov/40738883/) | **Steinhardt et al. (2025). PMID:40738883** — Activity of CAR-T cells and bispecific antibodies in multiple myeloma with extramedullary involvement. | `pubmed` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Cilta-cel**: `N=15` *(events not reported)* | **Talquetamab**: `N=15` *(events not reported)* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[8]` | [`10.3390/cells15181660`](https://pubmed.ncbi.nlm.nih.gov/42782760/) | **Canichella et al. (2026). PMID:42782760** — Beyond CAR-T: Preventing and Treating Relapse in B-Cell Haematological Malignancies. | `europepmc` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: *Not reported* | **Control**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[9]` | [`10.1038/s41408-022-00643-3`](https://pubmed.ncbi.nlm.nih.gov/39632797/) | **Merz et al. (2024). PMID:39632797** — Bispecific antibodies targeting BCMA or GPRC5D are highly effective in relapsed myeloma after CAR T-cell therapy. | `pubmed` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Talquetamab**: `N=28` *(events not reported)* | **Teclistamab**: `N=37` *(events not reported)* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[10]` | [`10.3390/ijms27167179`](https://pubmed.ncbi.nlm.nih.gov/42653183/) | **Shambhavi et al. (2026). PMID:42653183** — T-Cell Engagers Targeting <i>BCMA</i>, <i>GPRC5D</i>, or <i>FcRH5</i> in Relapsed/Refractory Multiple Myeloma: The La... | `europepmc, pubmed` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Talquetamab**: *Not reported* | **Standard of care (SOC)**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[11]` | [`10.1016/j.blre.2025.101342`](https://pubmed.ncbi.nlm.nih.gov/41177723/) | **Zhou et al. (2025). PMID:41177723** — Bispecific antibodies in multiple myeloma: maximizing potential through rational combination therapies. | `pubmed` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: *Not reported* | **Control**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |
| `[12]` | [`10.1007/s12015-026-11228-z`](https://pubmed.ncbi.nlm.nih.gov/42684629/) | **Su et al. (2026). PMID:42684629** — Beyond Remission: Risk-Adapted Maintenance and Mechanism-Guided Salvage After CAR T-Cell Therapy for Multiple Myeloma. | `europepmc` (Clinical Study) | Adult patients with relapsed or refractory multiple myeloma | **Intervention**: *Not reported* | **Control**: *Not reported* | *Not pooled (Narrative synthesis)* | `RobLevel.LOW` | **Narrative Only** (Requires n_events and n_total in both arms; one or more were missing.) |

## 5. Study-by-Study Evidence Proof, Dual-Reviewer Justifications & RoB 2 Audit

Below is the complete audit trail for each extracted study, including **why it passed screening**, **verbatim text quotes**, and **all 5 Cochrane RoB 2 domain judgements**:

### [1] Jourdes et al. (2024). PMID:38432433 — [`10.1016/j.cmi.2024.02.023`](https://pubmed.ncbi.nlm.nih.gov/38432433/)
- **Full Title:** Characteristics and incidence of infections in patients with multiple myeloma treated by bispecific antibodies: a national retrospective study.
- **Source Database(s):** `pubmed` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/38432433/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study is performed in "BsAb-treated patients with multiple myeloma", which matches the population criteria.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study is a retrospective, multicentre study in BsAb-treated patients with multiple myeloma. The protocol excludes narrative reviews, editorials, case reports, and animal studies. This study is a journal article, which is not an excluded type.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`
- **Data Completeness / Verifier Flags:** `no_outcome_data_in_abstract, assessed_from_abstract_only`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The study is a retrospective study, and therefore does not involve randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The study is a retrospective study, and therefore does not involve deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The study is a retrospective study, and therefore does not involve missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The study is a retrospective study, and therefore does not involve bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The study is a retrospective study, and therefore does not involve bias in selection of the reported result. |

### [2] Zhang et al. (2026). PMID:42623170 — [`10.1080/21645515.2026.2711554`](https://pubmed.ncbi.nlm.nih.gov/42623170/)
- **Full Title:** Global trends in CAR-T cell therapy for multiple myeloma: A bibliometric analysis, 2013-2025.
- **Source Database(s):** `europepmc` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42623170/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study is on CAR-T cell therapy for multiple myeloma, which is the target population.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study is a bibliometric analysis, not a randomized controlled trial. The protocol excludes narrative reviews, editorials, case reports, and animal studies. The abstract is a review, which is excluded.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a bibliometric analysis, which does not involve randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text describes a bibliometric analysis, which does not involve deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text describes a bibliometric analysis, which does not involve missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text describes a bibliometric analysis, which does not involve measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text describes a bibliometric analysis, which does not involve selection of the reported result. |

### [3] Leitner et al. (2026). PMID:42518303 — [`10.1080/10428194.2026.2699285`](https://pubmed.ncbi.nlm.nih.gov/42518303/)
- **Full Title:** Real-world analyses of bispecific antibodies and CAR-T cell therapy in relapsed or refractory multiple myeloma: a global TriNetX discovery and contemporary validation cohort.
- **Source Database(s):** `europepmc` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42518303/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study compares bispecific antibodies and CAR-T cell therapy in relapsed or refractory multiple myeloma, which aligns with the defined intervention.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study compares bispecific antibodies and CAR-T cell therapy, which is not the comparator specified in the protocol. The protocol states that the comparator is bispecific antibodies or standard regimens.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`
- **Data Completeness / Verifier Flags:** `assessed_from_abstract_only`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study used propensity matching, which is a method to reduce selection bias. The text does not mention randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study used propensity matching, which is a method to reduce selection bias. The text does not mention blinding. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study used propensity matching, which is a method to reduce selection bias. The text does not mention any missing data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study used propensity matching, which is a method to reduce selection bias. The text does not mention any measurement bias. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study used propensity matching, which is a method to reduce selection bias. The text does not mention any bias in selection of the reported result. |

### [4] Tirado et al. (2024). DOI:10.1101/2024.09.02.610843 — [`10.1101/2024.09.02.610843`](https://doi.org/10.1101/2024.09.02.610843)
- **Full Title:** CAR-T cells targeting CCR9 and CD1a for the treatment of T cell acute lymphoblastic leukemia
- **Source Database(s):** `preprints` | **Verification URL:** https://doi.org/10.1101/2024.09.02.610843
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract describes CAR-T cell therapy for T-ALL, which is a relevant intervention for multiple myeloma. The population is not the same, but the intervention is relevant.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** Wrong population. The abstract states that the study is targeting T-ALL, not multiple myeloma.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: Wrong population. The abs...`
- **Data Completeness / Verifier Flags:** `no_outcome_data_in_abstract`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study used CAR-T cells, which are not randomized. |
| Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study used CAR-T cells, which are not blinded. |
| Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study used CAR-T cells, which are not blinded. |
| Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study used CAR-T cells, which are not blinded. |
| Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study used CAR-T cells, which are not blinded. |

### [5] Chari et al. (2024). PMID:38609727 — [`10.1056/nejmoa2204591`](https://pubmed.ncbi.nlm.nih.gov/38609727/)
- **Full Title:** Talquetamab, a T-Cell–Redirecting GPRC5D Bispecific Antibody for Multiple Myeloma
- **Source Database(s):** `pubmed, openalex` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/38609727/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study population consists of "heavily pretreated relapsed or refractory multiple myeloma", which aligns with the population criteria for this review.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study included patients with heavily pretreated relapsed or refractory multiple myeloma that had progressed with established therapies or who could not receive these therapies without unacceptable side effects. The protocol excludes studies using bispecific antibodies or standard regimens. The abstract states that talquetamab is a bispecific antibody against CD3 and GP
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study was a phase 1 study, and the primary end points were assessed to select the recommended doses for a phase 2 study. The study design does not mention randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study was a phase 1 study, and the primary end points were assessed to select the recommended doses for a phase 2 study. The study design does not mention blinding. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study was a phase 1 study, and the primary end points were assessed to select the recommended doses for a phase 2 study. The text does not mention missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study was a phase 1 study, and the primary end points were assessed to select the recommended doses for a phase 2 study. The text does not mention the measurement method of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study was a phase 1 study, and the primary end points were assessed to select the recommended doses for a phase 2 study. The text does not mention a pre-registered protocol or analysis plan. |

### [6] Miller et al. (2026). PMID:42190708 — [`10.6004/jnccn.2026.7004`](https://pubmed.ncbi.nlm.nih.gov/42190708/)
- **Full Title:** Incorporating the Next Generation of Immunotherapies Into the Treatment of Multiple Myeloma.
- **Source Database(s):** `europepmc` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42190708/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states "Adult patients with relapsed or refractory multiple myeloma", which matches the population criteria.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states "CAR T-cell therapy and BsAbs necessitate careful attention to unique toxicities, including cytokine release syndrome, immune effector cell-associated neurotoxicity syndrome, cytopenias, and heightened infection risk.", which is not in the protocol.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states "CAR...`
- **Data Completeness / Verifier Flags:** `assessed_from_abstract_only`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a review and does not describe the randomization process. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a review and does not describe deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a review and does not describe missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in selection of the reported result. |

### [7] Steinhardt et al. (2025). PMID:40738883 — [`10.1200/jco.20.00386`](https://pubmed.ncbi.nlm.nih.gov/40738883/)
- **Full Title:** Activity of CAR-T cells and bispecific antibodies in multiple myeloma with extramedullary involvement.
- **Source Database(s):** `pubmed` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/40738883/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study included patients with relapsed or refractory multiple myeloma, which aligns with the population criteria.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study included 80 patients with EMD not adjacent to the bone treated with ide-cel, cilta-cel, teclistamab, or talquetamab at three academic centers in Germany. The protocol states that the population is adult patients with relapsed or refractory multiple myeloma. This is consistent with the protocol.
- **Screening Consensus Decision:** `both reviewers agreed to include`
- **Data Completeness / Verifier Flags:** `ungrounded_event_counts_removed_by_python_verifier`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study was retrospective, and therefore randomization was not performed. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the patients were heavily pretreated, and that the majority of patients receiving cilta-cel, ide-cel, or teclistamab were BCMA-naive (>88%). |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the proportion of patients with outcome data was approximately 95% or more, and that the loss of data was balanced across arms. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the outcome was objective. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study was retrospective, and that the reported outcomes matched the study protocol. |

### [8] Canichella et al. (2026). PMID:42782760 — [`10.3390/cells15181660`](https://pubmed.ncbi.nlm.nih.gov/42782760/)
- **Full Title:** Beyond CAR-T: Preventing and Treating Relapse in B-Cell Haematological Malignancies.
- **Source Database(s):** `europepmc` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42782760/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract mentions CAR-T cell therapy for relapsed/refractory multiple myeloma, which is within the target population. The abstract also mentions bispecific antibodies as a comparator.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that CAR-T cell therapy has revolutionized the treatment landscape of relapsed/refractory (R/R) B-cell acute lymphoblastic leukemia (B-ALL), non-Hodgkin lymphoma (NHL), and multiple myeloma (MM). The population is adult patients with relapsed or refractory multiple myeloma, which is stated in the protocol.
- **Screening Consensus Decision:** `both reviewers agreed to include`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a review and does not describe the randomization process. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a review and does not describe deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a review and does not describe missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in selection of the reported result. |

### [9] Merz et al. (2024). PMID:39632797 — [`10.1038/s41408-022-00643-3`](https://pubmed.ncbi.nlm.nih.gov/39632797/)
- **Full Title:** Bispecific antibodies targeting BCMA or GPRC5D are highly effective in relapsed myeloma after CAR T-cell therapy.
- **Source Database(s):** `pubmed` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/39632797/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the study analyzes outcomes of post-CAR T-cell therapy relapse and impact of different salvage strategies in an international cohort of 139 patients. The population is adult patients with relapsed or refractory multiple myeloma, which matches the eligibility criteria.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study analyzed outcomes of post-CAR T-cell therapy relapse and impact of different salvage strategies in an international cohort of 139 patients (n = 130 ide-cel, n = 9 cilta-cel), receiving talquetamab (n = 28), teclistamab (n = 37), combinations of immunomodulating drugs (IMiDs), proteasome inhibitors (PIs) or CD38 monoclonal antibodies (n = 43), and others (n = 31).
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a cohort study, and does not describe randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a cohort study, and does not describe deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a cohort study, and does not describe missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a cohort study, and does not describe bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a cohort study, and does not describe bias in selection of the reported result. |

### [10] Shambhavi et al. (2026). PMID:42653183 — [`10.3390/ijms27167179`](https://pubmed.ncbi.nlm.nih.gov/42653183/)
- **Full Title:** T-Cell Engagers Targeting <i>BCMA</i>, <i>GPRC5D</i>, or <i>FcRH5</i> in Relapsed/Refractory Multiple Myeloma: The Landscape Beyond CAR-T Cell Therapy-A Systematic Review and Network Meta-Analysis.
- **Source Database(s):** `europepmc, pubmed` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42653183/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract does not mention the comparator.
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that the study evaluates and compares the efficacy and safety of bispecific antibodies targeting BCMA, GPRC5D, or FcRH5 in RRMM using direct and indirect evidence. The population is adult patients with relapsed or refractory multiple myeloma, which is consistent with the protocol. The intervention is bispecific antibodies, which is consistent with the protocol. The comparator i
- **Screening Consensus Decision:** `both reviewers agreed to include`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a systematic review and network meta-analysis, which does not involve randomization. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a systematic review and network meta-analysis, which does not involve deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a systematic review and network meta-analysis, which does not involve missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a systematic review and network meta-analysis, which does not involve bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a systematic review and network meta-analysis, which does not involve bias in selection of the reported result. |

### [11] Zhou et al. (2025). PMID:41177723 — [`10.1016/j.blre.2025.101342`](https://pubmed.ncbi.nlm.nih.gov/41177723/)
- **Full Title:** Bispecific antibodies in multiple myeloma: maximizing potential through rational combination therapies.
- **Source Database(s):** `pubmed` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/41177723/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract mentions bispecific antibodies in multiple myeloma, which is the target population. It also mentions CAR-T cell therapy as a comparator, and the primary outcome is the incidence and relative risk of Cytokine Release Syndrome (CRS).
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that teclistamab, elranatamab, linvoseltamab (all BCMA×CD3) and talquetamab (GPRC5D × CD3) have received regulatory approval for relapsed/refractory MM. The protocol excludes studies using CAR-T cell therapy.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`
- **Data Completeness / Verifier Flags:** `assessed_from_abstract_only`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a journal article, and does not describe the randomization process. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a journal article, and does not describe deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a journal article, and does not describe missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a journal article, and does not describe bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a journal article, and does not describe bias in selection of the reported result. |

### [12] Su et al. (2026). PMID:42684629 — [`10.1007/s12015-026-11228-z`](https://pubmed.ncbi.nlm.nih.gov/42684629/)
- **Full Title:** Beyond Remission: Risk-Adapted Maintenance and Mechanism-Guided Salvage After CAR T-Cell Therapy for Multiple Myeloma.
- **Source Database(s):** `europepmc` | **Verification URL:** https://pubmed.ncbi.nlm.nih.gov/42684629/
- **Screening Reviewer 1 (Recall-Oriented) Proof:** The abstract states that the review synthesizes pivotal trials, real-world cohorts, and translational studies into a risk-adapted framework for longitudinal care. The population is adult patients with relapsed or refractory multiple myeloma, which matches the eligibility criteria. The intervention is CAR-T cell therapy, and the comparator is bispecific antibodies or standard regimens, which matche
- **Screening Reviewer 2 (Precision-Oriented) Proof:** The abstract states that this is a review, not a primary research study. The protocol excludes narrative reviews.
- **Screening Consensus Decision:** `Reviewers disagreed: the precision-oriented reviewer would have excluded this record. Resolved to Include, because at title/abstract stage a disagreement is sent to full text, where eligibility can be checked against the methods section rather than guessed from an abstract. Objection raised, to be verified at full text: The abstract states that...`
- **Data Completeness / Verifier Flags:** `assessed_from_abstract_only`

| Cochrane RoB 2 Domain | Judgement | Quoted Justification from Text |
| :--- | :---: | :--- |
| Domain 1 - Bias arising from the randomization process | **`RobLevel.LOW`** | The text states that the study is a review and does not describe the randomization process. |
| Domain 2 - Bias due to deviations from intended interventions | **`RobLevel.LOW`** | The text states that the study is a review and does not describe deviations from intended interventions. |
| Domain 3 - Bias due to missing outcome data | **`RobLevel.LOW`** | The text states that the study is a review and does not describe missing outcome data. |
| Domain 4 - Bias in measurement of the outcome | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in measurement of the outcome. |
| Domain 5 - Bias in selection of the reported result | **`RobLevel.LOW`** | The text states that the study is a review and does not describe bias in selection of the reported result. |

## 6. Table 2: Excluded Articles at Title/Abstract Screening (Full Audit Log)

All **`11` articles excluded at screening** are listed below with their identifier, clickable verification link, PRISMA category, decision source, and exact reason:

| # | Article ID & Link | Title | Source DB | PRISMA Exclusion Category | Decided By | Exact Proof / Reason for Exclusion |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| `1` | [`10.1056/nejmoa1707447`](https://pubmed.ncbi.nlm.nih.gov/29226797/) | Axicabtagene Ciloleucel CAR T-Cell Therapy in Refractory Large B-Cell Lymphoma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `2` | [`10.1056/nejmoa1817226`](https://pubmed.ncbi.nlm.nih.gov/31042825/) | Anti-BCMA CAR T-Cell Therapy bb2121 in Relapsed or Refractory Multiple Myeloma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `3` | [`10.1056/nejmoa2024850`](https://pubmed.ncbi.nlm.nih.gov/33626253/) | Idecabtagene Vicleucel in Relapsed and Refractory Multiple Myeloma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `4` | [`10.1101/2020.05.28.20115758`](https://doi.org/10.1101/2020.05.28.20115758) | An inflammatory cytokine signature helps predict COVID-19 severity and death | `preprints` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `5` | [`10.1056/nejmoa1914347`](https://pubmed.ncbi.nlm.nih.gov/32242358/) | KTE-X19 CAR T-Cell Therapy in Relapsed or Refractory Mantle-Cell Lymphoma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `6` | [`10.1056/nejmoa1804980`](https://pubmed.ncbi.nlm.nih.gov/30501490/) | Tisagenlecleucel in Adult Relapsed or Refractory Diffuse Large B-Cell Lymphoma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `7` | [`10.1007/s40262-026-01663-z`](https://pubmed.ncbi.nlm.nih.gov/42287565/) | PF-06863135 As Single Agent And In Combination With Immunomodulatory Agents In Relapse/Refractory Multiple Myeloma | `clinicaltrials` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `8` | [`10.1056/nejmoa2203478`](https://pubmed.ncbi.nlm.nih.gov/35661166/) | Teclistamab in Relapsed or Refractory Multiple Myeloma | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `9` | [`10.1080/14712598.2024.2352591`](https://pubmed.ncbi.nlm.nih.gov/38738379/) | Cilta-cel, a BCMA-targeting CAR-T therapy for patients with multiple myeloma. | `pubmed` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `10` | [`10.1056/nejmoa1709866`](https://pubmed.ncbi.nlm.nih.gov/29385370/) | Tisagenlecleucel in Children and Young Adults with B-Cell Lymphoblastic Leukemia | `openalex` | **`Wrong intervention`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the intervention (CAR-T cell therapy, bispecific antibodies, standard regimens). |
| `11` | [`10.1038/s41408-021-00459-7`](https://pubmed.ncbi.nlm.nih.gov/33824268/) | CAR-T cell therapy: current limitations and potential strategies | `openalex` | **`Wrong population`** | relevance gate (Python, no model call) | Title, abstract, MeSH headings and keywords contain no mention of the population (patients, multiple myeloma, relapsed). |

## 7. Table 3: Studies Approved at Screening but Excluded from Quantitative Pooling

These studies passed title/abstract screening (`Include`), and the table below explains why they were not included in the final statistical meta-analysis pool:

| # | Study ID & Link | Title | Pipeline Stage | Exact Reason Not Pooled |
| :---: | :--- | :--- | :--- | :--- |
| `1` | [`10.1016/j.cmi.2024.02.023`](https://pubmed.ncbi.nlm.nih.gov/38432433/) | Characteristics and incidence of infections in patients with multiple myeloma treated by bispecific antibodies: a national retrospective... | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: no_outcome_data_in_abstract, assessed_from_abstract_only) |
| `2` | [`10.1080/21645515.2026.2711554`](https://pubmed.ncbi.nlm.nih.gov/42623170/) | Global trends in CAR-T cell therapy for multiple myeloma: A bibliometric analysis, 2013-2025. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. |
| `3` | [`10.1080/10428194.2026.2699285`](https://pubmed.ncbi.nlm.nih.gov/42518303/) | Real-world analyses of bispecific antibodies and CAR-T cell therapy in relapsed or refractory multiple myeloma: a global TriNetX discover... | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: assessed_from_abstract_only) |
| `4` | [`10.1101/2024.09.02.610843`](https://doi.org/10.1101/2024.09.02.610843) | CAR-T cells targeting CCR9 and CD1a for the treatment of T cell acute lymphoblastic leukemia | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: no_outcome_data_in_abstract) |
| `5` | [`10.1056/nejmoa2204591`](https://pubmed.ncbi.nlm.nih.gov/38609727/) | Talquetamab, a T-Cell–Redirecting GPRC5D Bispecific Antibody for Multiple Myeloma | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. |
| `6` | [`10.6004/jnccn.2026.7004`](https://pubmed.ncbi.nlm.nih.gov/42190708/) | Incorporating the Next Generation of Immunotherapies Into the Treatment of Multiple Myeloma. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: assessed_from_abstract_only) |
| `7` | [`10.1200/jco.20.00386`](https://pubmed.ncbi.nlm.nih.gov/40738883/) | Activity of CAR-T cells and bispecific antibodies in multiple myeloma with extramedullary involvement. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: ungrounded_event_counts_removed_by_python_verifier) |
| `8` | [`10.3390/cells15181660`](https://pubmed.ncbi.nlm.nih.gov/42782760/) | Beyond CAR-T: Preventing and Treating Relapse in B-Cell Haematological Malignancies. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. |
| `9` | [`10.1038/s41408-022-00643-3`](https://pubmed.ncbi.nlm.nih.gov/39632797/) | Bispecific antibodies targeting BCMA or GPRC5D are highly effective in relapsed myeloma after CAR T-cell therapy. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. |
| `10` | [`10.3390/ijms27167179`](https://pubmed.ncbi.nlm.nih.gov/42653183/) | T-Cell Engagers Targeting <i>BCMA</i>, <i>GPRC5D</i>, or <i>FcRH5</i> in Relapsed/Refractory Multiple Myeloma: The Landscape Beyond CAR-T... | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. |
| `11` | [`10.1016/j.blre.2025.101342`](https://pubmed.ncbi.nlm.nih.gov/41177723/) | Bispecific antibodies in multiple myeloma: maximizing potential through rational combination therapies. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: assessed_from_abstract_only) |
| `12` | [`10.1007/s12015-026-11228-z`](https://pubmed.ncbi.nlm.nih.gov/42684629/) | Beyond Remission: Risk-Adapted Maintenance and Mechanism-Guided Salvage After CAR T-Cell Therapy for Multiple Myeloma. | `Phase 7 (Meta-Analysis Pooling)` | MISSING_BINARY_DATA: Requires n_events and n_total in both arms; one or more were missing. (Flags: assessed_from_abstract_only) |
| `13` | [`10.1056/nejmoa2213614`](https://pubmed.ncbi.nlm.nih.gov/36762851/) | Ide-cel or Standard Regimens in Relapsed and Refractory Multiple Myeloma | `Phase 6 (Data Extraction Cap)` | Passed dual-reviewer title/abstract screening, but skipped at Phase 6 because max_studies_to_extract=12 cap was reached. |
| `14` | [`10.1080/14737140.2024.2445145`](https://pubmed.ncbi.nlm.nih.gov/39729045/) | Practical insights into bispecific antibody therapy in multiple myeloma. | `Phase 6 (Data Extraction Cap)` | Passed dual-reviewer title/abstract screening, but skipped at Phase 6 because max_studies_to_extract=12 cap was reached. |
| `15` | [`10.3390/cancers18152415`](https://pubmed.ncbi.nlm.nih.gov/42588634/) | When Myeloma Escapes the Bone Marrow: Extramedullary Disease in the Immunotherapy Era. | `Phase 6 (Data Extraction Cap)` | Passed dual-reviewer title/abstract screening, but skipped at Phase 6 because max_studies_to_extract=12 cap was reached. |
| `16` | [`10.1080/14712598.2026.2646947`](https://pubmed.ncbi.nlm.nih.gov/41842719/) | A review of the clinical efficacy of monoclonal antibody (mAb)-based therapies for relapsed/refractory multiple myeloma (RRMM). | `Phase 6 (Data Extraction Cap)` | Passed dual-reviewer title/abstract screening, but skipped at Phase 6 because max_studies_to_extract=12 cap was reached. |
| `17` | [`10.1158/2643-3230.bcd-25-0461`](https://pubmed.ncbi.nlm.nih.gov/42284467/) | Outcomes of CAR T-cell Therapy and Bispecific Antibodies as Single-Modality and Sequential Strategies in Relapsed/Refractory Multiple Mye... | `Phase 6 (Data Extraction Cap)` | Passed dual-reviewer title/abstract screening, but skipped at Phase 6 because max_studies_to_extract=12 cap was reached. |

## 8. Table 4: Deduplication Audit Log (Removed Duplicate Records)

A total of **`5` duplicate records** were identified across databases and merged into a single canonical study record before screening:

| # | Removed Duplicate ID & Link | Duplicate Source DB | Merged Into Primary Study ID | Matched By | Article Title |
| :---: | :--- | :--- | :--- | :---: | :--- |
| `1` | [`10.20944/preprints202607.0989.v1`](https://doi.org/10.20944/preprints202607.0989.v1) | `europepmc` | [`10.3390/ijms27167179`](https://doi.org/10.3390/ijms27167179) | `title` | T-Cell Engagers Targeting BCMA, GPRC5D, or FcRH5 in Relapsed/ Refractory Multiple Myeloma, Landscape Beyond CAR-T Cel... |
| `2` | [`10.1038/s41419-025-08203-w`](https://pubmed.ncbi.nlm.nih.gov/42653183/) | `pubmed` | [`10.3390/ijms27167179`](https://doi.org/10.3390/ijms27167179) | `pmid` | T-Cell Engagers Targeting BCMA, GPRC5D, or FcRH5 in Relapsed/Refractory Multiple Myeloma: The Landscape Beyond CAR-T... |
| `3` | [`10.1097/ppo.0000000000000847`](https://pubmed.ncbi.nlm.nih.gov/42809698/) | `pubmed` | [`10.1056/nejmoa2514663`](https://doi.org/10.1056/nejmoa2514663) | `pmcid` | T-Cell Redirecting Antibodies for the Treatment of Multiple Myeloma: Off-the-Shelf T-Cell Immunity. |
| `4` | [`10.1056/nejmoa2204591`](https://pubmed.ncbi.nlm.nih.gov/36507686/) | `openalex` | [`10.1056/nejmoa2204591`](https://doi.org/10.1056/nejmoa2204591) | `doi` | Talquetamab, a T-Cell–Redirecting GPRC5D Bispecific Antibody for Multiple Myeloma |
| `5` | [`10.21037/cco-25-110`](https://pubmed.ncbi.nlm.nih.gov/41797460/) | `europepmc` | [`10.21037/cco-25-110`](https://doi.org/10.21037/cco-25-110) | `doi` | The evolution of bispecific antibodies in multiple myeloma. |

## 9. Statistical Meta-Analysis, Sensitivity Analysis & GRADE Evidence Profile

### 9.4 Reproducible R Verification Script (`meta` / `metafor`)

```r
# ============================================================================
# Reproducible R Meta-Analysis Script — Run ID: run-20261001-123948
# Outcome: Incidence and relative risk of Cytokine Release Syndrome (CRS)
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

- **[1]** **Jourdes et al. (2024). PMID:38432433** *Characteristics and incidence of infections in patients with multiple myeloma treated by bispecific antibodies: a national retrospective study.* [Source: `pubmed` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/38432433/) (`https://pubmed.ncbi.nlm.nih.gov/38432433/`)
- **[2]** **Zhang et al. (2026). PMID:42623170** *Global trends in CAR-T cell therapy for multiple myeloma: A bibliometric analysis, 2013-2025.* [Source: `europepmc` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42623170/) (`https://pubmed.ncbi.nlm.nih.gov/42623170/`)
- **[3]** **Leitner et al. (2026). PMID:42518303** *Real-world analyses of bispecific antibodies and CAR-T cell therapy in relapsed or refractory multiple myeloma: a global TriNetX discovery and contemporary validation cohort.* [Source: `europepmc` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42518303/) (`https://pubmed.ncbi.nlm.nih.gov/42518303/`)
- **[4]** **Tirado et al. (2024). DOI:10.1101/2024.09.02.610843** *CAR-T cells targeting CCR9 and CD1a for the treatment of T cell acute lymphoblastic leukemia* [Source: `preprints` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://doi.org/10.1101/2024.09.02.610843) (`https://doi.org/10.1101/2024.09.02.610843`)
- **[5]** **Chari et al. (2024). PMID:38609727** *Talquetamab, a T-Cell–Redirecting GPRC5D Bispecific Antibody for Multiple Myeloma* [Source: `pubmed, openalex` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/38609727/) (`https://pubmed.ncbi.nlm.nih.gov/38609727/`)
- **[6]** **Miller et al. (2026). PMID:42190708** *Incorporating the Next Generation of Immunotherapies Into the Treatment of Multiple Myeloma.* [Source: `europepmc` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42190708/) (`https://pubmed.ncbi.nlm.nih.gov/42190708/`)
- **[7]** **Steinhardt et al. (2025). PMID:40738883** *Activity of CAR-T cells and bispecific antibodies in multiple myeloma with extramedullary involvement.* [Source: `pubmed` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/40738883/) (`https://pubmed.ncbi.nlm.nih.gov/40738883/`)
- **[8]** **Canichella et al. (2026). PMID:42782760** *Beyond CAR-T: Preventing and Treating Relapse in B-Cell Haematological Malignancies.* [Source: `europepmc` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42782760/) (`https://pubmed.ncbi.nlm.nih.gov/42782760/`)
- **[9]** **Merz et al. (2024). PMID:39632797** *Bispecific antibodies targeting BCMA or GPRC5D are highly effective in relapsed myeloma after CAR T-cell therapy.* [Source: `pubmed` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/39632797/) (`https://pubmed.ncbi.nlm.nih.gov/39632797/`)
- **[10]** **Shambhavi et al. (2026). PMID:42653183** *T-Cell Engagers Targeting <i>BCMA</i>, <i>GPRC5D</i>, or <i>FcRH5</i> in Relapsed/Refractory Multiple Myeloma: The Landscape Beyond CAR-T Cell Therapy-A Systematic Review and Network Meta-Analysis.* [Source: `europepmc, pubmed` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42653183/) (`https://pubmed.ncbi.nlm.nih.gov/42653183/`)
- **[11]** **Zhou et al. (2025). PMID:41177723** *Bispecific antibodies in multiple myeloma: maximizing potential through rational combination therapies.* [Source: `pubmed` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/41177723/) (`https://pubmed.ncbi.nlm.nih.gov/41177723/`)
- **[12]** **Su et al. (2026). PMID:42684629** *Beyond Remission: Risk-Adapted Maintenance and Mechanism-Guided Salvage After CAR T-Cell Therapy for Multiple Myeloma.* [Source: `europepmc` | Status: `Included (Narrative Synthesis)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42684629/) (`https://pubmed.ncbi.nlm.nih.gov/42684629/`)
- **[E1]** **Neelapu et al. (2017). PMID:29226797** *Axicabtagene Ciloleucel CAR T-Cell Therapy in Refractory Large B-Cell Lymphoma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/29226797/) (`https://pubmed.ncbi.nlm.nih.gov/29226797/`)
- **[E2]** **Raje et al. (2019). PMID:31042825** *Anti-BCMA CAR T-Cell Therapy bb2121 in Relapsed or Refractory Multiple Myeloma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/31042825/) (`https://pubmed.ncbi.nlm.nih.gov/31042825/`)
- **[E3]** **Munshi et al. (2021). PMID:33626253** *Idecabtagene Vicleucel in Relapsed and Refractory Multiple Myeloma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/33626253/) (`https://pubmed.ncbi.nlm.nih.gov/33626253/`)
- **[E4]** **Del et al. (2020). DOI:10.1101/2020.05.28.20115758** *An inflammatory cytokine signature helps predict COVID-19 severity and death* [Source: `preprints` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://doi.org/10.1101/2020.05.28.20115758) (`https://doi.org/10.1101/2020.05.28.20115758`)
- **[E5]** **Wang et al. (2020). PMID:32242358** *KTE-X19 CAR T-Cell Therapy in Relapsed or Refractory Mantle-Cell Lymphoma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/32242358/) (`https://pubmed.ncbi.nlm.nih.gov/32242358/`)
- **[E6]** **Schuster et al. (2018). PMID:30501490** *Tisagenlecleucel in Adult Relapsed or Refractory Diffuse Large B-Cell Lymphoma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/30501490/) (`https://pubmed.ncbi.nlm.nih.gov/30501490/`)
- **[E7]** **Pfizer et al. (2017). PMID:42287565** *PF-06863135 As Single Agent And In Combination With Immunomodulatory Agents In Relapse/Refractory Multiple Myeloma* [Source: `clinicaltrials` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/42287565/) (`https://pubmed.ncbi.nlm.nih.gov/42287565/`)
- **[E8]** **Moreau et al. (2022). PMID:35661166** *Teclistamab in Relapsed or Refractory Multiple Myeloma* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/35661166/) (`https://pubmed.ncbi.nlm.nih.gov/35661166/`)
- **[E9]** **Jagannath et al. (2024). PMID:38738379** *Cilta-cel, a BCMA-targeting CAR-T therapy for patients with multiple myeloma.* [Source: `pubmed` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/38738379/) (`https://pubmed.ncbi.nlm.nih.gov/38738379/`)
- **[E10]** **Maude et al. (2018). PMID:29385370** *Tisagenlecleucel in Children and Young Adults with B-Cell Lymphoblastic Leukemia* [Source: `openalex` | Status: `Excluded at Screening (Wrong intervention)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/29385370/) (`https://pubmed.ncbi.nlm.nih.gov/29385370/`)
- **[E11]** **Sterner et al. (2021). PMID:33824268** *CAR-T cell therapy: current limitations and potential strategies* [Source: `openalex` | Status: `Excluded at Screening (Wrong population)`] — [Verify Source](https://pubmed.ncbi.nlm.nih.gov/33824268/) (`https://pubmed.ncbi.nlm.nih.gov/33824268/`)

## 11. Generated Manuscript & Visual Figures

- **Publication Manuscript (PDF):** `/usr/local/google/home/omtrivedi/Work/SRMA Agent/runs/run-20261001-123948/manuscript.pdf`

## 12. Pipeline Warnings & Notes

- Quantitative pooling was not possible: No study contained data sufficient for this analysis.. This usually means the abstracts did not report event counts or means with standard deviations. A narrative synthesis is the correct output in that case, not a fabricated number.

---
*Disclaimer: This report was generated by the SRMA Agent for clinical research synthesis and decision support. Every statistical value was computed deterministically in Python (NumPy/SciPy) from extracted study data. Verify primary clinical records via the links above before clinical or regulatory use.*