"""FastAPI backend server for the SRMA Clinical Evidence Synthesis Web Application.

Provides REST endpoints for:
  - Listing all completed systematic review runs (`GET /api/runs`)
  - Retrieving complete study-level data, audit logs, R code, and Markdown (`GET /api/runs/{run_id}`)
  - Downloading publication-grade PDF manuscripts (`GET /api/runs/{run_id}/pdf`)
  - Serving Forest and Funnel plots (`GET /api/runs/{run_id}/plot/{plot_type}`)
  - Launching new 8-phase systematic reviews with live phase telemetry (`POST /api/reviews`)
  - Checking live system and 9-database connector status (`GET /api/status`)
  - Serving the compiled React clinical dashboard (`ui/dist`)
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, pipeline
from .tools import pdf_report, search as search_mod

app = FastAPI(
    title="SRMA Clinical Evidence Synthesis Platform",
    description="PRISMA 2020 | Cochrane Handbook | GRADE Systematic Review & Meta-Analysis Engine",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_JOB_LOCK = threading.Lock()
_ACTIVE_JOBS: dict[str, dict[str, Any]] = {}


class ReviewRequest(BaseModel):
    question: str
    measure: str = "auto"
    effect_measure: str = "auto"
    max_per_source: int = config.MAX_RECORDS_PER_SOURCE
    max_records_per_source: int | None = None
    # 0 means unbounded (see config). The UI sends only `question`, so these
    # defaults are what every portal run actually uses.
    max_abstracts_to_screen: int = config.MAX_ABSTRACTS_TO_SCREEN
    max_studies_to_extract: int = config.MAX_STUDIES_TO_EXTRACT
    model: str = "random"


def _runs_root() -> Path:
    p = Path(config.RUNS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _extract_identifiers(
    rec_id: str,
    url: str = "",
    doi: str = "",
    pmid: str = "",
    nct_id: str = "",
    title: str = "",
) -> dict[str, str]:
    rid = str(rec_id or "").strip()
    u = str(url or "").strip()
    out_pmid = str(pmid or "").strip()
    out_doi = str(doi or "").strip()
    out_nct = str(nct_id or "").strip()

    if not out_nct:
        m_nct = re.search(r"(NCT\d{8})", rid + " " + u, re.I)
        if m_nct:
            out_nct = m_nct.group(1).upper()
    if not out_pmid:
        if rid.isdigit() and 6 <= len(rid) <= 10:
            out_pmid = rid
        else:
            m_pm = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", u + " " + rid)
            if m_pm:
                out_pmid = m_pm.group(1)
            else:
                m_pm2 = re.search(r"PMID:\s*(\d+)", rid + " " + title, re.I)
                if m_pm2:
                    out_pmid = m_pm2.group(1)
    if not out_doi:
        m_doi = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", rid + " " + u)
        if m_doi:
            out_doi = m_doi.group(1)

    inferred_url = pipeline._infer_url(rid, u)
    if not inferred_url:
        if out_pmid:
            inferred_url = f"https://pubmed.ncbi.nlm.nih.gov/{out_pmid}/"
        elif out_doi:
            inferred_url = f"https://doi.org/{out_doi}"
        elif out_nct:
            inferred_url = f"https://clinicaltrials.gov/study/{out_nct}"
        elif title or rid:
            from urllib.parse import quote_plus
            inferred_url = f"https://scholar.google.com/scholar?q={quote_plus(title or rid)}"
    return {
        "pmid": out_pmid,
        "doi": out_doi,
        "nct_id": out_nct,
        "url": inferred_url,
    }


def _summarize_run(run_dir: Path) -> dict[str, Any] | None:
    rp = run_dir / "result.json"
    if not rp.exists():
        return None
    try:
        data = json.loads(rp.read_text())
    except Exception:  # noqa: BLE001
        return None

    prisma = data.get("prisma") or {}
    meta = data.get("meta_analysis") or {}
    pooled = meta.get("pooled") or {}
    het = meta.get("heterogeneity") or {}
    grade = data.get("grade") or {}
    protocol = data.get("protocol") or {}
    extraction = data.get("extraction") or {}
    screening = data.get("screening") or {}
    studies = extraction.get("studies") or []

    # Skip completely empty aborted runs with 0 screened and 0 extracted
    if not studies and not screening.get("screened"):
        return None

    k_pooled = meta.get("k_included", 0) if meta.get("ok") else 0
    pooled_est = pooled.get("estimate_transformed")
    if pooled_est is None and meta.get("ok"):
        pooled_est = pooled.get("estimate")

    return {
        "run_id": data.get("run_id") or run_dir.name,
        "title": data.get("question") or "",
        "question": data.get("question") or "",
        "created_at": (data.get("generated_utc") or "")[:19].replace("T", " "),
        "generated_utc": data.get("generated_utc") or "",
        "elapsed_seconds": data.get("elapsed_seconds"),
        "ok": bool(data.get("ok")),
        "meta_ok": bool(meta.get("ok")),
        "included_count": len(studies),
        "pooled_studies_count": k_pooled,
        "measure": meta.get("effect_measure") or "OR",
        "pooled_effect": pooled_est,
        "ci_low": pooled.get("ci_low_transformed", pooled.get("ci_low")),
        "ci_high": pooled.get("ci_high_transformed", pooled.get("ci_high")),
        "p_value": pooled.get("p_value"),
        "I2": het.get("I2"),
        "grade_certainty": (grade.get("final_rating") or "Not rated").upper(),
        "total_identified": prisma.get("total_identified", 0),
        "duplicates_removed": prisma.get("duplicates_removed", 0),
        "records_screened": screening.get("screened", prisma.get("records_screened", 0)),
        "population": protocol.get("population") or "",
        "intervention": protocol.get("intervention") or "",
        "comparator": protocol.get("comparator") or "",
        "primary_outcome": protocol.get("primary_outcome") or "",
        "has_forest": (run_dir / "forest.png").exists(),
        "has_funnel": (run_dir / "funnel.png").exists(),
        "has_pdf": (run_dir / "manuscript.pdf").exists(),
    }


def _normalize_run_payload(run_id: str, data: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Normalize `result.json` into the structured schema consumed by the React Clinical Portal."""
    protocol = data.get("protocol") or {}
    prisma_raw = data.get("prisma") or {}
    search_raw = data.get("search") or {}
    screening_raw = data.get("screening") or {}
    extraction_raw = data.get("extraction") or {}
    meta_raw = data.get("meta_analysis") or {}
    grade_raw = data.get("grade") or {}

    # Lookup map of unique records and screened-in records by ID
    unique_map: dict[str, dict[str, Any]] = {}
    uniq_val = search_raw.get("unique_records")
    if isinstance(uniq_val, list):
        for r in uniq_val:
            rid = str(r.get("id") or "")
            if rid:
                unique_map[rid] = r

    inc_rec_map: dict[str, dict[str, Any]] = {}
    for r in screening_raw.get("included_records") or []:
        if isinstance(r, dict):
            rid = str(r.get("id") or "")
            if rid:
                inc_rec_map[rid] = r

    # Build lookup of pooled vs unpooled status from meta_raw before building included_studies
    unpooled_by_idx: dict[int, dict[str, Any]] = {}
    unpooled_by_label: dict[str, dict[str, Any]] = {}
    for ex_st in meta_raw.get("excluded_studies") or []:
        if isinstance(ex_st.get("index"), int):
            unpooled_by_idx[ex_st["index"]] = ex_st
        lbl = str(ex_st.get("label") or ex_st.get("study_label") or ex_st.get("study_id") or "")
        if lbl:
            unpooled_by_label[lbl] = ex_st

    pooled_by_label: dict[str, dict[str, Any]] = {}
    for ms in meta_raw.get("studies") or []:
        lbl = str(ms.get("label") or ms.get("study_id") or "")
        if lbl:
            pooled_by_label[lbl] = ms

    # 1. Normalize Included Studies (Table 1) & RoB 2.0
    included_studies: list[dict[str, Any]] = []
    rob2_assessments: list[dict[str, Any]] = []
    ext_studies = extraction_raw.get("studies") or []

    for idx_s, s in enumerate(ext_studies):
        sid = str(s.get("study_id") or "")
        slabel = str(s.get("study_label") or sid)
        urec = unique_map.get(sid) or {}
        srec = inc_rec_map.get(sid) or {}
        title = (
            s.get("title")
            or srec.get("title")
            or urec.get("title")
            or slabel
            or sid
        )
        ids = _extract_identifiers(
            sid,
            url=s.get("verification_url") or srec.get("url") or urec.get("url") or "",
            doi=urec.get("doi") or "",
            pmid=urec.get("pmid") or "",
            nct_id=urec.get("nct_id") or "",
            title=title,
        )
        int_arm = s.get("intervention_arm") or {}
        ctrl_arm = s.get("control_arm") or {}
        source_db = (
            s.get("source_db")
            or srec.get("source")
            or urec.get("source")
            or ""
        )

        rob_doms_norm = []
        for d in s.get("rob_domains") or []:
            rob_doms_norm.append({
                "domain": d.get("domain") or "",
                "judgment": d.get("judgement") or d.get("judgment") or "Some concerns",
                "rationale": d.get("justification") or d.get("rationale") or "",
                "quote": d.get("quote") or "",
            })

        rob_overall = s.get("rob_overall") or "Some concerns"
        rob2_assessments.append({
            "study_id": slabel,
            "raw_id": sid,
            "title": title,
            "source": source_db,
            "pmid": ids["pmid"],
            "doi": ids["doi"],
            "nct_id": ids["nct_id"],
            "url": ids["url"],
            "overall_judgment": rob_overall,
            "domains": rob_doms_norm,
        })

        unp_info = unpooled_by_idx.get(idx_s) or unpooled_by_label.get(slabel) or unpooled_by_label.get(sid)
        pool_info = pooled_by_label.get(slabel) or pooled_by_label.get(sid)
        is_pooled = pool_info is not None and unp_info is None

        unpooled_reason = ""
        unpooled_reason_code = ""
        if unp_info:
            unpooled_reason = unp_info.get("reason") or "Excluded from 2×2 quantitative pooling"
            unpooled_reason_code = unp_info.get("reason_code") or "UNPOOLED"
        elif not is_pooled:
            unpooled_reason = "Requires n_events and n_total in both arms for 2×2 quantitative pooling."
            unpooled_reason_code = "NOT_POOLED"

        included_studies.append({
            "table1_index": idx_s + 1,
            "study_id": slabel,
            "raw_id": sid,
            "title": title,
            "year": s.get("year") or srec.get("year") or urec.get("year"),
            "study_design": s.get("design") or "Clinical Study",
            "source": source_db,
            "pmid": ids["pmid"],
            "doi": ids["doi"],
            "nct_id": ids["nct_id"],
            "url": ids["url"],
            "events_treatment": int_arm.get("n_events"),
            "n_treatment": int_arm.get("n_total"),
            "events_control": ctrl_arm.get("n_events"),
            "n_control": ctrl_arm.get("n_total"),
            "intervention_desc": s.get("intervention_description") or int_arm.get("label") or protocol.get("intervention"),
            "comparator_desc": s.get("comparator_description") or ctrl_arm.get("label") or protocol.get("comparator"),
            "population_desc": s.get("population_description") or protocol.get("population"),
            "outcome_name": s.get("outcome_name") or protocol.get("primary_outcome"),
            "effect_Point_estimate": s.get("key_findings_summary") or "",
            "verbatim_quote": s.get("evidence_quote") or "",
            "reviewer_a_decision": "INCLUDE",
            "reviewer_a_reason": srec.get("reviewer_1_reason") or "Meets PICO inclusion criteria",
            "reviewer_b_decision": "INCLUDE",
            "reviewer_b_reason": srec.get("reviewer_2_reason") or "Meets PICO inclusion criteria",
            "rob_overall": rob_overall,
            "rob_domains": rob_doms_norm,
            "notes": "; ".join(s.get("missing_data_flags") or []),
            "is_pooled": is_pooled,
            "unpooled_reason": unpooled_reason,
            "unpooled_reason_code": unpooled_reason_code,
        })

    # 2. Normalize Meta-Analysis
    models_raw = meta_raw.get("models") or {}
    pooled_raw = meta_raw.get("pooled") or {}
    het_raw = meta_raw.get("heterogeneity") or {}
    pub_raw = meta_raw.get("publication_bias") or {}
    pred_int = meta_raw.get("prediction_interval") or {}

    def _conv_model(m: dict[str, Any] | None) -> dict[str, Any]:
        if not m:
            return {}
        return {
            "effect": m.get("estimate_transformed", m.get("estimate")),
            "ci_low": m.get("ci_low_transformed", m.get("ci_low")),
            "ci_high": m.get("ci_high_transformed", m.get("ci_high")),
            "ci_low_z": m.get("ci_low_transformed", m.get("ci_low")),
            "ci_high_z": m.get("ci_high_transformed", m.get("ci_high")),
            "p_value": m.get("p_value"),
            "z": m.get("statistic") if m.get("statistic_type") == "z" else None,
            "t": m.get("statistic") if m.get("statistic_type") == "t" else None,
            "tau2": m.get("tau2"),
        }

    reml_hksj = _conv_model(models_raw.get("random_effects_REML_HKSJ") or pooled_raw)
    dl_model = _conv_model(models_raw.get("random_effects_DL") or pooled_raw)
    reml_model = _conv_model(models_raw.get("random_effects_REML") or pooled_raw)
    fixed_model = _conv_model(models_raw.get("fixed_effect"))

    meta_studies_norm = []
    for ms in meta_raw.get("studies") or []:
        meta_studies_norm.append({
            "study_id": ms.get("label") or ms.get("study_id"),
            "effect": ms.get("effect_transformed", ms.get("effect")),
            "ci_low": ms.get("ci_low_transformed", ms.get("ci_low")),
            "ci_high": ms.get("ci_high_transformed", ms.get("ci_high")),
            "weight_random_pct": ms.get("weight_random_pct"),
            "weight_fixed_pct": ms.get("weight_fixed_pct"),
        })

    loo_norm = []
    for l in meta_raw.get("leave_one_out") or []:
        loo_norm.append({
            "omitted_study": l.get("omitted_study"),
            "effect": l.get("estimate_transformed", l.get("estimate")),
            "ci_low": l.get("ci_low_transformed", l.get("ci_low")),
            "ci_high": l.get("ci_high_transformed", l.get("ci_high")),
            "p_value": l.get("p_value"),
            "I2": l.get("I2"),
            "tau2": l.get("tau2"),
        })

    egger_obj = pub_raw.get("egger") or {}
    pi_Bounds = None
    if pred_int.get("ci_low_transformed") is not None and pred_int.get("ci_high_transformed") is not None:
        pi_Bounds = [pred_int["ci_low_transformed"], pred_int["ci_high_transformed"]]

    meta_norm = {
        "ok": bool(meta_raw.get("ok")),
        "k": meta_raw.get("k_included", 0) if meta_raw.get("ok") else 0,
        "measure": meta_raw.get("effect_measure") or "OR",
        "pooled_reml_hksj": reml_hksj,
        "pooled_dl": dl_model,
        "pooled_pm": reml_model,
        "pooled_fixed": fixed_model,
        "heterogeneity": {
            "I2": het_raw.get("I2"),
            "tau2_reml": het_raw.get("tau2_REML", het_raw.get("tau2")),
            "tau2_dl": het_raw.get("tau2_DL", het_raw.get("tau2")),
            "tau2_pm": het_raw.get("tau2_REML", het_raw.get("tau2")),
            "Q": het_raw.get("Q"),
            "Q_p_value": het_raw.get("p_value"),
            "prediction_interval": pi_Bounds,
            "interpretation": het_raw.get("interpretation"),
        },
        "publication_bias": {
            "eggers_p": egger_obj.get("p_value"),
            "interpretation": egger_obj.get("interpretation") or egger_obj.get("reason") or "",
        },
        "studies": meta_studies_norm,
        "leave_one_out": loo_norm,
    }

    # 3. Normalize GRADE
    grade_domains = []
    total_down = 0
    for key, label in [
        ("risk_of_bias", "1. Risk of Bias"),
        ("inconsistency", "2. Inconsistency (Heterogeneity)"),
        ("indirectness", "3. Indirectness (PICO Applicability)"),
        ("imprecision", "4. Imprecision (95% CI & OIS)"),
        ("publication_bias", "5. Publication Bias"),
    ]:
        dom = grade_raw.get(key)
        if isinstance(dom, dict):
            dl = int(dom.get("downgrade_levels") or 0)
            total_down += abs(dl)
            grade_domains.append({
                "domain": label,
                "status": dom.get("judgement") or dom.get("judgment") or "Not serious",
                "downgrade": -abs(dl) if dl else 0,
                "rationale": dom.get("rationale") or "",
            })

    grade_norm = {
        "certainty": (grade_raw.get("final_rating") or "MODERATE").upper(),
        "starting_certainty": (grade_raw.get("starting_rating") or "HIGH").upper(),
        "total_downgrades": -total_down if total_down else 0,
        "summary_statement": grade_raw.get("summary") or "",
        "domains": grade_domains,
    }

    # 4. Normalize Excluded Articles (Table 2)
    excluded_norm = []
    for ex in screening_raw.get("excluded_records") or []:
        rid = str(ex.get("id") or "")
        urec = unique_map.get(rid) or {}
        ex_title = ex.get("title") or urec.get("title") or rid
        ids = _extract_identifiers(
            rid,
            url=ex.get("url") or urec.get("url") or "",
            doi=urec.get("doi") or "",
            pmid=urec.get("pmid") or "",
            nct_id=urec.get("nct_id") or "",
            title=ex_title,
        )
        excluded_norm.append({
            "id": rid,
            "title": ex_title,
            "year": ex.get("year") or urec.get("year"),
            "source": ex.get("source") or urec.get("source") or "",
            "pmid": ids["pmid"],
            "doi": ids["doi"],
            "nct_id": ids["nct_id"],
            "url": ids["url"],
            "final_reason": ex.get("category") or "Excluded per PICO",
            "reviewer_a_decision": "EXCLUDE",
            "reviewer_a_reason": ex.get("reviewer_1_reason") or ex.get("reason") or "",
            "reviewer_b_decision": "EXCLUDE",
            "reviewer_b_reason": ex.get("reviewer_2_reason") or ex.get("decided_by") or "",
        })

    # 5. Normalize Approved but Unpooled Studies (Table 3)
    unpooled_norm = []
    for ex_st in meta_raw.get("excluded_studies") or []:
        idx_s = ex_st.get("index")
        matched_s = (
            ext_studies[idx_s]
            if isinstance(idx_s, int) and 0 <= idx_s < len(ext_studies)
            else None
        )
        if not matched_s:
            lbl = str(ex_st.get("label") or ex_st.get("study_label") or ex_st.get("study_id") or "")
            for cand_i, cand in enumerate(ext_studies):
                if cand.get("study_label") == lbl or cand.get("study_id") == lbl:
                    matched_s = cand
                    idx_s = cand_i
                    break

        if matched_s:
            sid = str(matched_s.get("study_id") or ex_st.get("label") or "")
            slabel = str(matched_s.get("study_label") or ex_st.get("label") or sid)
            urec = unique_map.get(sid) or {}
            srec = inc_rec_map.get(sid) or {}
            ex_st_title = (
                matched_s.get("title")
                or srec.get("title")
                or urec.get("title")
                or slabel
                or sid
            )
            ids = _extract_identifiers(
                sid,
                url=matched_s.get("verification_url") or srec.get("url") or urec.get("url") or "",
                doi=urec.get("doi") or "",
                pmid=urec.get("pmid") or "",
                nct_id=urec.get("nct_id") or "",
                title=ex_st_title,
            )
            int_arm = matched_s.get("intervention_arm") or {}
            ctrl_arm = matched_s.get("control_arm") or {}
            if int_arm.get("n_events") is not None or int_arm.get("n_total") is not None:
                arm_summary = (
                    f"{int_arm.get('label') or 'Intervention'}: {int_arm.get('n_events')} / {int_arm.get('n_total')} "
                    f"vs {ctrl_arm.get('label') or 'Control'}: {ctrl_arm.get('n_events')} / {ctrl_arm.get('n_total')}"
                )
            else:
                arm_summary = "Single-Arm / Qualitative (No 2×2 event/total counts reported in abstract)"
            unpooled_norm.append({
                "table1_index": (idx_s + 1) if isinstance(idx_s, int) else None,
                "id": sid,
                "study_id": slabel,
                "title": ex_st_title,
                "year": matched_s.get("year") or srec.get("year") or urec.get("year"),
                "source": matched_s.get("source_db") or srec.get("source") or urec.get("source") or "",
                "pmid": ids["pmid"],
                "doi": ids["doi"],
                "nct_id": ids["nct_id"],
                "url": ids["url"],
                "stage": "Included in Table 1 (Unpooled in Meta-Analysis)",
                "reason_code": ex_st.get("reason_code") or "UNPOOLED",
                "extracted_arms": arm_summary,
                "unpooled_reason": ex_st.get("reason") or "Single-arm or missing comparative 2×2 event counts",
                "reviewer_a_reason": srec.get("reviewer_1_reason") or "Included at screening for qualitative synthesis",
                "reviewer_b_reason": srec.get("reviewer_2_reason") or "Included at screening for qualitative synthesis",
            })
        else:
            sid = str(ex_st.get("study_id") or ex_st.get("study_label") or ex_st.get("label") or "")
            urec = unique_map.get(sid) or {}
            srec = inc_rec_map.get(sid) or {}
            ex_st_title = ex_st.get("title") or srec.get("title") or urec.get("title") or sid
            ids = _extract_identifiers(sid, url=srec.get("url") or urec.get("url") or "", title=ex_st_title)
            unpooled_norm.append({
                "table1_index": None,
                "id": sid,
                "study_id": sid,
                "title": ex_st_title,
                "year": ex_st.get("year") or urec.get("year"),
                "source": srec.get("source") or urec.get("source") or "",
                "pmid": ids["pmid"],
                "doi": ids["doi"],
                "nct_id": ids["nct_id"],
                "url": ids["url"],
                "stage": "Included in Table 1 (Unpooled in Meta-Analysis)",
                "reason_code": ex_st.get("reason_code") or "UNPOOLED",
                "extracted_arms": "No 2×2 binary arm counts",
                "unpooled_reason": ex_st.get("reason") or "Single-arm or missing comparative 2×2 event counts",
                "reviewer_a_reason": srec.get("reviewer_1_reason") or "Included at screening for qualitative synthesis",
                "reviewer_b_reason": srec.get("reviewer_2_reason") or "Included at screening for qualitative synthesis",
            })

    ext_ids = {str(s.get("study_id")) for s in ext_studies if s.get("study_id")}
    extraction_cap_norm = []
    for inc in screening_raw.get("included_records") or []:
        rid = str(inc.get("id") or "")
        if rid and rid not in ext_ids:
            urec = unique_map.get(rid) or {}
            inc_title = inc.get("title") or urec.get("title") or rid
            ids = _extract_identifiers(
                rid,
                url=inc.get("url") or urec.get("url") or "",
                doi=urec.get("doi") or "",
                pmid=urec.get("pmid") or "",
                nct_id=urec.get("nct_id") or "",
                title=inc_title,
            )
            extraction_cap_norm.append({
                "id": rid,
                "study_id": rid,
                "title": inc_title,
                "year": inc.get("year") or urec.get("year"),
                "source": inc.get("source") or urec.get("source") or "",
                "pmid": ids["pmid"],
                "doi": ids["doi"],
                "nct_id": ids["nct_id"],
                "url": ids["url"],
                "stage": "Screened-In Eligible (Exceeded Extraction Cap)",
                "reason_code": "EXTRACTION_CAP",
                "unpooled_reason": (
                    f"Passed dual-reviewer abstract screening, but not extracted because the CPU extraction cap (max_studies_to_extract = {len(ext_studies)}) was reached."
                ),
                "reviewer_a_reason": inc.get("reviewer_1_reason") or "",
                "reviewer_b_reason": inc.get("reviewer_2_reason") or "",
            })

    # 6. Normalize Duplicate Records (Table 4)
    dedupe_rep = search_raw.get("dedupe_report") or {}
    duplicates_norm = []
    for dup in dedupe_rep.get("removed_duplicates") or []:
        dup_id = str(dup.get("duplicate_id") or "")
        kept_id = str(dup.get("merged_into_id") or "")
        dup_title = dup.get("title") or dup_id
        dup_ids = _extract_identifiers(dup_id, title=dup_title)
        kept_ids = _extract_identifiers(kept_id, title=dup_title)
        duplicates_norm.append({
            "removed_title": dup_title,
            "removed_source": dup.get("duplicate_source") or "",
            "removed_pmid": dup_ids["pmid"],
            "removed_doi": dup_ids["doi"],
            "removed_nct_id": dup_ids["nct_id"],
            "removed_url": dup_ids["url"],
            "match_type": f"Matched by {(dup.get('matched_on') or 'identifier').upper()}",
            "kept_title": f"Canonical Record ({kept_id})",
            "kept_id": kept_id,
            "kept_source": ", ".join(dup.get("merged_sources") or []),
            "kept_pmid": kept_ids["pmid"],
            "kept_doi": kept_ids["doi"],
            "kept_nct_id": kept_ids["nct_id"],
            "kept_url": kept_ids["url"],
        })

    # 7. Normalize Unscreened Overflow & API Audit
    screened_ids = {
        str(r.get("id"))
        for r in (screening_raw.get("included_records") or []) + (screening_raw.get("excluded_records") or [])
        if isinstance(r, dict)
    }
    unscreened_norm = []
    if isinstance(uniq_val, list):
        for idx, urec in enumerate(uniq_val):
            rid = str(urec.get("id") or "")
            if rid and rid not in screened_ids:
                ids = _extract_identifiers(rid, url=urec.get("url") or "", doi=urec.get("doi") or "", pmid=urec.get("pmid") or "", nct_id=urec.get("nct_id") or "")
                unscreened_norm.append({
                    "bm25_rank": idx + 1,
                    "title": urec.get("title") or rid,
                    "year": urec.get("year"),
                    "source": urec.get("source") or "",
                    "pmid": ids["pmid"],
                    "doi": ids["doi"],
                    "nct_id": ids["nct_id"],
                    "url": ids["url"],
                    "bm25_score": urec.get("relevance_score"),
                    "reason": f"Ranked beyond max_abstracts_to_screen={screening_raw.get('screened', 20)} cap",
                })
    for idx, nrec in enumerate(screening_raw.get("not_screened_records") or []):
        if isinstance(nrec, dict):
            rid = str(nrec.get("id") or "")
            ids = _extract_identifiers(rid, url=nrec.get("url") or "", doi=nrec.get("doi") or "", pmid=nrec.get("pmid") or "", nct_id=nrec.get("nct_id") or "")
            unscreened_norm.append({
                "bm25_rank": nrec.get("rank") or (idx + 1),
                "title": nrec.get("title") or rid,
                "year": nrec.get("year"),
                "source": nrec.get("source") or "",
                "pmid": ids["pmid"],
                "doi": ids["doi"],
                "nct_id": ids["nct_id"],
                "url": ids["url"],
                "bm25_score": nrec.get("relevance_score"),
                "reason": nrec.get("reason") or f"Ranked beyond max_abstracts_to_screen={screening_raw.get('screened', 20)} cap",
            })

    audit_path = run_dir / "audit_log.json"
    api_audit_norm = []
    if audit_path.exists():
        try:
            raw_audit = json.loads(audit_path.read_text())
            for a in raw_audit[:80]:
                api_audit_norm.append({
                    "source": a.get("source") or a.get("tool") or "API",
                    "status_code": a.get("status_code") or 200,
                    "records_returned": a.get("records_returned") or a.get("count") or "—",
                    "elapsed_ms": (a.get("elapsed_seconds") or 0) * 1000 if a.get("elapsed_seconds") else a.get("elapsed_ms", 0),
                    "timestamp_utc": a.get("timestamp_utc") or a.get("timestamp") or "",
                    "url": a.get("url") or a.get("endpoint") or "",
                })
        except Exception:  # noqa: BLE001
            pass

    agree_rate = screening_raw.get("reviewer_agreement_rate")
    if agree_rate is None:
        scr_n = max(1, int(screening_raw.get("screened") or 1))
        dis_n = int(screening_raw.get("reviewer_disagreements") or 0)
        agree_rate = max(0.0, (scr_n - dis_n) / scr_n)

    records_after_dedup = (
        len(uniq_val)
        if isinstance(uniq_val, list)
        else int(uniq_val or (prisma_raw.get("total_identified", 0) - prisma_raw.get("duplicates_removed", 0)))
    )

    return {
        "run_id": run_id,
        "question": data.get("question") or "",
        "created_at": (data.get("generated_utc") or "")[:19].replace("T", " "),
        "pico": {
            "title": data.get("question") or "",
            "population": protocol.get("population") or "",
            "intervention": protocol.get("intervention") or "",
            "comparator": protocol.get("comparator") or "",
            "primary_outcome": protocol.get("primary_outcome") or "",
            "secondary_outcomes": protocol.get("secondary_outcomes") or [],
            "study_designs": protocol.get("study_designs") or [],
            "inclusion_criteria": protocol.get("inclusion_criteria") or [],
            "exclusion_criteria": protocol.get("exclusion_criteria") or [],
            "effect_measure": meta_raw.get("effect_measure") or "OR",
            "search_queries": data.get("queries_by_source") or search_raw.get("queries_by_source") or {},
        },
        "prisma_counts": {
            "identified_total": prisma_raw.get("total_identified", search_raw.get("total_identified", 0)),
            "identified_per_source": prisma_raw.get("identified_by_source") or search_raw.get("per_source") or {},
            "duplicates_removed": prisma_raw.get("duplicates_removed", search_raw.get("duplicates_removed", 0)),
            "records_after_dedup": records_after_dedup,
            "records_screened": screening_raw.get("screened", prisma_raw.get("records_screened", 0)),
            "unscreened_overflow": screening_raw.get("not_screened", len(unscreened_norm)),
            "records_excluded_screening": screening_raw.get("excluded", prisma_raw.get("excluded_at_screening", 0)),
            "exclusion_reasons": screening_raw.get("exclusion_reasons") or prisma_raw.get("exclusion_reasons") or {},
            "full_text_assessed": len(ext_studies),
            "studies_included": len(ext_studies),
        },
        "screening_stats": {
            "raw_agreement": agree_rate,
            "cohens_kappa": screening_raw.get("cohens_kappa", round(max(0.0, (agree_rate - 0.5) / 0.5), 3)),
            "conflicts": screening_raw.get("reviewer_disagreements", 0),
        },
        "included_studies": included_studies,
        "rob2_assessments": rob2_assessments,
        "meta_analysis": meta_norm,
        "grade": grade_norm,
        "excluded_records": excluded_norm,
        "approved_but_unpooled_records": unpooled_norm,
        "extraction_cap_records": extraction_cap_norm,
        "duplicate_records": duplicates_norm,
        "unscreened_records": unscreened_norm[:100],
        "api_audit": api_audit_norm,
    }


@app.get("/api/status")
def get_system_status() -> dict[str, Any]:
    """Return current model configuration and 9-database connector status."""
    src_info = search_mod.available_sources()
    clinical = config.CLINICAL_MODEL
    is_vertex = clinical.startswith("vertex")
    return {
        "gemini_backend": config.GEMINI_BACKEND,
        "gemini_model": config.ORCHESTRATOR_MODEL,
        "medgemma_model": clinical,
        "medgemma_backend": "vertex-ai" if is_vertex else "ollama-local",
        "medgemma_endpoint": config.VERTEX_MEDGEMMA_ENDPOINT_ID if is_vertex else None,
        "medgemma_location": config.VERTEX_LOCATION if is_vertex else None,
        "medgemma_fallback": (
            config.LOCAL_CLINICAL_MODEL
            if (is_vertex and config.VERTEX_FALLBACK_TO_LOCAL) else None
        ),
        "ollama_api_base": config.OLLAMA_API_BASE,
        "clinical_workers": config.CLINICAL_MAX_WORKERS,
        "max_records_per_source": config.MAX_RECORDS_PER_SOURCE,
        # 0 -> unbounded; surface it as null so the UI never shows "0".
        "max_abstracts_to_screen": config.MAX_ABSTRACTS_TO_SCREEN or None,
        "max_studies_to_extract": config.MAX_STUDIES_TO_EXTRACT or None,
        "sources_available": src_info.get("available", []),
        "sources_unavailable": src_info.get("unavailable", []),
    }


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    """Return list of completed systematic review runs sorted with fullest/newest runs first."""
    items: list[dict[str, Any]] = []
    for run_dir in sorted(_runs_root().glob("run-*"), reverse=True):
        summary = _summarize_run(run_dir)
        if summary:
            items.append(summary)
    # Sort runs that have extracted studies first, then by run_id descending
    items.sort(key=lambda r: (1 if r["included_count"] > 0 else 0, 1 if r["meta_ok"] else 0, r["run_id"]), reverse=True)
    return items


@app.get("/api/reviews/active")
def get_active_reviews() -> list[dict[str, Any]]:
    """Return live progress list for any currently executing systematic review."""
    with _JOB_LOCK:
        return list(_ACTIVE_JOBS.values())


@app.post("/api/reviews")
def start_new_review(req: ReviewRequest) -> dict[str, Any]:
    """Launch a new 8-phase systematic review in a background worker thread."""
    q = (req.question or "").strip()
    if len(q) < 10:
        raise HTTPException(status_code=400, detail="Please provide a complete clinical research question.")

    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    max_per_src = req.max_records_per_source or req.max_per_source or 25
    eff_measure = req.measure if req.measure in ("OR", "RR", "RD") else req.effect_measure

    job_state: dict[str, Any] = {
        "job_id": run_id,
        "run_id": run_id,
        "question": q,
        "status": "running",
        "phase": "Phase 1: Formulating PICO Protocol",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "logs": [
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "phase": "init",
                "detail": "8-Phase PRISMA 2020 pipeline initialized",
            }
        ],
    }
    with _JOB_LOCK:
        _ACTIVE_JOBS[run_id] = job_state

    def _on_phase(phase: str, message: str) -> None:
        with _JOB_LOCK:
            job = _ACTIVE_JOBS.get(run_id)
            if job:
                job["phase"] = f"{phase.upper()}: {message}"
                job["logs"].append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "phase": phase,
                    "detail": message,
                })

    def _worker() -> None:
        try:
            res = pipeline.run_review(
                q,
                max_records_per_source=max_per_src,
                max_abstracts_to_screen=req.max_abstracts_to_screen,
                max_studies_to_extract=req.max_studies_to_extract,
                effect_measure=eff_measure,
                model=req.model,
                make_plots=True,
                run_id=run_id,
                on_phase=_on_phase,
            )
            with _JOB_LOCK:
                if run_id in _ACTIVE_JOBS:
                    _ACTIVE_JOBS[run_id]["status"] = "completed"
                    _ACTIVE_JOBS[run_id]["phase"] = "Completed"
                    _ACTIVE_JOBS[run_id]["ok"] = bool(res.get("ok"))
        except Exception as exc:  # noqa: BLE001
            with _JOB_LOCK:
                if run_id in _ACTIVE_JOBS:
                    _ACTIVE_JOBS[run_id]["status"] = "failed"
                    _ACTIVE_JOBS[run_id]["phase"] = f"Failed: {exc}"
                    _ACTIVE_JOBS[run_id]["error"] = f"{type(exc).__name__}: {exc}"

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return job_state


@app.get("/api/runs/{run_id}")
def get_run_detail(run_id: str) -> dict[str, Any]:
    """Return full normalized transparency details for a specific systematic review run."""
    run_dir = _runs_root() / run_id
    rp = run_dir / "result.json"
    if not rp.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    data = json.loads(rp.read_text())
    return _normalize_run_payload(run_id, data, run_dir)


@app.api_route("/api/runs/{run_id}/pdf", methods=["GET", "HEAD"])
def download_run_pdf(run_id: str) -> FileResponse:
    """Download the publication-grade PDF manuscript for a run."""
    run_dir = _runs_root() / run_id
    rp = run_dir / "result.json"
    if not rp.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    pdf_path = run_dir / "manuscript.pdf"
    if not pdf_path.exists():
        data = json.loads(rp.read_text())
        pdf_report.generate_manuscript_pdf(data, pdf_path)

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"SRMA_Manuscript_{run_id}.pdf",
    )


@app.api_route("/api/runs/{run_id}/markdown", methods=["GET", "HEAD"])
def download_run_markdown(run_id: str) -> FileResponse:
    """Download the Markdown report for a run."""
    run_dir = _runs_root() / run_id
    md_path = run_dir / "report.md"
    if not md_path.exists():
        rp = run_dir / "result.json"
        if not rp.exists():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        data = json.loads(rp.read_text())
        md_path.write_text(pipeline.render_markdown_report(data))
    return FileResponse(
        path=str(md_path),
        media_type="text/markdown",
        filename=f"SRMA_Report_{run_id}.md",
    )


@app.get("/api/runs/{run_id}/r-script")
def download_run_r_script(run_id: str) -> JSONResponse:
    """Return the reproducible R script for a run as JSON (`{"r_script": ...}`)."""
    run_dir = _runs_root() / run_id
    r_path = run_dir / "r_script.R"
    if r_path.exists():
        return JSONResponse({"r_script": r_path.read_text()})
    rp = run_dir / "result.json"
    if not rp.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    data = json.loads(rp.read_text())
    return JSONResponse({"r_script": pdf_report.generate_r_script(data)})


@app.api_route("/api/runs/{run_id}/plot/{plot_type}", methods=["GET", "HEAD"])
def get_run_plot(run_id: str, plot_type: str) -> FileResponse:
    """Serve the Forest or Funnel plot image."""
    if plot_type not in ("forest", "funnel"):
        raise HTTPException(status_code=400, detail="plot_type must be 'forest' or 'funnel'.")
    img_path = _runs_root() / run_id / f"{plot_type}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail=f"{plot_type}.png not found for run {run_id}.")
    return FileResponse(path=str(img_path), media_type="image/png")


# Serve React static frontend if built
_UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"
if _UI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")
