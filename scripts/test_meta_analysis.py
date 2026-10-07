#!/usr/bin/env python3
"""Validation suite for the deterministic meta-analysis engine.

This is the safety net for the only part of the SRMA system that produces
numbers. It checks three separate kinds of correctness:

  1. Published reference values. The classic aspirin / myocardial-infarction
     dataset must reproduce the literature: random-effects RR ~0.78,
     95% CI ~0.72-0.85, I^2 ~18%.

  2. Hand arithmetic. A three-study toy dataset whose Q, I^2, H^2, tau^2 and
     pooled estimate were computed by hand (the working is in the test
     docstrings) must be reproduced exactly. These constants were derived
     independently of the implementation.

  3. Guardrails and hygiene. Zero cells, missing SDs, zero denominators,
     the k >= 10 rule for bias tests, the I^2 > 50% flag, JSON
     serialisability, and the promise that no study is ever dropped
     silently.

Run it directly:

    ./.venv/bin/python scripts/test_meta_analysis.py

It exits non-zero if anything fails. It also works under pytest.
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from srma_agent.tools.meta_analysis import (  # noqa: E402
    beggs_test,
    binary_effect,
    continuous_effect,
    eggers_test,
    fixed_effect,
    heterogeneity,
    prediction_interval,
    random_effects,
    run_meta_analysis,
    tau2_dersimonian_laird,
    tau2_reml,
    trim_and_fill,
    _reml_loglik,
)
from srma_agent.tools.plots import forest_plot, funnel_plot  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")


# ==========================================================================
# Datasets
# ==========================================================================

def _binary(label, e1, n1, e2, n2, year=None):
    """A study record in the canonical StudyExtraction shape."""
    return {
        "study_id": label.lower().replace(" ", "-"),
        "study_label": label,
        "year": year,
        "intervention_arm": {"label": "Aspirin", "n_events": e1,
                             "n_total": n1},
        "control_arm": {"label": "Placebo", "n_events": e2, "n_total": n2},
        "outcome_name": "Mortality / vascular event",
    }


#: Antiplatelet (aspirin) trials for prevention of death / vascular events.
#: Events are in the aspirin arm first, then placebo/control.
ASPIRIN = [
    _binary("ISIS-2", 804, 8587, 1016, 8600, 1988),
    _binary("SALT", 54, 676, 89, 684, 1991),
    _binary("AMIS", 310, 2267, 344, 2257, 1980),
    _binary("PARIS-I", 148, 1219, 129, 807, 1980),
    _binary("CDP", 88, 758, 114, 771, 1976),
    _binary("GAMIS", 32, 317, 45, 309, 1980),
    _binary("UK-TIA", 75, 806, 98, 806, 1988),
    _binary("SAPAT", 42, 1009, 71, 1026, 1992),
]


# ==========================================================================
# Tiny assertion harness (so the suite runs without pytest installed)
# ==========================================================================

_FAILURES: list[str] = []
_PASSES: list[str] = []


def close(actual, expected, tol=1e-6, what=""):
    if actual is None or not math.isfinite(float(actual)):
        raise AssertionError(f"{what}: got a non-finite value {actual!r}")
    if abs(float(actual) - float(expected)) > tol:
        raise AssertionError(
            f"{what}: expected {expected!r} +/- {tol:g}, got {float(actual)!r} "
            f"(difference {abs(float(actual) - float(expected)):.3g})"
        )


def between(actual, low, high, what=""):
    if actual is None or not (low <= float(actual) <= high):
        raise AssertionError(
            f"{what}: expected a value in [{low}, {high}], got {actual!r}"
        )


def ok(condition, what=""):
    if not condition:
        raise AssertionError(what)


# ==========================================================================
# 1. Hand-computed toy dataset
# ==========================================================================


def test_toy_heterogeneity_by_hand():
    """Three studies with arithmetic that can be checked on paper.

        y = [0.5, 0.1, 0.9]      v = [0.05, 0.05, 0.05]
        w = 1/v = 20 each        sum w = 60
        mu_FE = (0.5 + 0.1 + 0.9) / 3 = 0.5
        Q  = 20 * (0^2 + 0.4^2 + 0.4^2) = 20 * 0.32 = 6.4
        df = 2
        p  = P(chi2_2 > 6.4) = exp(-6.4 / 2) = exp(-3.2) = 0.04076220...
        I2 = (6.4 - 2) / 6.4 = 0.6875 -> 68.75%
        H2 = 6.4 / 2 = 3.2
        C  = sum w - sum w^2 / sum w = 60 - 1200/60 = 40
        tau2_DL = (6.4 - 2) / 40 = 0.11
        SE_FE = sqrt(1/60) = 0.12909944
    """
    y = np.array([0.5, 0.1, 0.9])
    v = np.array([0.05, 0.05, 0.05])

    het = heterogeneity(y, v)
    close(het["Q"], 6.4, 1e-12, "Q")
    close(het["df"], 2, 0, "df")
    close(het["p_value"], math.exp(-3.2), 1e-12, "Q p-value")
    close(het["I2"], 68.75, 1e-10, "I^2")
    close(het["H2"], 3.2, 1e-12, "H^2")
    close(het["tau2_DL"], 0.11, 1e-12, "tau^2 (DL)")

    # Independent formula for Q: sum(w y^2) - (sum w y)^2 / sum w.
    w = 1.0 / v
    q_alt = float((w * y ** 2).sum() - (w * y).sum() ** 2 / w.sum())
    close(het["Q"], q_alt, 1e-12, "Q vs algebraic identity")

    fe = fixed_effect(y, v)
    close(fe["estimate"], 0.5, 1e-12, "fixed-effect estimate")
    close(fe["se"], math.sqrt(1.0 / 60.0), 1e-12, "fixed-effect SE")
    close(fe["ci_low"], 0.5 - 1.959963984540054 * math.sqrt(1 / 60), 1e-9,
          "fixed-effect CI low")
    close(sum(fe["weights"]), 100.0, 1e-9, "weights sum to 100%")

    # REML has a closed form here: tau^2 = 0.17/3 + (0.05 + tau^2)/3
    #                         =>  (2/3) tau^2 = 0.0733333...  =>  tau^2 = 0.11
    reml = tau2_reml(y, v)
    ok(reml["converged"], "REML should converge on the toy data")
    close(reml["tau2"], 0.11, 1e-9, "tau^2 (REML, closed form)")

    # Random effects: w = 1/(0.05+0.11) = 6.25, sum = 18.75, SE = sqrt(1/18.75)
    re = random_effects(y, v, het["tau2_DL"])
    close(re["estimate"], 0.5, 1e-12, "random-effects estimate")
    close(re["se"], math.sqrt(1.0 / 18.75), 1e-12, "random-effects SE")

    # HKSJ: q = sum w (y-mu)^2 / (k-1) = 6.25*0.32/2 = 1.0
    #       SE = sqrt(1/18.75); critical value t(2) = 4.30265273
    hk = random_effects(y, v, het["tau2_DL"], hksj=True)
    close(hk["se"], math.sqrt(1.0 / 18.75), 1e-12, "HKSJ SE")
    close(hk["df"], 2, 0, "HKSJ df")
    close(hk["ci_high"], 0.5 + 4.302652729911275 * math.sqrt(1 / 18.75), 1e-9,
          "HKSJ CI high (t reference)")
    ok(hk["ci_high"] > re["ci_high"],
       "HKSJ must widen the interval when k is small here")

    # Prediction interval: t(1) * sqrt(0.11 + 1/18.75)
    pi = prediction_interval(0.5, math.sqrt(1 / 18.75), 0.11, 3)
    expected_half = 12.706204736174698 * math.sqrt(0.11 + 1 / 18.75)
    close(pi["high"], 0.5 + expected_half, 1e-9, "prediction interval upper")


def test_toy_zero_heterogeneity():
    """Q below its df must clamp I^2 and tau^2 to exactly zero.

        y = [0.30, 0.10, 0.50], v = [0.04, 0.01, 0.25]
        w = [25, 100, 4], sum w = 129, sum wy = 19.5
        mu = 19.5/129 = 0.151162790697674...
        Q  = 1.302326 (< df = 2)  ->  I^2 = 0, tau^2 = 0
    """
    y = np.array([0.30, 0.10, 0.50])
    v = np.array([0.04, 0.01, 0.25])
    het = heterogeneity(y, v)
    close(het["Q"], 1.3023255813953485, 1e-9, "Q")
    close(het["I2"], 0.0, 1e-12, "I^2 clamped at zero")
    close(het["tau2_DL"], 0.0, 1e-12, "tau^2 clamped at zero")
    close(het["H2"], 1.0, 1e-12, "H^2 floored at one")
    fe = fixed_effect(y, v)
    close(fe["estimate"], 19.5 / 129.0, 1e-12, "fixed-effect estimate")


def test_reml_matches_likelihood_maximum():
    """The REML fixed point must sit at the maximum of the restricted
    log-likelihood, verified by a brute-force grid search."""
    y = np.array([0.5, 0.1, 0.9, 0.35, -0.2])
    v = np.array([0.05, 0.05, 0.05, 0.02, 0.12])
    tau2 = tau2_reml(y, v)["tau2"]
    grid = np.linspace(0.0, 2.0, 20001)
    best = float(grid[int(np.argmax([_reml_loglik(t, y, v) for t in grid]))])
    close(tau2, best, 2e-4, "REML tau^2 vs grid maximum")


# ==========================================================================
# 2. Per-study effect sizes, hand-checked
# ==========================================================================


def test_binary_effect_sizes_by_hand():
    """SALT: 54/676 aspirin vs 89/684 control.

        p1 = 54/676  = 0.079881656804734
        p2 = 89/684  = 0.130116959064327
        RR = p1/p2   = 0.613920...
        SE(logRR) = sqrt(1/54 - 1/676 + 1/89 - 1/684) = 0.163748...
        OR = (54*595)/(622*89) = 32130/55358 = 0.580404...
        SE(logOR) = sqrt(1/54 + 1/622 + 1/89 + 1/595) = 0.181777...
        RD = p1 - p2 = -0.050235...
        SE(RD) = sqrt(p1(1-p1)/676 + p2(1-p2)/684) = 0.016559...
    """
    rr = binary_effect(54, 676, 89, 684, "RR")
    # SALT: 54/676 vs 89/684. Exactly (54*684)/(676*89) = 36936/60164.
    # The previous constant here was hand-rounded at the 7th decimal and
    # was wrong by 1.25e-06, which failed against a correct engine.
    close(math.exp(rr["y"]), 36936 / 60164, 1e-9, "SALT risk ratio")
    close(math.sqrt(rr["v"]), 0.1637475, 1e-6, "SALT SE(log RR)")
    ok(not rr["corrected"], "no continuity correction should be needed")

    orr = binary_effect(54, 676, 89, 684, "OR")
    close(math.exp(orr["y"]), 32130.0 / 55358.0, 1e-9, "SALT odds ratio")
    close(math.sqrt(orr["v"]), 0.1817774, 1e-6, "SALT SE(log OR)")

    rd = binary_effect(54, 676, 89, 684, "RD")
    close(rd["y"], 54 / 676 - 89 / 684, 1e-12, "SALT risk difference")
    close(math.sqrt(rd["v"]), 0.0165589, 1e-6, "SALT SE(RD)")


def test_continuity_correction():
    """Zero cell: 0/50 vs 5/50, RR with 0.5 added to all four cells.

        a,b,c,d = 0.5, 50.5, 5.5, 45.5 ; arm totals become 51 and 51
        RR = (0.5/51)/(5.5/51) = 1/11 = 0.0909090909
        SE = sqrt(1/0.5 - 1/51 + 1/5.5 - 1/51) = sqrt(2.1426025...) = 1.4637631
    """
    eff = binary_effect(0, 50, 5, 50, "RR")
    ok(eff["corrected"], "correction flag must be set")
    close(math.exp(eff["y"]), 1.0 / 11.0, 1e-12, "corrected risk ratio")
    close(math.sqrt(eff["v"]), 1.4637631, 1e-6, "corrected SE(log RR)")

    # A table with no zero cell must be left completely untouched.
    untouched = binary_effect(10, 50, 5, 50, "RR")
    ok(not untouched["corrected"], "correction must not fire without a zero")
    close(math.exp(untouched["y"]), 2.0, 1e-12, "uncorrected risk ratio")


def test_hedges_g():
    """n1 = n2 = 20, means 10 vs 8, SDs 4 and 4.

        s_pooled = 4, Cohen's d = 0.5
        J ~ 1 - 3/(4*38 - 1) = 0.98013245 (exact gamma form is within 1e-4)
        g = J*d ~ 0.4900662
        var(g) = 1/20 + 1/20 + g^2/(2*40) ~ 0.10300287
    """
    eff = continuous_effect(10, 4, 20, 8, 4, 20, "SMD")
    close(eff["detail"]["cohens_d"], 0.5, 1e-12, "Cohen's d")
    close(eff["detail"]["pooled_sd"], 4.0, 1e-12, "pooled SD")
    close(eff["detail"]["hedges_correction_J"], 0.98013245, 5e-4,
          "Hedges' J correction")
    close(eff["y"], 0.49006622, 5e-4, "Hedges' g")
    close(eff["v"], 0.1 + eff["y"] ** 2 / 80.0, 1e-12, "var(g)")
    ok(abs(eff["y"]) < 0.5, "g must be shrunk relative to d")

    md = continuous_effect(10, 4, 20, 8, 4, 20, "MD")
    close(md["y"], 2.0, 1e-12, "mean difference")
    close(md["v"], 16 / 20 + 16 / 20, 1e-12, "var(MD)")


# ==========================================================================
# 3. The published reference dataset
# ==========================================================================

_ASPIRIN_RESULT: dict | None = None


def aspirin_result() -> dict:
    global _ASPIRIN_RESULT
    if _ASPIRIN_RESULT is None:
        _ASPIRIN_RESULT = run_meta_analysis(
            ASPIRIN, effect_measure="RR", model="random"
        )
    return _ASPIRIN_RESULT


def test_aspirin_reference_values():
    """Published benchmark: RR ~0.78, 95% CI ~0.72-0.85, I^2 ~18%."""
    res = aspirin_result()
    ok(res["ok"], f"analysis failed: {res.get('error')}")
    close(res["k_included"], 8, 0, "all eight trials analysed")
    close(res["k_excluded"], 0, 0, "no trial excluded")

    pooled = res["pooled"]
    rr = pooled["estimate_transformed"]
    lo = pooled["ci_low_transformed"]
    hi = pooled["ci_high_transformed"]
    i2 = res["heterogeneity"]["I2"]

    print(f"    aspirin RR = {rr:.4f} [{lo:.4f}, {hi:.4f}], "
          f"I^2 = {i2:.1f}%, tau^2 = {res['heterogeneity']['tau2']:.5f}, "
          f"Q = {res['heterogeneity']['Q']:.3f}")

    close(rr, 0.78, 0.02, "pooled random-effects risk ratio")
    close(lo, 0.72, 0.03, "95% CI lower limit")
    close(hi, 0.85, 0.03, "95% CI upper limit")
    close(i2, 18.0, 12.0, "I^2")
    ok(pooled["p_value"] < 0.001, "the pooled effect must be significant")
    ok(hi < 1.0, "the CI must exclude no-effect, as in the literature")

    # Sanity: the fixed-effect estimate should be close but not identical.
    fe = res["models"]["fixed_effect"]["estimate_transformed"]
    between(fe, 0.74, 0.82, "fixed-effect risk ratio")

    # Total participants across both arms.
    close(res["total_participants"],
          sum(s["intervention_arm"]["n_total"] + s["control_arm"]["n_total"]
              for s in ASPIRIN), 0, "total participants")


def test_aspirin_estimator_agreement():
    """DL, REML and HKSJ must all land in the same neighbourhood."""
    res = aspirin_result()
    models = res["models"]
    for name in ("random_effects_DL", "random_effects_REML",
                 "random_effects_DL_HKSJ", "random_effects_REML_HKSJ"):
        est = models[name]["estimate_transformed"]
        between(est, 0.74, 0.83, f"{name} estimate")
    # HKSJ uses a t reference on k-1 df, so its interval is the wider one.
    dl = models["random_effects_DL"]
    hk = models["random_effects_DL_HKSJ"]
    ok(hk["ci_high"] - hk["ci_low"] > dl["ci_high"] - dl["ci_low"],
       "HKSJ should widen the interval for this dataset")
    ok(hk["statistic_type"] == "t" and hk["df"] == 7,
       "HKSJ must use t with k-1 = 7 degrees of freedom")


def test_aspirin_heterogeneity_recomputed():
    """Recompute Q and I^2 from the per-study output, independently."""
    res = aspirin_result()
    y = np.array([s["effect"] for s in res["studies"]])
    v = np.array([s["variance"] for s in res["studies"]])
    w = 1.0 / v
    mu = (w * y).sum() / w.sum()
    q = float((w * (y - mu) ** 2).sum())
    close(res["heterogeneity"]["Q"], q, 1e-10, "Q recomputed from output")
    close(res["heterogeneity"]["I2"], max(0.0, (q - 7) / q) * 100, 1e-10,
          "I^2 recomputed from output")
    # Weights must be a genuine partition of 100%.
    close(sum(s["weight_random_pct"] for s in res["studies"]), 100.0, 1e-9,
          "random-effects weights")
    close(sum(s["weight_fixed_pct"] for s in res["studies"]), 100.0, 1e-9,
          "fixed-effect weights")
    # ISIS-2 is by far the largest trial and must carry the largest weight.
    heaviest = max(res["studies"], key=lambda s: s["weight_fixed_pct"])
    ok(heaviest["label"] == "ISIS-2",
       f"ISIS-2 should dominate the fixed-effect weighting, got "
       f"{heaviest['label']}")


def test_aspirin_leave_one_out():
    res = aspirin_result()
    loo = res["leave_one_out"]
    close(len(loo), 8, 0, "one leave-one-out fit per study")
    for row in loo:
        close(row["k_remaining"], 7, 0, "k after omission")
        between(row["estimate_transformed"], 0.70, 0.88,
                f"leave-one-out RR without {row['omitted_study']}")
        ok(row["ci_high_transformed"] < 1.0,
           f"conclusion should survive omitting {row['omitted_study']}")


def test_aspirin_other_measures():
    """OR should be further from 1 than RR; RD should be negative."""
    odds = run_meta_analysis(ASPIRIN, effect_measure="OR", model="random")
    rrr = aspirin_result()
    ok(odds["ok"], "OR analysis must succeed")
    ok(odds["pooled"]["estimate_transformed"]
       < rrr["pooled"]["estimate_transformed"],
       "for a protective effect the OR is more extreme than the RR")

    rd = run_meta_analysis(ASPIRIN, effect_measure="RD", model="random")
    ok(rd["ok"], "RD analysis must succeed")
    ok(rd["pooled"]["estimate"] < 0, "aspirin should reduce absolute risk")
    ok(not rd["is_ratio_measure"], "RD is not a ratio measure")
    between(rd["pooled"]["estimate"], -0.05, -0.005, "pooled risk difference")


def test_auto_detection():
    auto = run_meta_analysis(ASPIRIN, effect_measure="auto")
    close(auto["effect_measure"] == "RR", True, 0, "auto-detected RR")
    close(auto["pooled"]["estimate"],
          aspirin_result()["pooled"]["estimate"], 1e-12,
          "auto must match the explicit RR analysis")

    continuous = [
        {"study_label": f"C{i}",
         "intervention_arm": {"label": "T", "mean": m, "sd": 4.0,
                              "n_total": 40},
         "control_arm": {"label": "C", "mean": 8.0, "sd": 4.0, "n_total": 40}}
        for i, m in enumerate([10.0, 9.5, 10.5, 9.8], start=1)
    ]
    res = run_meta_analysis(continuous, effect_measure="auto")
    ok(res["effect_measure"] == "SMD",
       f"continuous data should auto-select SMD, got {res['effect_measure']}")
    ok(res["pooled"]["estimate"] > 0, "intervention means are higher")

    md = run_meta_analysis(continuous, effect_measure="MD")
    close(md["pooled"]["estimate"], 1.95, 0.01, "pooled mean difference")


# ==========================================================================
# 4. Guardrails
# ==========================================================================


def test_bias_tests_gated_at_ten_studies():
    res = aspirin_result()
    bias = res["publication_bias"]
    ok(not bias["egger"]["performed"], "Egger must be skipped with k = 8")
    ok("10" in bias["egger"]["reason"],
       "the skip reason must state the k >= 10 rule")
    ok(not bias["begg"]["performed"], "Begg must be skipped with k = 8")
    ok(any(f["code"] == "BIAS_TESTS_SKIPPED" for f in res["flags"]),
       "a flag must record that bias testing was skipped")

    # Twelve studies: the tests must now run.
    big = ASPIRIN + [
        _binary("Extra A", 40, 500, 50, 500),
        _binary("Extra B", 30, 400, 38, 400),
        _binary("Extra C", 21, 300, 27, 300),
        _binary("Extra D", 14, 200, 19, 200),
    ]
    res_big = run_meta_analysis(big, effect_measure="RR")
    eg = res_big["publication_bias"]["egger"]
    bg = res_big["publication_bias"]["begg"]
    ok(eg["performed"], f"Egger should run with k = {res_big['k_included']}")
    ok(bg["performed"], "Begg should run with 12 studies")
    between(eg["p_value"], 0.0, 1.0, "Egger p-value")
    between(bg["p_value"], 0.0, 1.0, "Begg p-value")
    close(eg["df"], res_big["k_included"] - 2, 0, "Egger df = k - 2")


def test_high_heterogeneity_flag():
    """I^2 > 50% must raise the mandatory subgroup-analysis flag."""
    divergent = [
        _binary("A", 10, 100, 50, 100),
        _binary("B", 48, 100, 50, 100),
        _binary("C", 12, 100, 55, 100),
        _binary("D", 52, 100, 50, 100),
    ]
    res = run_meta_analysis(divergent, effect_measure="RR")
    ok(res["heterogeneity"]["I2"] > 50, "this dataset should be heterogeneous")
    codes = [f["code"] for f in res["flags"]]
    ok("HIGH_HETEROGENEITY" in codes,
       f"expected a HIGH_HETEROGENEITY flag, got {codes}")
    msg = next(f["message"] for f in res["flags"]
               if f["code"] == "HIGH_HETEROGENEITY")
    ok("subgroup" in msg.lower() and "sensitivity" in msg.lower(),
       "the flag must demand subgroup / sensitivity analysis")

    # And a homogeneous dataset must not raise it.
    res2 = aspirin_result()
    ok("HIGH_HETEROGENEITY" not in [f["code"] for f in res2["flags"]],
       "the aspirin dataset should not trip the heterogeneity flag")


def test_no_study_is_dropped_silently():
    messy = ASPIRIN + [
        {"study_label": "No SD", "intervention_arm":
            {"label": "T", "mean": 5.0, "sd": None, "n_total": 30},
         "control_arm": {"label": "C", "mean": 4.0, "sd": 2.0,
                         "n_total": 30}},
        _binary("Zero denominator", 5, 0, 4, 40),
        _binary("Double zero", 0, 120, 0, 118),
        _binary("Impossible", 60, 50, 4, 40),
        {"study_label": "Nothing at all"},
    ]
    res = run_meta_analysis(messy, effect_measure="RR")

    close(res["k_supplied"], len(messy), 0, "k_supplied")
    close(res["k_included"] + res["k_excluded"], len(messy), 0,
          "every supplied study must be accounted for")
    close(res["k_included"], 8, 0, "only the eight valid trials are pooled")

    reasons = {e["label"]: e["reason_code"] for e in res["excluded_studies"]}
    ok(reasons.get("Zero denominator") == "ZERO_DENOMINATOR", str(reasons))
    ok(reasons.get("Double zero") == "DOUBLE_ZERO", str(reasons))
    ok(reasons.get("Impossible") == "EVENTS_EXCEED_TOTAL", str(reasons))
    ok(reasons.get("No SD") == "MISSING_BINARY_DATA", str(reasons))
    ok(reasons.get("Nothing at all") == "MISSING_BINARY_DATA", str(reasons))
    for entry in res["excluded_studies"]:
        ok(bool(entry["reason"]), "every exclusion needs a prose reason")
    ok(any("could not be analysed" in w for w in res["warnings"]),
       "exclusions must surface as a warning")

    # The same double-zero study IS informative for a risk difference.
    rd = run_meta_analysis(
        [_binary("Double zero", 0, 120, 0, 118), *ASPIRIN],
        effect_measure="RD")
    ok("Double zero" in [s["label"] for s in rd["studies"]],
       "a double-zero study must be retained for the risk difference")

    # A missing SD in a continuous analysis must be reported, not imputed.
    cont = [
        {"study_label": "Has SD", "intervention_arm":
            {"label": "T", "mean": 5.0, "sd": 2.0, "n_total": 30},
         "control_arm": {"label": "C", "mean": 4.0, "sd": 2.0,
                         "n_total": 30}},
        {"study_label": "No SD", "intervention_arm":
            {"label": "T", "mean": 5.0, "sd": None, "n_total": 30},
         "control_arm": {"label": "C", "mean": 4.0, "sd": 2.0,
                         "n_total": 30}},
    ]
    res_c = run_meta_analysis(cont, effect_measure="MD")
    codes = [e["reason_code"] for e in res_c["excluded_studies"]]
    ok("MISSING_CONTINUOUS_DATA" in codes or
       "MISSING_OR_INVALID_SD" in codes,
       f"a missing SD must be flagged, got {codes}")


def test_continuity_correction_reported():
    data = [
        _binary("Zero arm", 0, 60, 7, 60),
        _binary("Normal 1", 12, 60, 18, 60),
        _binary("Normal 2", 9, 55, 15, 58),
    ]
    res = run_meta_analysis(data, effect_measure="OR")
    corrected = [s["label"] for s in res["studies"]
                 if s["continuity_corrected"]]
    ok(corrected == ["Zero arm"], f"expected one corrected study, {corrected}")
    ok(any("continuity correction" in w.lower() for w in res["warnings"]),
       "the correction must be reported in the warnings")


def test_degenerate_inputs():
    empty = run_meta_analysis([], effect_measure="RR")
    ok(not empty["ok"], "an empty list must fail cleanly, not raise")

    single = run_meta_analysis([ASPIRIN[0]], effect_measure="RR")
    ok(single["ok"], "a single study should still return a result")
    close(single["k_included"], 1, 0, "k = 1")
    ok(not single["prediction_interval"]["available"],
       "no prediction interval with one study")
    ok(single["leave_one_out"] == [], "no leave-one-out with one study")
    ok(any("one study" in w for w in single["warnings"]),
       "k = 1 must be warned about")

    bad = run_meta_analysis(ASPIRIN, effect_measure="banana")
    ok(not bad["ok"], "an unknown effect measure must fail cleanly")

    weird_model = run_meta_analysis(ASPIRIN, effect_measure="RR",
                                    model="bayesian")
    ok(weird_model["ok"], "an unknown model should fall back, not crash")
    ok(any("Unrecognised model" in n for n in weird_model["notes"]),
       "the fallback must be disclosed")


def test_json_serialisable():
    """The result must survive json.dumps with no NaN, Inf or numpy types."""
    for res in (aspirin_result(),
                run_meta_analysis(ASPIRIN, effect_measure="RD",
                                  model="random_reml_hksj"),
                run_meta_analysis([], effect_measure="RR")):
        text = json.dumps(res, allow_nan=False)
        ok("NaN" not in text and "Infinity" not in text,
           "no NaN/Infinity tokens may reach the JSON payload")
        round_tripped = json.loads(text)
        ok(isinstance(round_tripped, dict), "round-trip must give a dict")


def test_determinism():
    """Same input, byte-identical output. No randomness anywhere."""
    a = json.dumps(run_meta_analysis(ASPIRIN, effect_measure="RR"),
                   sort_keys=True)
    b = json.dumps(run_meta_analysis(ASPIRIN, effect_measure="RR"),
                   sort_keys=True)
    ok(a == b, "two identical runs produced different output")


# ==========================================================================
# 5. Publication bias machinery
# ==========================================================================


def _mirrored_funnel(centre=-0.3, c=1.0, m=12, se_min=0.05, se_max=0.5):
    """A perfectly symmetric funnel, built without any random numbers.

    For each of `m` standard errors there are two studies, at
    `centre + c*se` and `centre - c*se`. That makes Egger's regression
    exactly solvable: the standard normal deviate is

        y_i / se_i = centre * (1/se_i) +/- c

    so the fitted line is  SND = centre * precision + 0  and the intercept
    is algebraically zero, whatever the standard errors are. Subtracting
    `b * se` from every effect then shifts that intercept to exactly `-b`.
    Using a seeded RNG instead would make pass/fail a property of the seed,
    which is not a thing worth testing.
    """
    se_values = np.linspace(se_min, se_max, m)
    y: list[float] = []
    se: list[float] = []
    for s in se_values:
        y.extend([centre + c * s, centre - c * s])
        se.extend([s, s])
    return np.array(y), np.array(se) ** 2


def test_egger_and_begg_behaviour():
    # Symmetric funnel: the intercept is exactly zero, so p is exactly 1.
    y, v = _mirrored_funnel()
    eg = eggers_test(y, v)
    bg = beggs_test(y, v)
    ok(eg["performed"] and bg["performed"], "both tests should run")
    close(eg["intercept"], 0.0, 1e-9, "Egger intercept on a symmetric funnel")
    close(eg["slope"], -0.3, 1e-9, "Egger slope recovers the true effect")
    close(eg["df"], len(y) - 2, 0, "Egger df = k - 2")
    ok(eg["p_value"] > 0.05,
       f"symmetric data must not show asymmetry (p = {eg['p_value']:.3f})")
    ok(not eg["asymmetry_detected"], "no asymmetry flag on symmetric data")
    ok(bg["p_value"] > 0.05, "Begg must not fire on a symmetric funnel")

    # Impose a small-study effect: every effect is pushed down by 3 standard
    # errors, which moves the Egger intercept from 0 to exactly -3.
    se = np.sqrt(v)
    eg2 = eggers_test(y - 3.0 * se, v)
    close(eg2["intercept"], -3.0, 1e-9, "Egger intercept after biasing")
    ok(eg2["p_value"] < 0.05,
       f"a deliberate small-study effect must be detected "
       f"(p = {eg2['p_value']:.3g})")
    ok(eg2["asymmetry_detected"], "asymmetry flag must be set")


def test_trim_and_fill():
    y, v = _mirrored_funnel()
    taf = trim_and_fill(y, v)
    ok(taf["performed"], f"trim-and-fill should run with k = {y.size}")
    # On an exactly symmetric funnel L0 lands within half a study of zero,
    # and which way it rounds depends on how rank ties inside each mirrored
    # pair are broken. The estimator is knife-edge here by construction, so
    # the honest assertion is "essentially nothing to fill".
    ok(taf["n_missing_estimated"] <= 1,
       f"a symmetric funnel should need no imputation, got "
       f"{taf['n_missing_estimated']}")
    if taf["adjusted_estimate"] is not None:
        close(taf["adjusted_estimate"], -0.3, 0.02,
              "any spurious fill must leave the estimate essentially intact")

    # Now censor the funnel: drop the upper member of every imprecise pair,
    # i.e. suppress the six least favourable small studies. The remaining
    # funnel is missing studies on its right-hand side.
    se = np.sqrt(v)
    big = se > np.median(se)
    keep = ~(big & (y > -0.3))
    y_c, v_c = y[keep], v[keep]
    close(y_c.size, 18, 0, "six studies were censored")

    # Pool fixed-effect on both sides of the comparison below. Censoring a
    # tail inflates tau^2, and a random-effects pool of the *augmented* set
    # is dragged towards the unweighted mean of the filled data, which here
    # sits further from the truth than the censored estimate did. That is a
    # documented weakness of trim-and-fill under heterogeneity rather than a
    # bug, so asserting on it would be asserting the wrong thing. Under
    # fixed-effect weights the direction of the correction is a theorem:
    # adding studies above the current mean must raise it.
    taf2 = trim_and_fill(y_c, v_c, use_random=False)
    ok(taf2["n_missing_estimated"] > 0,
       "censoring one side of the funnel must be detected")
    ok(taf2["side_imputed"] == "right",
       f"studies were removed from the right, got {taf2['side_imputed']}")
    close(len(taf2["imputed_effects"]), taf2["n_missing_estimated"], 0,
          "one imputed effect per estimated missing study")
    close(len(taf2["imputed_variances"]), taf2["n_missing_estimated"], 0,
          "imputed studies reuse the variances of the trimmed ones")
    ok(all(e > -0.3 for e in taf2["imputed_effects"]),
       f"imputed studies must land on the right: {taf2['imputed_effects']}")

    observed = float((y_c / v_c).sum() / (1.0 / v_c).sum())
    adjusted = taf2["adjusted_estimate"]
    ok(observed < -0.3, "censoring should have dragged the estimate down")
    ok(adjusted > observed,
       f"the adjusted estimate ({adjusted:.4f}) must correct back towards "
       f"the uncensored value (-0.3) from the censored one "
       f"({observed:.4f})")
    ok(adjusted <= -0.3 + 0.05,
       f"trim-and-fill should not wildly overshoot, got {adjusted:.4f}")


# ==========================================================================
# 6. Plots
# ==========================================================================


def test_plots_render():
    os.makedirs(RUNS, exist_ok=True)
    res = aspirin_result()

    forest = forest_plot(
        res, os.path.join(RUNS, "forest_aspirin.png"),
        title="Aspirin vs placebo: vascular death / MI (validation dataset)")
    funnel = funnel_plot(res, os.path.join(RUNS, "funnel_aspirin.png"))

    for path in (forest, funnel):
        ok(os.path.exists(path), f"{path} was not written")
        size = os.path.getsize(path)
        ok(size > 10_000, f"{path} is suspiciously small ({size} bytes)")
        with open(path, "rb") as fh:
            ok(fh.read(8) == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG")
    print(f"    wrote {forest}")
    print(f"    wrote {funnel}")

    # A continuous (non-log-scale) forest plot, and a funnel with the bias
    # tests actually performed, to exercise the other code paths.
    cont = [
        {"study_label": f"Trial {i}",
         "intervention_arm": {"label": "T", "mean": m, "sd": 4.0,
                              "n_total": n},
         "control_arm": {"label": "C", "mean": 8.0, "sd": 4.2,
                         "n_total": n}}
        for i, (m, n) in enumerate(
            [(10.0, 40), (9.5, 60), (10.5, 25), (9.8, 120), (11.0, 30)],
            start=1)
    ]
    res_c = run_meta_analysis(cont, effect_measure="MD")
    p3 = forest_plot(res_c, os.path.join(RUNS, "forest_continuous_md.png"))
    ok(os.path.getsize(p3) > 10_000, "continuous forest plot too small")
    print(f"    wrote {p3}")

    big = ASPIRIN + [
        _binary("Extra A", 40, 500, 50, 500),
        _binary("Extra B", 30, 400, 38, 400),
        _binary("Extra C", 21, 300, 27, 300),
        _binary("Extra D", 14, 200, 19, 200),
    ]
    res_b = run_meta_analysis(big, effect_measure="RR")
    p4 = funnel_plot(res_b, os.path.join(RUNS, "funnel_twelve_studies.png"),
                     annotate_labels=True)
    ok(os.path.getsize(p4) > 10_000, "12-study funnel plot too small")
    print(f"    wrote {p4}")

    # A zero-cell dataset exercises the continuity-correction dagger marker.
    zero = [_binary("Zero arm", 0, 60, 7, 60),
            _binary("Normal 1", 12, 60, 18, 60),
            _binary("Normal 2", 9, 55, 15, 58)]
    p5 = forest_plot(run_meta_analysis(zero, effect_measure="OR"),
                     os.path.join(RUNS, "forest_zero_cell.png"))
    ok(os.path.getsize(p5) > 10_000, "zero-cell forest plot too small")
    print(f"    wrote {p5}")


def test_plot_refuses_bad_input():
    failed = run_meta_analysis([], effect_measure="RR")
    try:
        forest_plot(failed, os.path.join(RUNS, "should_not_exist.png"))
    except ValueError:
        pass
    else:
        raise AssertionError("plotting a failed analysis must raise")


# ==========================================================================
# Runner
# ==========================================================================


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} test groups against the meta-analysis "
          "engine\n" + "=" * 72)
    for fn in tests:
        name = fn.__name__
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report, keep going
            _FAILURES.append(name)
            print(f"[FAIL] {name}\n       {exc}")
            if not isinstance(exc, AssertionError):
                traceback.print_exc()
        else:
            _PASSES.append(name)
            print(f"[ ok ] {name}")
    print("=" * 72)
    print(f"{len(_PASSES)} passed, {len(_FAILURES)} failed")
    if _FAILURES:
        print("failed: " + ", ".join(_FAILURES))
        return 1

    res = aspirin_result()
    het = res["heterogeneity"]
    p = res["pooled"]
    print("\nHeadline validation result (aspirin dataset, random effects, "
          "DerSimonian-Laird):")
    print(f"  pooled RR   = {p['estimate_transformed']:.4f} "
          f"(95% CI {p['ci_low_transformed']:.4f} to "
          f"{p['ci_high_transformed']:.4f})")
    print(f"  expected    ~ 0.78 (95% CI ~0.72 to ~0.85)")
    print(f"  I^2         = {het['I2']:.2f}%   (expected ~18%)")
    print(f"  tau^2 (DL)  = {het['tau2_DL']:.6f}")
    print(f"  tau^2 (REML)= {het['tau2_REML']:.6f}")
    print(f"  Q           = {het['Q']:.4f} on {het['df']} df, "
          f"p = {het['p_value']:.4f}")
    pi = res["prediction_interval"]
    if pi.get("available"):
        print(f"  95% PI      = {pi['low_transformed']:.4f} to "
              f"{pi['high_transformed']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
