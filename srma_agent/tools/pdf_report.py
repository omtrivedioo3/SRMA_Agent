"""Publication-grade PDF manuscript generator and reproducible R code builder.

Generates a multi-page clinical systematic review and meta-analysis PDF
(`manuscript.pdf`) styled after peer-reviewed oncology and medical journals
(e.g. Acta Oncologica / Cochrane Database of Systematic Reviews) and adhering
to PRISMA 2020, Cochrane Handbook, and GRADE reporting standards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _infer_url(study_id: str, existing_url: str = "") -> str:
    """Return a canonical verification URL for a study identifier."""
    if existing_url and existing_url != "None":
        return existing_url
    sid = str(study_id or "").strip()
    if not sid:
        return ""
    if sid.startswith("http"):
        return sid
    if sid.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{sid.upper()}"
    if sid.upper().startswith("PMID:"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{sid.split(':', 1)[1].strip()}/"
    if sid.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{sid}/"
    if sid.upper().startswith("PMC"):
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{sid.upper()}/"
    if "/" in sid and sid[:3] in ("10.", "doi"):
        clean = sid.removeprefix("doi:").removeprefix("DOI:").strip()
        return f"https://doi.org/{clean}"
    return ""


def generate_r_script(result: dict[str, Any]) -> str:
    """Generate a reproducible R script (meta / metafor) from extracted study data.

    Implements Section 5 of the SRMA Agent Implementation Guide and Specification.
    """
    protocol = result.get("protocol") or {}
    extraction_info = result.get("extraction") or {}
    meta = result.get("meta_analysis") or {}
    extracted = extraction_info.get("studies") or []

    eff = meta.get("effect_measure") or "RR"
    if eff not in ("RR", "OR", "RD", "MD", "SMD"):
        eff = "RR"

    binary_rows: list[tuple[str, int, int, int, int]] = []
    cont_rows: list[tuple[str, int, float, float, int, float, float]] = []
    single_arm_rows: list[tuple[str, int, int]] = []

    for ext in extracted:
        label = str(ext.get("study_label") or ext.get("study_id") or "Study").replace('"', "'")
        ia = ext.get("intervention_arm") or {}
        ca = ext.get("control_arm") or {}
        if (
            ia.get("n_events") is not None
            and ia.get("n_total") is not None
            and ca.get("n_events") is not None
            and ca.get("n_total") is not None
        ):
            binary_rows.append((
                label,
                int(ia["n_events"]),
                int(ia["n_total"]),
                int(ca["n_events"]),
                int(ca["n_total"]),
            ))
        elif (
            ia.get("mean") is not None
            and ia.get("sd") is not None
            and ia.get("n_total") is not None
            and ca.get("mean") is not None
            and ca.get("sd") is not None
            and ca.get("n_total") is not None
        ):
            cont_rows.append((
                label,
                int(ia["n_total"]),
                float(ia["mean"]),
                float(ia["sd"]),
                int(ca["n_total"]),
                float(ca["mean"]),
                float(ca["sd"]),
            ))
        elif ia.get("n_events") is not None and ia.get("n_total") is not None:
            single_arm_rows.append((label, int(ia["n_events"]), int(ia["n_total"])))

    lines = [
        "# ============================================================================",
        f"# Reproducible R Meta-Analysis Script — Run ID: {result.get('run_id', 'SRMA')}",
        f"# Outcome: {protocol.get('primary_outcome', 'Primary Endpoint')}",
        "# Generated per PRISMA 2020 & Cochrane Handbook specifications",
        "# ============================================================================",
        "library(meta)",
        "library(metafor)",
        "",
    ]

    if binary_rows:
        studies_str = ", ".join(f'"{r[0]}"' for r in binary_rows)
        ev_e_str = ", ".join(str(r[1]) for r in binary_rows)
        n_e_str = ", ".join(str(r[2]) for r in binary_rows)
        ev_c_str = ", ".join(str(r[3]) for r in binary_rows)
        n_c_str = ", ".join(str(r[4]) for r in binary_rows)
        lines += [
            "m_data <- data.frame(",
            f"  study   = c({studies_str}),",
            f"  event_e = c({ev_e_str}),",
            f"  n_e     = c({n_e_str}),",
            f"  event_c = c({ev_c_str}),",
            f"  n_c     = c({n_c_str})",
            ")",
            "",
            "# Random-Effects Binary Meta-Analysis (Inverse Variance / REML)",
            "m_res <- metabin(",
            "  event.e = event_e, n.e = n_e,",
            "  event.c = event_c, n.c = n_c,",
            "  data    = m_data,",
            "  studlab = study,",
            '  method  = "Inverse",',
            f'  sm      = "{eff if eff in ("RR", "OR", "RD") else "RR"}",',
            "  common  = TRUE,",
            "  random  = TRUE,",
            '  method.tau = "REML",',
            "  hakn    = TRUE",
            ")",
            "",
            "summary(m_res)",
            'forest(m_res, layout = "Cochrane", col.square = "navy", prediction = TRUE, print.I2 = TRUE)',
            "funnel(m_res)",
            "# Leave-one-out sensitivity analysis",
            "metainf(m_res, pooled = 'random')",
        ]
    elif cont_rows:
        studies_str = ", ".join(f'"{r[0]}"' for r in cont_rows)
        n_e_str = ", ".join(str(r[1]) for r in cont_rows)
        m_e_str = ", ".join(str(r[2]) for r in cont_rows)
        sd_e_str = ", ".join(str(r[3]) for r in cont_rows)
        n_c_str = ", ".join(str(r[4]) for r in cont_rows)
        m_c_str = ", ".join(str(r[5]) for r in cont_rows)
        sd_c_str = ", ".join(str(r[6]) for r in cont_rows)
        lines += [
            "m_data <- data.frame(",
            f"  study  = c({studies_str}),",
            f"  n_e    = c({n_e_str}),",
            f"  mean_e = c({m_e_str}),",
            f"  sd_e   = c({sd_e_str}),",
            f"  n_c    = c({n_c_str}),",
            f"  mean_c = c({m_c_str}),",
            f"  sd_c   = c({sd_c_str})",
            ")",
            "",
            "m_res <- metacont(",
            "  n.e = n_e, mean.e = mean_e, sd.e = sd_e,",
            "  n.c = n_c, mean.c = mean_c, sd.c = sd_c,",
            "  data = m_data, studlab = study,",
            f'  sm = "{eff if eff in ("MD", "SMD") else "MD"}",',
            '  method.tau = "REML", random = TRUE',
            ")",
            "summary(m_res)",
            'forest(m_res, layout = "Cochrane", col.square = "navy", prediction = TRUE)',
        ]
    elif single_arm_rows:
        studies_str = ", ".join(f'"{r[0]}"' for r in single_arm_rows)
        ev_str = ", ".join(str(r[1]) for r in single_arm_rows)
        n_str = ", ".join(str(r[2]) for r in single_arm_rows)
        lines += [
            "# Single-Arm Proportional Meta-Analysis (Logit Transformation)",
            "m_prop_data <- data.frame(",
            f"  study = c({studies_str}),",
            f"  event = c({ev_str}),",
            f"  n     = c({n_str})",
            ")",
            "m_prop <- metaprop(event = event, n = n, studlab = study, data = m_prop_data, sm = 'PLOGIT', method.tau = 'REML')",
            "summary(m_prop)",
            'forest(m_prop, layout = "Cochrane", col.square = "navy")',
        ]
    else:
        lines += [
            "# Fewer than 2 studies reported comparative arm-level event counts or means/SDs",
            "# in the retrieved abstracts. Populate m_data below after full-text extraction:",
            "m_data <- data.frame(",
            '  study   = c("Study_1", "Study_2"),',
            "  event_e = c(NA, NA), n_e = c(NA, NA),",
            "  event_c = c(NA, NA), n_c = c(NA, NA)",
            ")",
        ]

    return "\n".join(lines)


def _clean(val: Any, max_len: int = 350) -> str:
    """Escape XML entities and truncate cleanly for ReportLab Paragraph."""
    if val is None:
        return ""
    s = " ".join(str(val).replace("\n", " ").replace("\r", " ").split()).strip()
    if len(s) > max_len:
        s = s[: max_len - 3].rstrip() + "..."
    return escape(s)


def _draw_page_chrome(canvas, doc) -> None:
    """Draw journal header rule and page numbering footer on every page."""
    canvas.saveState()
    w, h = A4
    # Top journal running header
    canvas.setStrokeColor(colors.HexColor("#1e3a5f"))
    canvas.setLineWidth(0.75)
    canvas.line(14 * mm, h - 13 * mm, w - 14 * mm, h - 13 * mm)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(colors.HexColor("#1e3a5f"))
    canvas.drawString(14 * mm, h - 11 * mm, "CLINICAL EVIDENCE SYNTHESIS  |  PRISMA 2020 • COCHRANE HANDBOOK • GRADE")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawRightString(w - 14 * mm, h - 11 * mm, "Systematic Review & Meta-Analysis Manuscript")

    # Bottom footer
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.setLineWidth(0.5)
    canvas.line(14 * mm, 13 * mm, w - 14 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(
        14 * mm,
        9 * mm,
        "Generated by SRMA Agent — Deterministic Biostatistics & Auditable Clinical Evidence Pipeline",
    )
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawRightString(w - 14 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def generate_manuscript_pdf(result: dict[str, Any], output_path: str | Path) -> str:
    """Render a publication-grade PDF manuscript modeled on Manual_SRMA_Study.pdf."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Systematic Review and Meta-Analysis - {result.get('run_id', '')}",
        author="SRMA Clinical Evidence Synthesis System",
    )
    usable_w = A4[0] - 28 * mm

    base = getSampleStyleSheet()
    navy = colors.HexColor("#0f2942")
    slate = colors.HexColor("#334155")
    muted = colors.HexColor("#64748b")
    accent = colors.HexColor("#1d4ed8")
    border_col = colors.HexColor("#cbd5e1")
    bg_soft = colors.HexColor("#f8fafc")
    bg_header = colors.HexColor("#0f2942")

    st_banner = ParagraphStyle(
        "Banner",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1d4ed8"),
        spaceAfter=3,
    )
    st_title = ParagraphStyle(
        "ManuscriptTitle",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=navy,
        spaceAfter=5,
    )
    st_meta = ParagraphStyle(
        "ManuscriptMeta",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=muted,
        spaceAfter=8,
    )
    st_h1 = ParagraphStyle(
        "SectionH1",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=navy,
        spaceBefore=10,
        spaceAfter=5,
    )
    st_h2 = ParagraphStyle(
        "SectionH2",
        parent=base["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=slate,
        spaceBefore=7,
        spaceAfter=3,
    )
    st_body = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_JUSTIFY,
        spaceAfter=5,
    )
    st_abs = ParagraphStyle(
        "AbstractBody",
        parent=st_body,
        fontSize=8.3,
        leading=12,
        spaceAfter=4,
    )
    st_cell = ParagraphStyle(
        "TableCell",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor("#1e293b"),
    )
    st_cell_hdr = ParagraphStyle(
        "TableHeader",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.3,
        leading=9.5,
        textColor=colors.white,
    )
    st_code = ParagraphStyle(
        "CodeBlock",
        parent=base["Code"],
        fontName="Courier",
        fontSize=6.8,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
        backColor=colors.HexColor("#f1f5f9"),
        borderPadding=5,
        spaceAfter=6,
    )

    story: list[Any] = []

    question = result.get("question") or "Clinical Systematic Review and Meta-Analysis"
    run_id = result.get("run_id") or "N/A"
    gen_utc = result.get("generated_utc") or ""
    elapsed = result.get("elapsed_seconds") or ""
    cfg = result.get("config") or {}
    protocol = result.get("protocol") or {}
    search_info = result.get("search") or {}
    prisma = result.get("prisma") or {}
    screening_info = result.get("screening") or {}
    extraction_info = result.get("extraction") or {}
    meta = result.get("meta_analysis") or {}
    grade = result.get("grade") or {}
    plots = result.get("plots") or {}

    inc_records = screening_info.get("included_records") or []
    exc_records = screening_info.get("excluded_records") or []
    inc_by_id = {str(r.get("id")): r for r in inc_records if r.get("id")}
    extracted_studies = extraction_info.get("studies") or []
    ext_by_id = {str(s.get("study_id")): s for s in extracted_studies if s.get("study_id")}

    pooled_studies = meta.get("studies") or []
    pooled_by_key: dict[str, dict[str, Any]] = {}
    for ps in pooled_studies:
        lbl = str(ps.get("label") or "")
        pooled_by_key[lbl] = ps
        for sid, ext in ext_by_id.items():
            if sid in lbl or lbl == str(ext.get("study_label") or ""):
                pooled_by_key[sid] = ps

    meta_excluded = meta.get("excluded_studies") or []
    meta_exc_by_label = {str(e.get("label") or ""): e for e in meta_excluded}

    # ------------------------------------------------------------------
    # TITLE & MASTHEAD
    # ------------------------------------------------------------------
    story.append(Paragraph("ORIGINAL RESEARCH ARTICLE — SYSTEMATIC REVIEW AND META-ANALYSIS", st_banner))
    story.append(Paragraph(_clean(question, 300), st_title))
    story.append(
        Paragraph(
            f"<b>Protocol &amp; Run Identifier:</b> {escape(str(run_id))} &nbsp;|&nbsp; "
            f"<b>Timestamp (UTC):</b> {escape(str(gen_utc[:19]))} &nbsp;|&nbsp; "
            f"<b>Execution Duration:</b> {escape(str(elapsed))}s &nbsp;|&nbsp; "
            f"<b>Orchestrator:</b> {escape(str(cfg.get('orchestrator_model', 'Gemini')))} &nbsp;|&nbsp; "
            f"<b>Clinical Reviewer:</b> {escape(str(cfg.get('clinical_model', 'MedGemma')))}",
            st_meta,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.2, color=navy, spaceAfter=8))

    # ------------------------------------------------------------------
    # STRUCTURED CLINICAL ABSTRACT BOX (Acta Oncologica style)
    # ------------------------------------------------------------------
    tot_id = prisma.get("total_identified", search_info.get("total_identified", 0))
    dups_rem = prisma.get("duplicates_removed", search_info.get("duplicates_removed", 0))
    uniq_cnt = search_info.get("unique_records", max(0, tot_id - dups_rem))
    n_scr = screening_info.get("screened", prisma.get("records_screened", 0))
    n_exc_scr = screening_info.get("excluded", prisma.get("excluded_at_screening", 0))
    n_inc_scr = screening_info.get("included", len(inc_records))
    n_ext = len(extracted_studies)
    k_pooled = meta.get("k_included", 0) if meta.get("ok") else 0

    bg_text = (
        f"<b>Background &amp; Objective:</b> To systematically evaluate clinical evidence addressing: "
        f"<i>{_clean(question, 280)}</i>. Specifically, this review assesses "
        f"<b>{_clean(protocol.get('intervention', 'the target intervention'), 120)}</b> compared with "
        f"<b>{_clean(protocol.get('comparator', 'control/standard care'), 120)}</b> with respect to "
        f"<b>{_clean(protocol.get('primary_outcome', 'the primary clinical endpoint'), 120)}</b> in "
        f"<b>{_clean(protocol.get('population', 'eligible patients'), 140)}</b>."
    )
    methods_text = (
        f"<b>Methods:</b> Following PRISMA 2020 guidelines and the Cochrane Handbook for Systematic Reviews "
        f"of Interventions, federated literature searches were executed across indexed biomedical databases, "
        f"trial registries, and preprint servers. Records underwent deterministic 5-tier deduplication "
        f"(DOI, PMID, PMCID, NCT ID, and normalized title+year), a PICO relevance gate, and independent "
        f"dual-reviewer title/abstract screening (Recall-oriented Reviewer 1 and Precision-oriented Reviewer 2). "
        f"Eligible studies underwent structured arm-level extraction and 5-domain Cochrane Risk of Bias 2.0 (RoB 2) "
        f"assessment. Certainty of evidence was rated using the GRADE framework."
    )
    if meta.get("ok"):
        pooled = meta["pooled"]
        het = meta["heterogeneity"]
        eff_lbl = meta.get("effect_measure_label", "Effect Estimate")
        est = pooled.get("estimate_transformed") or 0.0
        ci_l = pooled.get("ci_low_transformed") or 0.0
        ci_h = pooled.get("ci_high_transformed") or 0.0
        pval = pooled.get("p_value")
        pval_str = f"{pval:.4g}" if pval is not None else "N/A"
        i2 = het.get("I2")
        tau2 = het.get("tau2")
        het_str = (
            f"Between-study heterogeneity was <i>I</i><super>2</super> = {i2:.1f}% (<i>&tau;</i><super>2</super> = {(tau2 or 0.0):.4f})."
            if i2 is not None
            else "Between-study heterogeneity was not estimable (k = 1)."
        )
        results_text = (
            f"<b>Results:</b> Of <b>{tot_id}</b> records identified across databases, <b>{dups_rem}</b> duplicates "
            f"were removed, leaving <b>{uniq_cnt}</b> unique citations. A total of <b>{n_scr}</b> records were "
            f"screened at the title/abstract level, <b>{n_exc_scr}</b> were excluded with documented PRISMA reasons, "
            f"and <b>{n_inc_scr}</b> met screening eligibility. Following full-text/abstract extraction of "
            f"<b>{n_ext}</b> studies, <b>{k_pooled}</b> comparative studies (<b>{meta.get('total_participants') or 0}</b> "
            f"total participants) contributed to quantitative synthesis. The pooled <b>{escape(str(eff_lbl))}</b> was "
            f"<b>{est:.3f}</b> (95% CI <b>{ci_l:.3f}</b> to <b>{ci_h:.3f}</b>; <i>p</i> = {pval_str}). "
            f"{het_str}"
        )
        conc_text = (
            f"<b>Conclusion &amp; GRADE Certainty:</b> {_clean(grade.get('summary') or meta.get('interpretation') or '', 320)} "
            f"(Overall GRADE Certainty: <b>{_clean(grade.get('final_rating', 'Assessed'), 40)}</b>)."
        )
    else:
        single_arm_notes: list[str] = []
        for ext in extracted_studies:
            ia = ext.get("intervention_arm") or {}
            if ia.get("n_events") is not None and ia.get("n_total"):
                pct = (int(ia["n_events"]) / int(ia["n_total"])) * 100.0
                single_arm_notes.append(
                    f"{_clean(ext.get('study_label') or ext.get('study_id'), 40)}: "
                    f"{ia['n_events']}/{ia['n_total']} ({pct:.1f}%)"
                )
        sa_str = (
            f" Single-arm event rates reported in included studies included: {'; '.join(single_arm_notes)}."
            if single_arm_notes
            else ""
        )
        results_text = (
            f"<b>Results:</b> Of <b>{tot_id}</b> records identified across databases, <b>{dups_rem}</b> duplicates "
            f"were removed, leaving <b>{uniq_cnt}</b> unique records. Out of <b>{n_scr}</b> records screened, "
            f"<b>{n_exc_scr}</b> were excluded and <b>{n_inc_scr}</b> met eligibility criteria. Data extraction and "
            f"Cochrane RoB 2 assessment were completed for <b>{n_ext}</b> studies.{sa_str}"
        )
        conc_text = (
            f"<b>Conclusion &amp; Synthesis Status:</b> Fewer than 2 extracted abstracts reported complete two-arm "
            f"comparative event counts or means/SDs; per Cochrane Handbook guardrails, findings are synthesized "
            f"qualitatively across all {n_ext} included studies in Table 1 without imputing unreported comparator data."
        )

    abs_rows = [
        [Paragraph("<b>STRUCTURED ABSTRACT</b>", ParagraphStyle("AbsHdr", parent=st_h2, textColor=navy, spaceBefore=0))],
        [Paragraph(bg_text, st_abs)],
        [Paragraph(methods_text, st_abs)],
        [Paragraph(results_text, st_abs)],
        [Paragraph(conc_text, st_abs)],
    ]
    abs_table = Table(abs_rows, colWidths=[usable_w])
    abs_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg_soft),
            ("BOX", (0, 0), (-1, -1), 0.8, navy),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ])
    )
    story.append(abs_table)
    story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # SECTION 1: PICO PROTOCOL & SEARCH STRATEGY
    # ------------------------------------------------------------------
    story.append(Paragraph("1. Protocol Specification (PICOS) &amp; Literature Search Strategy", st_h1))
    pico_rows = [
        [Paragraph("PICOS Parameter", st_cell_hdr), Paragraph("Protocol Definition &amp; Eligibility Rules", st_cell_hdr)],
        [Paragraph("<b>Population (P)</b>", st_cell), Paragraph(_clean(protocol.get("population"), 350), st_cell)],
        [Paragraph("<b>Intervention (I)</b>", st_cell), Paragraph(_clean(protocol.get("intervention"), 350), st_cell)],
        [Paragraph("<b>Comparator (C)</b>", st_cell), Paragraph(_clean(protocol.get("comparator"), 350), st_cell)],
        [Paragraph("<b>Primary Outcome (O)</b>", st_cell), Paragraph(_clean(protocol.get("primary_outcome"), 350), st_cell)],
        [
            Paragraph("<b>Eligible Study Designs (S)</b>", st_cell),
            Paragraph(_clean(", ".join(protocol.get("study_designs") or ["Randomized Controlled Trial"]), 300), st_cell),
        ],
        [
            Paragraph("<b>Inclusion Criteria</b>", st_cell),
            Paragraph(_clean("; ".join(protocol.get("inclusion_criteria") or []), 500), st_cell),
        ],
        [
            Paragraph("<b>Exclusion Criteria</b>", st_cell),
            Paragraph(_clean("; ".join(protocol.get("exclusion_criteria") or []), 500), st_cell),
        ],
    ]
    t_pico = Table(pico_rows, colWidths=[42 * mm, usable_w - 42 * mm])
    t_pico.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), bg_header),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
            ("GRID", (0, 0), (-1, -1), 0.4, border_col),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(t_pico)
    story.append(Spacer(1, 5))

    if result.get("query"):
        story.append(Paragraph("<b>Canonical PRESS-Validated Boolean Search String (PubMed / MEDLINE Dialect):</b>", st_h2))
        story.append(Paragraph(_clean(result.get("query"), 900), st_code))

    # ------------------------------------------------------------------
    # SECTION 2: PRISMA 2020 FLOW & RECORD ACCOUNTING
    # ------------------------------------------------------------------
    story.append(Paragraph("2. PRISMA 2020 Study Selection Flow &amp; Complete Record Accounting", st_h1))
    prisma_rows = [
        [
            Paragraph("PRISMA 2020 Phase", st_cell_hdr),
            Paragraph("Pipeline Stage / Database Source", st_cell_hdr),
            Paragraph("Record Count", st_cell_hdr),
            Paragraph("Methodological Notes &amp; Accounting Audit", st_cell_hdr),
        ]
    ]
    per_src = search_info.get("per_source") or {}
    for src_name, src_info in per_src.items():
        cnt = src_info.get("count", 0)
        st_str = src_info.get("status", "ok")
        prisma_rows.append([
            Paragraph("1. Identification", st_cell),
            Paragraph(f"Database: <b>{escape(str(src_name))}</b>", st_cell),
            Paragraph(f"<b>{cnt}</b>", st_cell),
            Paragraph(f"API Status: {escape(str(st_str))}", st_cell),
        ])

    dedupe_rep = search_info.get("dedupe_report") or {}
    matched_by = dedupe_rep.get("matched_by") or {}
    match_str = ", ".join(f"{k.upper()}: {v}" for k, v in matched_by.items() if v) or "DOI / PMID / NCT / Title+Year"
    n_not_scr = screening_info.get("not_screened", max(0, uniq_cnt - n_scr))
    gate_rej = screening_info.get("gate_rejected", 0)
    agree_rate = screening_info.get("reviewer_agreement_rate")
    agree_str = f"{agree_rate * 100:.1f}%" if agree_rate is not None else "N/A"
    n_ext_att = extraction_info.get("attempted", len(extracted_studies))
    n_ext_skip = extraction_info.get("not_attempted", max(0, n_inc_scr - n_ext_att))
    n_unpooled = max(0, len(extracted_studies) - k_pooled)

    prisma_rows += [
        [
            Paragraph("<b>1. Identification</b>", st_cell),
            Paragraph("<b>Total Records Identified</b>", st_cell),
            Paragraph(f"<b>{tot_id}</b>", st_cell),
            Paragraph("Combined citations retrieved across all active connectors", st_cell),
        ],
        [
            Paragraph("2. Deduplication", st_cell),
            Paragraph("Duplicate Records Removed", st_cell),
            Paragraph(f"-{dups_rem}", st_cell),
            Paragraph(f"5-tier deterministic match ({escape(match_str)})", st_cell),
        ],
        [
            Paragraph("<b>2. Deduplication</b>", st_cell),
            Paragraph("<b>Unique Records After Deduplication</b>", st_cell),
            Paragraph(f"<b>{uniq_cnt}</b>", st_cell),
            Paragraph(f"{tot_id} identified - {dups_rem} duplicates = {uniq_cnt} unique records", st_cell),
        ],
    ]
    if n_not_scr > 0:
        prisma_rows.append([
            Paragraph("3. Screening", st_cell),
            Paragraph("Unscreened (Beyond Screening Cap)", st_cell),
            Paragraph(f"-{n_not_scr}", st_cell),
            Paragraph(f"Screening cap configured at {n_scr} records", st_cell),
        ])
    prisma_rows += [
        [
            Paragraph("<b>3. Screening</b>", st_cell),
            Paragraph("<b>Records Screened (Title &amp; Abstract)</b>", st_cell),
            Paragraph(f"<b>{n_scr}</b>", st_cell),
            Paragraph(f"Independent dual MedGemma reviewers (Inter-reviewer agreement: {agree_str})", st_cell),
        ],
        [
            Paragraph("3. Screening", st_cell),
            Paragraph("Records Excluded at Title/Abstract Screening", st_cell),
            Paragraph(f"-{n_exc_scr}", st_cell),
            Paragraph(f"{gate_rej} by deterministic PICO gate + {max(0, n_exc_scr - gate_rej)} by dual reviewers (Table 2)", st_cell),
        ],
        [
            Paragraph("<b>3. Screening</b>", st_cell),
            Paragraph("<b>Studies Approved at Screening</b>", st_cell),
            Paragraph(f"<b>{n_inc_scr}</b>", st_cell),
            Paragraph(f"{n_scr} screened - {n_exc_scr} excluded = {n_inc_scr} eligible studies", st_cell),
        ],
    ]
    if n_ext_skip > 0:
        prisma_rows.append([
            Paragraph("4. Eligibility / Extraction", st_cell),
            Paragraph("Skipped Due to Extraction Cap", st_cell),
            Paragraph(f"-{n_ext_skip}", st_cell),
            Paragraph(f"Extraction cap ({n_ext_att}) reached (listed in Table 3)", st_cell),
        ])
    prisma_rows.append([
        Paragraph("<b>4. Eligibility / Extraction</b>", st_cell),
        Paragraph("<b>Studies Extracted &amp; Assessed for RoB 2</b>", st_cell),
        Paragraph(f"<b>{n_ext_att}</b>", st_cell),
        Paragraph("Structured arm-level extraction + 5-domain Cochrane RoB 2.0", st_cell),
    ])
    if n_unpooled > 0:
        prisma_rows.append([
            Paragraph("5. Inclusion", st_cell),
            Paragraph("Included in Narrative Synthesis Only (Unpooled)", st_cell),
            Paragraph(f"-{n_unpooled}", st_cell),
            Paragraph("Missing two-arm comparative counts in abstract (listed in Table 3)", st_cell),
        ])
    prisma_rows.append([
        Paragraph("<b>5. Inclusion</b>", st_cell),
        Paragraph("<b>Studies Included in Quantitative Meta-Analysis</b>", st_cell),
        Paragraph(f"<b>{k_pooled}</b>", st_cell),
        Paragraph(f"{meta.get('total_participants') or 0} total participants analyzed quantitatively", st_cell),
    ])

    t_prisma = Table(prisma_rows, colWidths=[34 * mm, 56 * mm, 22 * mm, usable_w - 112 * mm], repeatRows=1)
    t_prisma.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), bg_header),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
            ("GRID", (0, 0), (-1, -1), 0.4, border_col),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ])
    )
    story.append(t_prisma)
    story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # SECTION 3: TABLE 1 - CHARACTERISTICS OF INCLUDED STUDIES
    # ------------------------------------------------------------------
    story.append(Paragraph("3. Table 1: Baseline Characteristics &amp; Extracted Evidence of Included Studies", st_h1))
    story.append(
        Paragraph(
            "Every study that passed screening and underwent structured extraction is documented below with its "
            "identifier, source database, study design, arm-level sample sizes and event rates, effect estimate, "
            "and overall Cochrane RoB 2.0 judgement:",
            st_body,
        )
    )

    t1_rows = [
        [
            Paragraph("Ref / Study ID", st_cell_hdr),
            Paragraph("Author (Year) &amp; Study Title", st_cell_hdr),
            Paragraph("Source &amp; Design", st_cell_hdr),
            Paragraph("Intervention Arm", st_cell_hdr),
            Paragraph("Comparator Arm", st_cell_hdr),
            Paragraph("Effect [95% CI] &amp; Wt", st_cell_hdr),
            Paragraph("RoB 2 &amp; Synthesis Status", st_cell_hdr),
        ]
    ]

    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        inc_meta = inc_by_id.get(sid, {})
        url = _infer_url(sid, str(ext.get("verification_url") or inc_meta.get("url") or ""))
        label = str(ext.get("study_label") or inc_meta.get("citation") or sid)
        title = str(ext.get("title") or inc_meta.get("title") or "(Title not stated)")
        source_db = str(ext.get("source_db") or inc_meta.get("source") or "Database")
        design = str(ext.get("design") or "Clinical Study")

        ia = ext.get("intervention_arm") or {}
        ca = ext.get("control_arm") or {}

        def _fmt_arm_pdf(arm: dict[str, Any]) -> str:
            lbl = _clean(arm.get("label") or "Arm", 35)
            n_tot = arm.get("n_total")
            n_ev = arm.get("n_events")
            mean_v = arm.get("mean")
            sd_v = arm.get("sd")
            if n_ev is not None and n_tot is not None:
                pct = f" ({int(n_ev) / int(n_tot) * 100:.1f}%)" if int(n_tot) > 0 else ""
                return f"<b>{lbl}:</b> {n_ev}/{n_tot}{pct}"
            if mean_v is not None and sd_v is not None and n_tot is not None:
                return f"<b>{lbl}:</b> {mean_v}&plusmn;{sd_v} (N={n_tot})"
            if n_tot is not None:
                return f"<b>{lbl}:</b> N={n_tot} (events NR)"
            return f"<b>{lbl}:</b> NR"

        ps = pooled_by_key.get(sid) or pooled_by_key.get(label)
        if ps:
            eff_v = ps.get("effect_transformed", ps.get("effect", 0.0))
            cil_v = ps.get("ci_low_transformed", ps.get("ci_low", 0.0))
            cih_v = ps.get("ci_high_transformed", ps.get("ci_high", 0.0))
            wt_v = ps.get("weight_random_pct", 0.0)
            eff_cell = f"<b>{eff_v:.2f}</b> [{cil_v:.2f}, {cih_v:.2f}]<br/>Wt: {wt_v:.1f}%"
            status_str = "Pooled"
        else:
            eff_cell = "<i>Narrative synthesis</i>"
            status_str = "Narrative (NR in both arms)"

        rob_ov = _clean(ext.get("rob_overall") or "Some concerns", 30)
        id_html = (
            f'<b>[{idx}]</b> <a href="{escape(url)}" color="#1d4ed8"><u>{_clean(sid, 28)}</u></a>'
            if url
            else f"<b>[{idx}]</b> {_clean(sid, 28)}"
        )
        t1_rows.append([
            Paragraph(id_html, st_cell),
            Paragraph(f"<b>{_clean(label, 50)}</b><br/>{_clean(title, 140)}", st_cell),
            Paragraph(f"<b>{_clean(source_db, 25)}</b><br/>{_clean(design, 40)}", st_cell),
            Paragraph(_fmt_arm_pdf(ia), st_cell),
            Paragraph(_fmt_arm_pdf(ca), st_cell),
            Paragraph(eff_cell, st_cell),
            Paragraph(f"<b>{rob_ov}</b><br/>{status_str}", st_cell),
        ])

    if len(t1_rows) > 1:
        t1 = Table(
            t1_rows,
            colWidths=[24 * mm, 48 * mm, 21 * mm, 24 * mm, 24 * mm, 21 * mm, usable_w - 162 * mm],
            repeatRows=1,
        )
        t1.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ])
        )
        story.append(t1)
    story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # SECTION 4: METHODOLOGICAL QUALITY & COCHRANE ROB 2.0 MATRIX
    # ------------------------------------------------------------------
    story.append(Paragraph("4. Methodological Quality &amp; Cochrane Risk of Bias 2.0 (RoB 2) Assessment", st_h1))
    rob_rows = [
        [
            Paragraph("Study ID &amp; Citation", st_cell_hdr),
            Paragraph("D1: Randomization", st_cell_hdr),
            Paragraph("D2: Deviations", st_cell_hdr),
            Paragraph("D3: Missing Data", st_cell_hdr),
            Paragraph("D4: Measurement", st_cell_hdr),
            Paragraph("D5: Reporting", st_cell_hdr),
            Paragraph("Overall RoB 2", st_cell_hdr),
        ]
    ]
    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        label = str(ext.get("study_label") or sid)
        doms = ext.get("rob_domains") or []
        d_vals = [ _clean((doms[i].get("judgement") if i < len(doms) else "Some concerns"), 20) for i in range(5) ]
        ov = _clean(ext.get("rob_overall") or "Some concerns", 25)
        rob_rows.append([
            Paragraph(f"<b>[{idx}] {_clean(label, 42)}</b>", st_cell),
            Paragraph(d_vals[0], st_cell),
            Paragraph(d_vals[1], st_cell),
            Paragraph(d_vals[2], st_cell),
            Paragraph(d_vals[3], st_cell),
            Paragraph(d_vals[4], st_cell),
            Paragraph(f"<b>{ov}</b>", st_cell),
        ])
    if len(rob_rows) > 1:
        t_rob = Table(
            rob_rows,
            colWidths=[42 * mm, 23 * mm, 23 * mm, 23 * mm, 23 * mm, 23 * mm, usable_w - 157 * mm],
            repeatRows=1,
        )
        t_rob.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ])
        )
        story.append(t_rob)
        story.append(Spacer(1, 6))

    # Detailed per-study proof & RoB 2 rationales
    story.append(Paragraph("<b>Study-by-Study Dual-Reviewer Screening Proofs &amp; RoB 2 Verbatim Justifications:</b>", st_h2))
    for idx, ext in enumerate(extracted_studies, 1):
        sid = str(ext.get("study_id") or f"Study-{idx}")
        inc_meta = inc_by_id.get(sid, {})
        url = _infer_url(sid, str(ext.get("verification_url") or inc_meta.get("url") or ""))
        label = str(ext.get("study_label") or inc_meta.get("citation") or sid)
        title = str(ext.get("title") or inc_meta.get("title") or "")
        r1_p = _clean(inc_meta.get("reviewer_1_reason") or "Included at screening", 260)
        r2_p = _clean(inc_meta.get("reviewer_2_reason") or "Included at screening", 260)
        dec_p = _clean(inc_meta.get("decided_by") or "Dual-reviewer consensus", 220)
        dom_quotes = "; ".join(
            f"D{i+1} ({_clean(d.get('judgement'), 18)}): {_clean(d.get('justification'), 110)}"
            for i, d in enumerate(ext.get("rob_domains") or [])
        )
        link_str = f' (<a href="{escape(url)}" color="#1d4ed8"><u>{escape(url)}</u></a>)' if url else ""
        story.append(
            Paragraph(
                f"<b>[{idx}] {_clean(label, 55)} — {_clean(sid, 30)}</b>{link_str}: <i>{_clean(title, 180)}</i><br/>"
                f"&bull; <b>Reviewer 1 (Recall):</b> {r1_p}<br/>"
                f"&bull; <b>Reviewer 2 (Precision):</b> {r2_p}<br/>"
                f"&bull; <b>Consensus Rule:</b> {dec_p}<br/>"
                f"&bull; <b>RoB 2 Domain Evidence:</b> {dom_quotes or 'Assessed from abstract.'}",
                st_body,
            )
        )

    # ------------------------------------------------------------------
    # SECTION 5: QUANTITATIVE META-ANALYSIS, PLOTS & SENSITIVITY
    # ------------------------------------------------------------------
    story.append(Paragraph("5. Quantitative Meta-Analysis, Estimator Sensitivity &amp; Visual Figures", st_h1))
    if meta.get("ok"):
        models_dict = meta.get("models") or {}
        if models_dict:
            m_rows = [
                [
                    Paragraph("Statistical Pooling Model", st_cell_hdr),
                    Paragraph("&tau;<super>2</super> Estimator", st_cell_hdr),
                    Paragraph("Pooled Effect", st_cell_hdr),
                    Paragraph("95% Confidence Interval", st_cell_hdr),
                    Paragraph("p-value", st_cell_hdr),
                    Paragraph("Studies (k)", st_cell_hdr),
                ]
            ]
            for m_key, m_val in models_dict.items():
                est_v = m_val.get("estimate_transformed")
                cil_v = m_val.get("ci_low_transformed")
                cih_v = m_val.get("ci_high_transformed")
                pv = m_val.get("p_value")
                m_rows.append([
                    Paragraph(f"<b>{escape(str(m_key))}</b>", st_cell),
                    Paragraph(escape(str(m_val.get("tau2_method") or "Fixed")), st_cell),
                    Paragraph(f"<b>{est_v:.3f}</b>" if est_v is not None else "N/A", st_cell),
                    Paragraph(f"[{cil_v:.3f}, {cih_v:.3f}]" if (cil_v is not None and cih_v is not None) else "N/A", st_cell),
                    Paragraph(f"{pv:.4g}" if pv is not None else "N/A", st_cell),
                    Paragraph(str(m_val.get("k", 0)), st_cell),
                ])
            t_mod = Table(m_rows, colWidths=[48 * mm, 26 * mm, 28 * mm, 38 * mm, 22 * mm, usable_w - 162 * mm])
            t_mod.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                    ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ])
            )
            story.append(t_mod)
            story.append(Spacer(1, 6))

        loo = meta.get("leave_one_out") or []
        if loo:
            story.append(Paragraph("<b>Leave-One-Out Sensitivity Analysis:</b>", st_h2))
            loo_rows = [
                [
                    Paragraph("Omitted Study", st_cell_hdr),
                    Paragraph("Remaining (k)", st_cell_hdr),
                    Paragraph("Recalculated Estimate", st_cell_hdr),
                    Paragraph("95% CI", st_cell_hdr),
                    Paragraph("p-value", st_cell_hdr),
                    Paragraph("I<super>2</super> (%)", st_cell_hdr),
                ]
            ]
            for r in loo:
                loo_rows.append([
                    Paragraph(_clean(r.get("omitted_study"), 60), st_cell),
                    Paragraph(str(r.get("k_remaining", 0)), st_cell),
                    Paragraph(f"<b>{r.get('estimate_transformed', 0):.3f}</b>", st_cell),
                    Paragraph(f"[{r.get('ci_low_transformed', 0):.3f}, {r.get('ci_high_transformed', 0):.3f}]", st_cell),
                    Paragraph(f"{r.get('p_value', 1):.4g}", st_cell),
                    Paragraph(f"{r.get('I2', 0):.1f}%", st_cell),
                ])
            t_loo = Table(loo_rows, colWidths=[56 * mm, 24 * mm, 32 * mm, 34 * mm, 18 * mm, usable_w - 164 * mm])
            t_loo.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                    ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ])
            )
            story.append(t_loo)
            story.append(Spacer(1, 6))

        # Embed Forest and Funnel plots if present on disk
        for fig_idx, (p_key, p_title) in enumerate(
            [("forest", "Figure 1: Random-Effects Forest Plot"), ("funnel", "Figure 2: Publication Bias Funnel Plot")],
            1,
        ):
            p_file = plots.get(p_key) or str(out_path.parent / f"{p_key}.png")
            if p_file and Path(p_file).exists():
                story.append(Paragraph(f"<b>{p_title}</b>", st_h2))
                img = Image(p_file, width=usable_w * 0.92, height=usable_w * 0.50, kind="proportional")
                story.append(img)
                story.append(Spacer(1, 6))
    else:
        story.append(
            Paragraph(
                "Quantitative two-arm pooling was not executed because fewer than 2 included abstracts provided "
                "complete two-arm comparative event counts or means/SDs. Per Cochrane Handbook standards, "
                "unreported comparator figures are never imputed.",
                st_body,
            )
        )

    # Reproducible R verification script
    story.append(Paragraph("<b>Reproducible R Verification Script (meta / metafor):</b>", st_h2))
    r_code_escaped = escape(generate_r_script(result)).replace("\n", "<br/>")
    story.append(Paragraph(r_code_escaped, st_code))

    # ------------------------------------------------------------------
    # SECTION 6: GRADE SUMMARY OF FINDINGS
    # ------------------------------------------------------------------
    if grade:
        story.append(Paragraph("6. GRADE Certainty of Evidence &amp; Summary of Findings Profile", st_h1))
        g_rows = [
            [
                Paragraph("GRADE Domain", st_cell_hdr),
                Paragraph("Domain Judgement", st_cell_hdr),
                Paragraph("Downgrade Levels", st_cell_hdr),
                Paragraph("Methodological Justification", st_cell_hdr),
            ]
        ]
        for dom in ("risk_of_bias", "inconsistency", "indirectness", "imprecision", "publication_bias"):
            d_obj = grade.get(dom) or {}
            g_rows.append([
                Paragraph(f"<b>{escape(dom.replace('_', ' ').title())}</b>", st_cell),
                Paragraph(_clean(d_obj.get("judgement", "Not serious"), 30), st_cell),
                Paragraph(f"-{d_obj.get('downgrade_levels', 0)}", st_cell),
                Paragraph(_clean(d_obj.get("rationale", ""), 280), st_cell),
            ])
        g_rows.append([
            Paragraph("<b>FINAL GRADE CERTAINTY</b>", st_cell),
            Paragraph(f"<b>{_clean(grade.get('final_rating', 'Not rated'), 30)}</b>", st_cell),
            Paragraph(f"Start: {_clean(grade.get('starting_rating', 'High'), 20)}", st_cell),
            Paragraph(_clean(grade.get("summary", ""), 300), st_cell),
        ])
        t_grade = Table(g_rows, colWidths=[36 * mm, 28 * mm, 24 * mm, usable_w - 88 * mm])
        t_grade.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ])
        )
        story.append(t_grade)
        story.append(Spacer(1, 8))

    # ------------------------------------------------------------------
    # SECTION 7: AUDIT APPENDIX - EXCLUDED, UNPOOLED & DUPLICATE RECORDS
    # ------------------------------------------------------------------
    story.append(Paragraph("7. Transparency Audit Appendix: Excluded, Unpooled &amp; Duplicate Records", st_h1))
    story.append(Paragraph(f"<b>Table 2: Articles Excluded at Title/Abstract Screening (n = {len(exc_records)})</b>", st_h2))
    if exc_records:
        ex_rows = [
            [
                Paragraph("# / Article ID", st_cell_hdr),
                Paragraph("Title", st_cell_hdr),
                Paragraph("PRISMA Category", st_cell_hdr),
                Paragraph("Decision Source", st_cell_hdr),
                Paragraph("Documented Exclusion Reason / Proof", st_cell_hdr),
            ]
        ]
        for i, ex in enumerate(exc_records, 1):
            ex_id = str(ex.get("id") or f"Ex-{i}")
            ex_url = _infer_url(ex_id, str(ex.get("url") or ""))
            id_link = (
                f'<b>{i}.</b> <a href="{escape(ex_url)}" color="#1d4ed8"><u>{_clean(ex_id, 26)}</u></a>'
                if ex_url
                else f"<b>{i}.</b> {_clean(ex_id, 26)}"
            )
            ex_rows.append([
                Paragraph(id_link, st_cell),
                Paragraph(_clean(ex.get("title") or "(No title)", 130), st_cell),
                Paragraph(f"<b>{_clean(ex.get('category') or 'Excluded', 30)}</b>", st_cell),
                Paragraph(_clean(ex.get("decided_by") or "Screening", 45), st_cell),
                Paragraph(_clean(ex.get("reason") or ex.get("reviewer_2_reason") or "", 240), st_cell),
            ])
        t_ex = Table(ex_rows, colWidths=[28 * mm, 46 * mm, 26 * mm, 28 * mm, usable_w - 128 * mm], repeatRows=1)
        t_ex.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(t_ex)
        story.append(Spacer(1, 6))

    # Table 3: Approved at screening but not pooled
    skipped_cap = extraction_info.get("skipped_due_to_cap") or []
    if not skipped_cap and len(inc_records) > len(extracted_studies):
        for r in inc_records:
            rid = str(r.get("id") or "")
            if rid and rid not in ext_by_id:
                skipped_cap.append({
                    "id": rid,
                    "title": r.get("title") or "",
                    "url": _infer_url(rid, str(r.get("url") or "")),
                    "reason": f"Passed dual-reviewer screening; skipped at Phase 6 due to max_studies_to_extract={len(extracted_studies)} cap.",
                })
    if meta_excluded or skipped_cap:
        story.append(Paragraph("<b>Table 3: Studies Approved at Screening but Excluded from Quantitative Pooling</b>", st_h2))
        up_rows = [
            [
                Paragraph("# / Study ID", st_cell_hdr),
                Paragraph("Study Title", st_cell_hdr),
                Paragraph("Pipeline Stage", st_cell_hdr),
                Paragraph("Exact Exclusion / Non-Pooling Rationale", st_cell_hdr),
            ]
        ]
        u_idx = 1
        for ex_st in meta_excluded:
            lbl = str(ex_st.get("label") or "")
            matched_ext = next(
                (e for e in extracted_studies if str(e.get("study_label")) == lbl or str(e.get("study_id")) in lbl),
                None,
            )
            sid = str((matched_ext.get("study_id") if matched_ext else None) or lbl)
            raw_url = (matched_ext.get("verification_url") if matched_ext else None) or inc_by_id.get(sid, {}).get("url") or ""
            url = _infer_url(sid, str(raw_url))
            title = str((matched_ext.get("title") if matched_ext else None) or inc_by_id.get(sid, {}).get("title") or lbl)
            id_link = f'<b>{u_idx}.</b> <a href="{escape(url)}" color="#1d4ed8"><u>{_clean(sid, 28)}</u></a>' if url else f"<b>{u_idx}.</b> {_clean(sid, 28)}"
            up_rows.append([
                Paragraph(id_link, st_cell),
                Paragraph(_clean(title, 140), st_cell),
                Paragraph("Phase 7 (Pooling)", st_cell),
                Paragraph(_clean(f"{ex_st.get('reason_code', 'MISSING_DATA')}: {ex_st.get('reason', '')}", 220), st_cell),
            ])
            u_idx += 1
        for sk in skipped_cap:
            sid = str(sk.get("id") or "")
            url = _infer_url(sid, str(sk.get("url") or ""))
            id_link = f'<b>{u_idx}.</b> <a href="{escape(url)}" color="#1d4ed8"><u>{_clean(sid, 28)}</u></a>' if url else f"<b>{u_idx}.</b> {_clean(sid, 28)}"
            up_rows.append([
                Paragraph(id_link, st_cell),
                Paragraph(_clean(sk.get("title") or "", 140), st_cell),
                Paragraph("Phase 6 (Extraction Cap)", st_cell),
                Paragraph(_clean(sk.get("reason") or "", 220), st_cell),
            ])
            u_idx += 1
        t_up = Table(up_rows, colWidths=[30 * mm, 56 * mm, 32 * mm, usable_w - 118 * mm], repeatRows=1)
        t_up.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(t_up)
        story.append(Spacer(1, 6))

    # Table 4: Deduplication audit log
    rem_dups = dedupe_rep.get("removed_duplicates") or []
    if rem_dups:
        story.append(Paragraph(f"<b>Table 4: Deduplication Audit Log — Removed Duplicate Records (n = {len(rem_dups)})</b>", st_h2))
        dup_rows = [
            [
                Paragraph("# / Duplicate ID", st_cell_hdr),
                Paragraph("Duplicate Source", st_cell_hdr),
                Paragraph("Merged Into Primary ID", st_cell_hdr),
                Paragraph("Matched On", st_cell_hdr),
                Paragraph("Article Title", st_cell_hdr),
            ]
        ]
        for i, d in enumerate(rem_dups[:40], 1):
            dup_id = str(d.get("duplicate_id") or "")
            dup_url = _infer_url(dup_id, str(d.get("url") or ""))
            id_link = f'<b>{i}.</b> <a href="{escape(dup_url)}" color="#1d4ed8"><u>{_clean(dup_id, 26)}</u></a>' if dup_url else f"<b>{i}.</b> {_clean(dup_id, 26)}"
            dup_rows.append([
                Paragraph(id_link, st_cell),
                Paragraph(_clean(d.get("duplicate_source"), 25), st_cell),
                Paragraph(_clean(d.get("merged_into_id"), 28), st_cell),
                Paragraph(_clean(d.get("matched_on"), 18), st_cell),
                Paragraph(_clean(d.get("title"), 130), st_cell),
            ])
        t_dup = Table(dup_rows, colWidths=[32 * mm, 24 * mm, 32 * mm, 20 * mm, usable_w - 108 * mm], repeatRows=1)
        t_dup.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), bg_header),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, bg_soft]),
                ("GRID", (0, 0), (-1, -1), 0.4, border_col),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        story.append(t_dup)

    doc.build(story, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)
    return str(out_path)
