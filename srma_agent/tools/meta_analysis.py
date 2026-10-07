"""Deterministic meta-analysis engine: the single source of numerical truth.

The SRMA specification forbids the language model from ever computing or
guessing a number. Every statistic that reaches a report, a figure, or a
clinician must be produced here, in plain numpy/scipy, from the extracted
study data. Nothing in this module calls an LLM and nothing in it is
stochastic: the same input always yields bit-identical output.

What is implemented
-------------------
Effect measures
    Binary      Risk Ratio (RR), Odds Ratio (OR), Risk Difference (RD)
    Continuous  Mean Difference (MD), Standardised Mean Difference
                (Hedges' g, with the exact small-sample correction)

Pooling
    Fixed effect (inverse variance)
    Random effects, tau^2 by DerSimonian-Laird *and* by REML
    Hartung-Knapp-Sidik-Jonkman (HKSJ) variance adjustment with t reference

Heterogeneity
    Cochran's Q + p-value, I^2, H^2, tau^2, 95% prediction interval

Bias / robustness
    Egger's regression test, Begg's rank correlation test,
    leave-one-out sensitivity analysis, Duval & Tweedie trim-and-fill

Conventions, and why
--------------------
Continuity correction
    When *any* of the four cells of a 2x2 table is zero, 0.5 is added to all
    four cells before taking logs. This is the RevMan / Cochrane Handbook
    default. It is applied to all four cells (not only the zero one) because
    correcting a single cell biases the effect estimate. The correction is
    recorded per study in the output so a reviewer can see exactly where it
    was used.

Double-zero studies
    A study with no events in either arm carries no information about a
    *ratio* measure, and the continuity correction would manufacture a
    spurious estimate out of the arm sizes alone. Such studies are therefore
    excluded from RR and OR analyses (and reported as excluded, never
    silently dropped) but retained for RD, where they are informative.

Default random-effects estimator
    `model="random"` uses DerSimonian-Laird, which is what RevMan and the
    great majority of published Cochrane reviews use, so results are
    comparable with the literature. REML and HKSJ are always computed and
    returned alongside, and HKSJ is the statistically preferable choice when
    k is small; the output says so.

Prediction interval
    mu +/- t(k-2) * sqrt(tau^2 + SE(mu)^2), the Higgins-Thompson-Spiegelhalter
    form. Requires k >= 3.

Guardrails required by the specification
    * I^2 > 50% raises a flag demanding subgroup / sensitivity analysis.
    * Egger's and Begg's tests only run with k >= 10 studies; below that they
      are skipped and the output states why.
    * No study is ever dropped silently. Every excluded study appears in
      `excluded_studies` with a machine-readable reason.

Main entry point
----------------
    run_meta_analysis(studies, effect_measure="auto", model="random") -> dict

Returns a plain JSON-serialisable dict (no numpy scalars, no NaN/Inf) so it
can be wrapped directly as an ADK tool.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
from scipy import stats
from scipy.special import gammaln

__all__ = [
    "run_meta_analysis",
    "compute_effect_sizes",
    "fixed_effect",
    "random_effects",
    "tau2_dersimonian_laird",
    "tau2_reml",
    "heterogeneity",
    "prediction_interval",
    "eggers_test",
    "beggs_test",
    "leave_one_out",
    "trim_and_fill",
    "BINARY_MEASURES",
    "CONTINUOUS_MEASURES",
    "RATIO_MEASURES",
    "MIN_K_FOR_BIAS_TESTS",
    "CONTINUITY_CORRECTION",
]

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

BINARY_MEASURES = ("RR", "OR", "RD")
CONTINUOUS_MEASURES = ("MD", "SMD")
#: Measures analysed on the log scale and back-transformed for reporting.
RATIO_MEASURES = ("RR", "OR")

#: Cochrane / RevMan default continuity correction for zero cells.
CONTINUITY_CORRECTION = 0.5

#: Egger and Begg are badly underpowered below this; the spec mandates 10.
MIN_K_FOR_BIAS_TESTS = 10

#: I^2 above this (percent) triggers the mandatory-further-analysis flag.
I2_FLAG_THRESHOLD = 50.0

MEASURE_LABELS = {
    "RR": "Risk Ratio",
    "OR": "Odds Ratio",
    "RD": "Risk Difference",
    "MD": "Mean Difference",
    "SMD": "Standardised Mean Difference (Hedges' g)",
}

_Z = 1.959963984540054  # stats.norm.ppf(0.975), hard-coded for determinism


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _f(value: Any) -> float | None:
    """Coerce to a finite float, or None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _jsonify(obj: Any) -> Any:
    """Recursively convert to JSON-safe primitives.

    numpy scalars become python floats/ints; NaN and +/-Inf become None,
    because `json.dumps` emits bare `NaN`/`Infinity` tokens that are not
    valid JSON and break downstream consumers.
    """
    if isinstance(obj, dict):
        return {str(k): _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return val if math.isfinite(val) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return [_jsonify(v) for v in obj.tolist()]
    return obj


def _exp(value: float) -> float:
    """math.exp that saturates instead of raising on absurd inputs.

    A pathological extracted table can produce a log effect of several
    hundred. The tool must degrade to a non-finite value (which `_jsonify`
    renders as null) rather than raise out of an ADK tool call.
    """
    try:
        return math.exp(value)
    except OverflowError:
        return math.inf if value > 0 else 0.0


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    val = float(value)
    if not math.isfinite(val):
        return None
    return round(val, digits)


def _get(d: dict, *names: str) -> Any:
    """First present, non-None value among several key aliases."""
    for name in names:
        if name in d and d[name] is not None:
            return d[name]
    return None


# --------------------------------------------------------------------------
# Effect sizes: binary outcomes
# --------------------------------------------------------------------------


def binary_effect(
    e1: float,
    n1: float,
    e2: float,
    n2: float,
    measure: str,
    correction: float = CONTINUITY_CORRECTION,
) -> dict[str, Any]:
    """Effect size and variance for one 2x2 table.

    Args:
        e1, n1: events and total in the intervention (experimental) arm.
        e2, n2: events and total in the control arm.
        measure: one of "RR", "OR", "RD".
        correction: continuity correction added to all four cells when any
            cell is zero. 0.5 is the Cochrane/RevMan default.

    Returns:
        dict with keys `y` (effect on the analysis scale: log RR, log OR, or
        raw RD), `v` (variance of `y`), `corrected` (bool) and `detail`.

    Notes:
        log RR standard error uses the delta-method expression
            SE = sqrt(1/e1 - 1/n1 + 1/e2 - 1/n2)
        log OR uses
            SE = sqrt(1/a + 1/b + 1/c + 1/d)
        RD uses the binomial variance
            SE = sqrt(p1(1-p1)/n1 + p2(1-p2)/n2)
        RD is computed from the *uncorrected* proportions unless a zero cell
        forces a correction, since correcting otherwise shifts the estimate.
    """
    measure = measure.upper()
    a, b = float(e1), float(n1 - e1)  # events / non-events, intervention
    c, d = float(e2), float(n2 - e2)  # events / non-events, control

    needs_cc = min(a, b, c, d) == 0
    if needs_cc and correction > 0:
        a, b, c, d = a + correction, b + correction, c + correction, d + correction
        tot1, tot2 = a + b, c + d
        corrected = True
    else:
        tot1, tot2 = float(n1), float(n2)
        corrected = False

    if measure == "RR":
        y = math.log((a / tot1) / (c / tot2))
        v = 1.0 / a - 1.0 / tot1 + 1.0 / c - 1.0 / tot2
    elif measure == "OR":
        y = math.log((a * d) / (b * c))
        v = 1.0 / a + 1.0 / b + 1.0 / c + 1.0 / d
    elif measure == "RD":
        p1, p2 = a / tot1, c / tot2
        y = p1 - p2
        v = p1 * (1.0 - p1) / tot1 + p2 * (1.0 - p2) / tot2
    else:
        raise ValueError(f"Unknown binary measure: {measure!r}")

    return {
        "y": y,
        "v": v,
        "corrected": corrected,
        "detail": {
            "events_intervention": _f(e1),
            "n_intervention": _f(n1),
            "events_control": _f(e2),
            "n_control": _f(n2),
            "risk_intervention": _f(e1) / _f(n1) if n1 else None,
            "risk_control": _f(e2) / _f(n2) if n2 else None,
        },
    }


# --------------------------------------------------------------------------
# Effect sizes: continuous outcomes
# --------------------------------------------------------------------------


def _hedges_correction(df: float) -> float:
    """Exact small-sample bias correction J for Hedges' g.

    J = Gamma(df/2) / (sqrt(df/2) * Gamma((df-1)/2)), computed through
    `gammaln` so it is stable for large df. Falls back to the usual
    1 - 3/(4df - 1) approximation if df is too small for the gamma form.
    """
    if df <= 1:
        return 1.0 - 3.0 / (4.0 * df - 1.0) if (4.0 * df - 1.0) > 0 else 1.0
    log_j = gammaln(df / 2.0) - 0.5 * math.log(df / 2.0) - gammaln((df - 1.0) / 2.0)
    j = math.exp(log_j)
    if not math.isfinite(j) or j <= 0:
        return 1.0 - 3.0 / (4.0 * df - 1.0)
    return j


def continuous_effect(
    m1: float,
    sd1: float,
    n1: float,
    m2: float,
    sd2: float,
    n2: float,
    measure: str,
) -> dict[str, Any]:
    """Effect size and variance for one continuous (mean/SD/n) comparison.

    MD  = m1 - m2,  Var = sd1^2/n1 + sd2^2/n2
    SMD = Hedges' g = J * (m1 - m2) / s_pooled, with
          s_pooled = sqrt(((n1-1)sd1^2 + (n2-1)sd2^2) / (n1+n2-2))
          Var(g)   = 1/n1 + 1/n2 + g^2 / (2(n1+n2))
    The variance expression is the large-sample form applied to the
    bias-corrected g, matching `metafor::escalc(measure="SMD")`.
    """
    measure = measure.upper()
    n1, n2 = float(n1), float(n2)
    diff = float(m1) - float(m2)

    if measure == "MD":
        v = sd1 * sd1 / n1 + sd2 * sd2 / n2
        y = diff
        extra: dict[str, Any] = {}
    elif measure == "SMD":
        df = n1 + n2 - 2.0
        s_pooled = math.sqrt(
            ((n1 - 1.0) * sd1 * sd1 + (n2 - 1.0) * sd2 * sd2) / df
        )
        cohens_d = diff / s_pooled
        j = _hedges_correction(df)
        y = j * cohens_d
        v = 1.0 / n1 + 1.0 / n2 + (y * y) / (2.0 * (n1 + n2))
        extra = {
            "cohens_d": cohens_d,
            "hedges_correction_J": j,
            "pooled_sd": s_pooled,
        }
    else:
        raise ValueError(f"Unknown continuous measure: {measure!r}")

    detail = {
        "mean_intervention": _f(m1),
        "sd_intervention": _f(sd1),
        "n_intervention": n1,
        "mean_control": _f(m2),
        "sd_control": _f(sd2),
        "n_control": n2,
    }
    detail.update(extra)
    return {"y": y, "v": v, "corrected": False, "detail": detail}


# --------------------------------------------------------------------------
# Input normalisation
# --------------------------------------------------------------------------


def _extract_arms(study: dict) -> tuple[dict, dict, str]:
    """Pull intervention and control arm dicts out of a study record.

    Accepts the canonical `StudyExtraction` shape (nested `intervention_arm`
    / `control_arm` objects, as produced by `model_dump()`) and a small set
    of flat aliases for convenience when data is entered by hand.
    """
    label = str(
        _get(study, "study_label", "label", "study", "name", "study_id", "id")
        or "Unnamed study"
    )

    arm_i = _get(study, "intervention_arm", "treatment_arm", "experimental_arm")
    arm_c = _get(study, "control_arm", "comparator_arm", "placebo_arm")
    if isinstance(arm_i, dict) and isinstance(arm_c, dict):
        return dict(arm_i), dict(arm_c), label

    # Flat fallback.
    flat_i = {
        "n_events": _get(study, "events_intervention", "e1", "events_treat",
                         "events_t"),
        "n_total": _get(study, "n_intervention", "n1", "n_treat", "total_t"),
        "mean": _get(study, "mean_intervention", "m1", "mean1"),
        "sd": _get(study, "sd_intervention", "sd1"),
    }
    flat_c = {
        "n_events": _get(study, "events_control", "e2", "events_ctrl",
                         "events_c"),
        "n_total": _get(study, "n_control", "n2", "n_ctrl", "total_c"),
        "mean": _get(study, "mean_control", "m2", "mean2"),
        "sd": _get(study, "sd_control", "sd2"),
    }
    return flat_i, flat_c, label


def _classify(arm_i: dict, arm_c: dict) -> str:
    """Return "binary", "continuous" or "unusable" for one study."""
    def has_binary(a: dict) -> bool:
        return _f(_get(a, "n_events", "events")) is not None and \
            _f(_get(a, "n_total", "n", "total")) is not None

    def has_continuous(a: dict) -> bool:
        return (
            _f(_get(a, "mean")) is not None
            and _f(_get(a, "sd")) is not None
            and _f(_get(a, "n_total", "n", "total")) is not None
        )

    if has_binary(arm_i) and has_binary(arm_c):
        return "binary"
    if has_continuous(arm_i) and has_continuous(arm_c):
        return "continuous"
    return "unusable"


def compute_effect_sizes(
    studies: Sequence[dict],
    measure: str,
    correction: float = CONTINUITY_CORRECTION,
) -> tuple[list[dict], list[dict]]:
    """Turn raw study records into per-study effect sizes.

    Returns:
        (included, excluded). `included` entries carry `y`, `v`, `se`, the
        study label and the raw numbers. `excluded` entries carry the label
        and a plain-English `reason` plus a machine-readable `reason_code`.
        Nothing is ever discarded without an entry in `excluded`.
    """
    measure = measure.upper()
    included: list[dict] = []
    excluded: list[dict] = []

    for index, raw in enumerate(studies):
        if not isinstance(raw, dict):
            excluded.append({
                "index": index,
                "label": f"study[{index}]",
                "reason_code": "MALFORMED_RECORD",
                "reason": "Study record is not a mapping/dict.",
            })
            continue

        arm_i, arm_c, label = _extract_arms(raw)
        year = _f(_get(raw, "year"))
        kind = _classify(arm_i, arm_c)

        def reject(code: str, why: str) -> None:
            excluded.append({
                "index": index,
                "label": label,
                "reason_code": code,
                "reason": why,
            })

        if measure in BINARY_MEASURES:
            if kind != "binary":
                reject(
                    "MISSING_BINARY_DATA",
                    "Requires n_events and n_total in both arms; one or more "
                    "were missing.",
                )
                continue
            e1 = _f(_get(arm_i, "n_events", "events"))
            n1 = _f(_get(arm_i, "n_total", "n", "total"))
            e2 = _f(_get(arm_c, "n_events", "events"))
            n2 = _f(_get(arm_c, "n_total", "n", "total"))

            if n1 is None or n2 is None or n1 <= 0 or n2 <= 0:
                reject("ZERO_DENOMINATOR",
                       "Arm total (n_total) is zero or missing.")
                continue
            if e1 < 0 or e2 < 0:
                reject("NEGATIVE_EVENTS", "Negative event count.")
                continue
            if e1 > n1 or e2 > n2:
                reject("EVENTS_EXCEED_TOTAL",
                       f"Events exceed arm total ({e1:g}/{n1:g}, {e2:g}/{n2:g}).")
                continue
            if measure in RATIO_MEASURES and e1 == 0 and e2 == 0:
                reject(
                    "DOUBLE_ZERO",
                    "No events in either arm: uninformative for a ratio "
                    "measure, so excluded per Cochrane Handbook 10.4.4.1. "
                    "It would be retained in a risk-difference analysis.",
                )
                continue

            try:
                eff = binary_effect(e1, n1, e2, n2, measure, correction)
            except (ValueError, ZeroDivisionError) as exc:
                reject("UNCOMPUTABLE", f"Effect size could not be computed: {exc}")
                continue
            raw_detail = eff["detail"]

        elif measure in CONTINUOUS_MEASURES:
            if kind != "continuous":
                reject(
                    "MISSING_CONTINUOUS_DATA",
                    "Requires mean, sd and n_total in both arms; one or more "
                    "were missing.",
                )
                continue
            m1 = _f(_get(arm_i, "mean"))
            sd1 = _f(_get(arm_i, "sd"))
            n1 = _f(_get(arm_i, "n_total", "n", "total"))
            m2 = _f(_get(arm_c, "mean"))
            sd2 = _f(_get(arm_c, "sd"))
            n2 = _f(_get(arm_c, "n_total", "n", "total"))

            if n1 is None or n2 is None or n1 < 2 or n2 < 2:
                reject("INSUFFICIENT_N",
                       "Continuous outcomes need n >= 2 in both arms.")
                continue
            if sd1 is None or sd2 is None or sd1 <= 0 or sd2 <= 0:
                reject("MISSING_OR_INVALID_SD",
                       "Standard deviation missing or non-positive. SDs are "
                       "never imputed; the study is excluded and reported.")
                continue
            try:
                eff = continuous_effect(m1, sd1, n1, m2, sd2, n2, measure)
            except (ValueError, ZeroDivisionError) as exc:
                reject("UNCOMPUTABLE", f"Effect size could not be computed: {exc}")
                continue
            raw_detail = eff["detail"]
        else:
            raise ValueError(f"Unsupported effect measure: {measure!r}")

        y, v = eff["y"], eff["v"]
        if not math.isfinite(y) or not math.isfinite(v) or v <= 0:
            reject("NON_FINITE_EFFECT",
                   "Effect size or its variance was not finite/positive.")
            continue

        included.append({
            "index": index,
            "label": label,
            "year": int(year) if year is not None else None,
            "y": float(y),
            "v": float(v),
            "se": math.sqrt(v),
            "continuity_corrected": bool(eff["corrected"]),
            "raw": raw_detail,
        })

    return included, excluded


# --------------------------------------------------------------------------
# Pooling
# --------------------------------------------------------------------------


def _ci(estimate: float, se: float, crit: float) -> tuple[float, float]:
    return estimate - crit * se, estimate + crit * se


def fixed_effect(y: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    """Inverse-variance fixed-effect pool."""
    w = 1.0 / v
    sw = w.sum()
    mu = float((w * y).sum() / sw)
    se = float(math.sqrt(1.0 / sw))
    lo, hi = _ci(mu, se, _Z)
    z = mu / se if se > 0 else math.nan
    return {
        "model": "fixed",
        "tau2": 0.0,
        "estimate": mu,
        "se": se,
        "ci_low": lo,
        "ci_high": hi,
        "statistic": float(z),
        "statistic_type": "z",
        "df": None,
        "p_value": float(2.0 * stats.norm.sf(abs(z))),
        "weights": (w / sw * 100.0).tolist(),
        "k": int(y.size),
    }


def tau2_dersimonian_laird(y: np.ndarray, v: np.ndarray) -> float:
    """DerSimonian-Laird moment estimator of tau^2 (truncated at 0)."""
    k = y.size
    if k < 2:
        return 0.0
    w = 1.0 / v
    sw = w.sum()
    mu = (w * y).sum() / sw
    q = float((w * (y - mu) ** 2).sum())
    c = float(sw - (w ** 2).sum() / sw)
    if c <= 0:
        return 0.0
    return max(0.0, (q - (k - 1)) / c)


def _reml_loglik(tau2: float, y: np.ndarray, v: np.ndarray) -> float:
    """Restricted log-likelihood (up to an additive constant)."""
    w = 1.0 / (v + tau2)
    sw = w.sum()
    mu = (w * y).sum() / sw
    return float(
        -0.5 * np.log(v + tau2).sum()
        - 0.5 * math.log(sw)
        - 0.5 * (w * (y - mu) ** 2).sum()
    )


def tau2_reml(
    y: np.ndarray,
    v: np.ndarray,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> dict[str, Any]:
    """REML estimator of tau^2.

    Uses the standard fixed-point iteration

        tau2 <- [ sum w_i^2 ((y_i - mu)^2 - v_i) ] / sum w_i^2  +  1 / sum w_i

    started from the DerSimonian-Laird estimate and truncated at zero. If the
    iteration has not converged within `max_iter`, the restricted
    log-likelihood is maximised directly by a bounded scalar search, so the
    function always returns a defensible value and says which route it took.
    """
    k = y.size
    if k < 2:
        return {"tau2": 0.0, "converged": True, "iterations": 0,
                "method": "trivial (k < 2)"}

    tau2 = tau2_dersimonian_laird(y, v)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        w = 1.0 / (v + tau2)
        sw = w.sum()
        mu = (w * y).sum() / sw
        w2 = w ** 2
        new = float((w2 * ((y - mu) ** 2 - v)).sum() / w2.sum() + 1.0 / sw)
        new = max(0.0, new)
        if abs(new - tau2) < tol * max(1.0, abs(tau2)):
            tau2 = new
            converged = True
            break
        tau2 = new

    if not converged:
        # Fallback: direct bounded maximisation of the restricted likelihood.
        upper = max(10.0 * float(np.var(y, ddof=1) + v.max()), 1e-6)
        grid = np.linspace(0.0, upper, 2001)
        lls = np.array([_reml_loglik(t, y, v) for t in grid])
        tau2 = float(grid[int(np.argmax(lls))])
        return {"tau2": tau2, "converged": False, "iterations": iterations,
                "method": "grid maximisation of restricted log-likelihood"}

    return {"tau2": float(tau2), "converged": True, "iterations": iterations,
            "method": "fixed-point REML iteration"}


def random_effects(
    y: np.ndarray,
    v: np.ndarray,
    tau2: float,
    hksj: bool = False,
    tau2_method: str = "DL",
) -> dict[str, Any]:
    """Random-effects pool for a given tau^2.

    With `hksj=True` the Hartung-Knapp-Sidik-Jonkman variance estimator is
    used,

        SE_HKSJ^2 = sum w_i (y_i - mu)^2 / ((k - 1) * sum w_i)

    and inference uses a t distribution on k-1 degrees of freedom. This is
    not truncated at the classical variance (matching `metafor`'s default
    `test="knha"`); it can therefore give a *narrower* interval than the
    ordinary random-effects one when the studies agree unusually well.
    """
    k = int(y.size)
    w = 1.0 / (v + tau2)
    sw = w.sum()
    mu = float((w * y).sum() / sw)

    if hksj and k >= 2:
        q_hk = float((w * (y - mu) ** 2).sum() / (k - 1))
        se = math.sqrt(q_hk / sw)
        df = k - 1
        crit = float(stats.t.ppf(0.975, df))
        statistic = mu / se if se > 0 else math.nan
        p = float(2.0 * stats.t.sf(abs(statistic), df))
        stat_type = "t"
    else:
        se = math.sqrt(1.0 / sw)
        df = None
        crit = _Z
        statistic = mu / se if se > 0 else math.nan
        p = float(2.0 * stats.norm.sf(abs(statistic)))
        stat_type = "z"

    lo, hi = _ci(mu, se, crit)
    return {
        "model": "random-effects (HKSJ)" if hksj else "random-effects",
        "tau2_method": tau2_method,
        "hksj": bool(hksj),
        "tau2": float(tau2),
        "estimate": mu,
        "se": float(se),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "statistic": float(statistic),
        "statistic_type": stat_type,
        "df": df,
        "p_value": p,
        "weights": (w / sw * 100.0).tolist(),
        "k": k,
    }


# --------------------------------------------------------------------------
# Heterogeneity
# --------------------------------------------------------------------------


def heterogeneity(y: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    """Cochran's Q, its p-value, I^2, H^2 and tau^2 (DL and REML).

    Q  = sum w_i (y_i - mu_FE)^2, w_i = 1/v_i, df = k - 1
    I2 = max(0, (Q - df) / Q) * 100
    H2 = Q / df   (reported truncated at 1, as H^2 < 1 is not interpretable)
    """
    k = int(y.size)
    if k < 2:
        return {
            "k": k, "Q": None, "df": max(k - 1, 0), "p_value": None,
            "I2": None, "H2": None, "tau2_DL": 0.0, "tau2_REML": 0.0,
            "tau2": 0.0, "tau": 0.0, "reml_converged": True,
            "reml_iterations": 0,
            "interpretation": "Heterogeneity is undefined with fewer than 2 studies.",
        }

    w = 1.0 / v
    sw = w.sum()
    mu = (w * y).sum() / sw
    q = float((w * (y - mu) ** 2).sum())
    df = k - 1
    p = float(stats.chi2.sf(q, df))
    i2 = max(0.0, (q - df) / q) * 100.0 if q > 0 else 0.0
    h2 = max(1.0, q / df) if df > 0 else None

    dl = tau2_dersimonian_laird(y, v)
    reml = tau2_reml(y, v)

    if i2 < 30:
        interp = "Heterogeneity may not be important (I^2 < 30%)."
    elif i2 < 50:
        interp = "Moderate heterogeneity (I^2 30-50%)."
    elif i2 < 75:
        interp = "Substantial heterogeneity (I^2 50-75%)."
    else:
        interp = "Considerable heterogeneity (I^2 > 75%)."

    return {
        "k": k,
        "Q": q,
        "df": df,
        "p_value": p,
        "I2": float(i2),
        "H2": float(h2) if h2 is not None else None,
        "tau2_DL": float(dl),
        "tau2_REML": float(reml["tau2"]),
        "tau2": float(dl),          # the headline value, matching RevMan
        "tau": float(math.sqrt(dl)),
        "reml_converged": bool(reml["converged"]),
        "reml_iterations": reml["iterations"],
        "interpretation": interp,
    }


def prediction_interval(
    estimate: float,
    se: float,
    tau2: float,
    k: int,
) -> dict[str, Any]:
    """95% prediction interval for the effect in a future study.

    mu +/- t(k-2) * sqrt(tau^2 + SE(mu)^2), per Higgins, Thompson &
    Spiegelhalter (2009). Undefined for k < 3.
    """
    if k < 3:
        return {
            "available": False,
            "reason": f"A prediction interval needs at least 3 studies (k={k}).",
            "low": None, "high": None,
        }
    df = k - 2
    crit = float(stats.t.ppf(0.975, df))
    width = crit * math.sqrt(tau2 + se * se)
    return {
        "available": True,
        "df": df,
        "low": float(estimate - width),
        "high": float(estimate + width),
        "note": "Range within which the true effect of a future comparable "
                "study is expected to lie, 95% of the time.",
    }


# --------------------------------------------------------------------------
# Publication bias
# --------------------------------------------------------------------------


def eggers_test(y: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    """Egger's regression test for funnel-plot asymmetry.

    Regresses the standard normal deviate y_i/se_i on precision 1/se_i by
    ordinary least squares; a non-zero intercept indicates asymmetry. The
    intercept is tested with a t statistic on k-2 degrees of freedom.
    """
    k = int(y.size)
    if k < 3:
        return {"performed": False,
                "reason": f"Egger's test requires at least 3 studies (k={k})."}

    se = np.sqrt(v)
    snd = y / se
    precision = 1.0 / se

    x_mean = precision.mean()
    y_mean = snd.mean()
    sxx = float(((precision - x_mean) ** 2).sum())
    if sxx <= 0:
        return {"performed": False,
                "reason": "All studies have identical precision; the "
                          "regression is degenerate."}
    sxy = float(((precision - x_mean) * (snd - y_mean)).sum())
    slope = sxy / sxx
    intercept = float(y_mean - slope * x_mean)

    fitted = intercept + slope * precision
    rss = float(((snd - fitted) ** 2).sum())
    df = k - 2
    s2 = rss / df
    se_intercept = math.sqrt(s2 * (1.0 / k + x_mean ** 2 / sxx))
    t_stat = intercept / se_intercept if se_intercept > 0 else math.nan
    p = float(2.0 * stats.t.sf(abs(t_stat), df))

    return {
        "performed": True,
        "intercept": intercept,
        "se_intercept": float(se_intercept),
        "slope": float(slope),
        "t": float(t_stat),
        "df": df,
        "p_value": p,
        "asymmetry_detected": bool(p < 0.05),
        "interpretation": (
            "Funnel-plot asymmetry detected (p < 0.05). This is consistent "
            "with publication bias or small-study effects, but asymmetry has "
            "other causes (true heterogeneity, poor methods in small trials) "
            "and is not proof of bias."
            if p < 0.05 else
            "No statistically significant funnel-plot asymmetry (p >= 0.05). "
            "Absence of evidence of bias is not evidence of its absence."
        ),
    }


def beggs_test(y: np.ndarray, v: np.ndarray) -> dict[str, Any]:
    """Begg & Mazumdar rank correlation test.

    Kendall's tau between the variance-standardised effect sizes and their
    variances:  y*_i = (y_i - mu_FE) / sqrt(v_i - 1/sum(1/v_j)).
    """
    k = int(y.size)
    if k < 3:
        return {"performed": False,
                "reason": f"Begg's test requires at least 3 studies (k={k})."}

    w = 1.0 / v
    mu_fe = (w * y).sum() / w.sum()
    v_star = v - 1.0 / w.sum()
    if np.any(v_star <= 0):
        return {"performed": False,
                "reason": "Standardised variances were non-positive; the "
                          "rank correlation is undefined for this data."}
    y_star = (y - mu_fe) / np.sqrt(v_star)

    # Unpack as a tuple: the field names on SciPy's result object changed
    # between versions (correlation -> statistic), but the order did not.
    tau_stat, p_value = stats.kendalltau(y_star, v, variant="b")
    tau_stat = float(tau_stat)
    p = float(p_value)
    return {
        "performed": True,
        "kendall_tau": tau_stat,
        "p_value": p,
        "asymmetry_detected": bool(p < 0.05),
        "interpretation": (
            "Rank correlation between effect size and variance is significant "
            "(p < 0.05): small-study effects are present."
            if p < 0.05 else
            "No significant rank correlation (p >= 0.05). Begg's test has low "
            "power; a null result is weak evidence."
        ),
    }


def trim_and_fill(
    y: np.ndarray,
    v: np.ndarray,
    tau2_estimator: str = "DL",
    use_random: bool = True,
    estimator: str = "L0",
    max_iter: int = 100,
) -> dict[str, Any]:
    """Duval & Tweedie (2000) trim-and-fill.

    Implements the iterative algorithm exactly as described in the original
    paper and in `metafor::trimfill`:

      1. The side on which studies appear to be missing is inferred from the
         sign of the slope of y regressed on sqrt(v). Data are sign-flipped
         so that missing studies are always treated as being on the left.
      2. With the current pooled estimate, effects are centred, ranked by
         absolute value and re-signed. The number of missing studies k0 is
         estimated by L0 = (4*Sr - k(k+1)) / (2k - 1) where Sr is the sum of
         the ranks of the positive deviations, or by R0 = (k - max rank of a
         positive deviation) - 1.
      3. The k0 largest effects are trimmed, the pool is refitted, and steps
         2-3 repeat until k0 is stable.
      4. k0 mirror-image studies (2*mu - y_i, same variance) are added for
         the k0 largest effects and the model is refitted on the augmented
         set. That refit is the bias-adjusted estimate.

    The method assumes asymmetry is caused by suppression of studies and is
    known to over-impute under genuine heterogeneity; the adjusted estimate
    is a sensitivity analysis, never a replacement for the primary result.
    """
    k = int(y.size)
    if k < 3:
        return {"performed": False,
                "reason": f"Trim-and-fill requires at least 3 studies (k={k})."}

    def pool(yy: np.ndarray, vv: np.ndarray) -> float:
        if use_random and yy.size >= 2:
            tau2 = (tau2_dersimonian_laird(yy, vv) if tau2_estimator == "DL"
                    else tau2_reml(yy, vv)["tau2"])
            w = 1.0 / (vv + tau2)
        else:
            w = 1.0 / vv
        return float((w * yy).sum() / w.sum())

    # --- 1. which side are studies missing from? -------------------------
    se = np.sqrt(v)
    slope_num = float(((se - se.mean()) * (y - y.mean())).sum())
    slope_den = float(((se - se.mean()) ** 2).sum())
    slope = slope_num / slope_den if slope_den > 0 else 0.0
    side = "right" if slope < 0 else "left"
    # Work in a frame where the missing studies are on the left, so the
    # studies to trim are the largest ones.
    flip = -1.0 if side == "right" else 1.0
    yf = flip * y

    # --- 2/3. iterate trim --------------------------------------------
    order = np.argsort(yf, kind="stable")   # ascending effect
    k0 = 0
    mu = pool(yf, v)
    iterations = 0
    for iterations in range(1, max_iter + 1):
        keep = order[: k - k0] if k0 > 0 else order
        yk, vk = yf[keep], v[keep]
        mu = pool(yk, vk)

        centred = yf - mu
        absr = stats.rankdata(np.abs(centred), method="ordinal")
        signed = np.sign(centred) * absr

        if estimator.upper() == "R0":
            positives = signed[signed > 0]
            gamma = 0.0 if positives.size == 0 else float(k - positives.max())
            new_k0 = max(0, int(math.floor(gamma - 1.0 + 1e-9)))
        else:  # L0
            sr = float(signed[signed > 0].sum())
            l0 = (4.0 * sr - k * (k + 1.0)) / (2.0 * k - 1.0)
            new_k0 = max(0, int(math.floor(l0 + 0.5)))
        new_k0 = min(new_k0, k - 1)

        if new_k0 == k0:
            k0 = new_k0
            break
        k0 = new_k0

    # --- 4. fill and refit ----------------------------------------------
    if k0 == 0:
        return {
            "performed": True,
            "estimator": estimator.upper(),
            "side_imputed": side,
            "n_missing_estimated": 0,
            "iterations": iterations,
            "adjusted_estimate": None,
            "imputed_effects": [],
            "note": "No missing studies were estimated; the funnel plot is "
                    "symmetric under this method and no adjustment is needed.",
        }

    largest = order[-k0:]                 # the k0 most extreme (right) effects
    imputed_y = 2.0 * mu - yf[largest]
    imputed_v = v[largest]
    aug_y = np.concatenate([yf, imputed_y])
    aug_v = np.concatenate([v, imputed_v])

    tau2_aug = (tau2_dersimonian_laird(aug_y, aug_v) if tau2_estimator == "DL"
                else tau2_reml(aug_y, aug_v)["tau2"])
    fit = (random_effects(aug_y, aug_v, tau2_aug, tau2_method=tau2_estimator)
           if use_random else fixed_effect(aug_y, aug_v))

    # Undo the sign flip so results are on the original scale.
    adj = flip * fit["estimate"]
    lo, hi = sorted([flip * fit["ci_low"], flip * fit["ci_high"]])
    return {
        "performed": True,
        "estimator": estimator.upper(),
        "side_imputed": side,
        "n_missing_estimated": int(k0),
        "iterations": iterations,
        "adjusted_estimate": float(adj),
        "adjusted_ci_low": float(lo),
        "adjusted_ci_high": float(hi),
        "adjusted_tau2": float(tau2_aug),
        "k_augmented": int(aug_y.size),
        "imputed_effects": (flip * imputed_y).tolist(),
        "imputed_variances": imputed_v.tolist(),
        "note": "Trim-and-fill is a sensitivity analysis. It assumes "
                "asymmetry is caused by missing studies and over-imputes "
                "when heterogeneity is real. Report it beside the primary "
                "estimate, never in place of it.",
    }


# --------------------------------------------------------------------------
# Leave-one-out
# --------------------------------------------------------------------------


def leave_one_out(
    effects: Sequence[dict],
    model: str,
    tau2_estimator: str,
    hksj: bool,
) -> list[dict]:
    """Refit the model k times, each time omitting one study."""
    k = len(effects)
    if k < 3:
        return []
    out: list[dict] = []
    for i in range(k):
        sub = [e for j, e in enumerate(effects) if j != i]
        y = np.array([e["y"] for e in sub], dtype=float)
        v = np.array([e["v"] for e in sub], dtype=float)
        if model == "fixed":
            fit = fixed_effect(y, v)
            tau2 = 0.0
        else:
            tau2 = (tau2_dersimonian_laird(y, v) if tau2_estimator == "DL"
                    else tau2_reml(y, v)["tau2"])
            fit = random_effects(y, v, tau2, hksj=hksj,
                                 tau2_method=tau2_estimator)
        het = heterogeneity(y, v)
        out.append({
            "omitted_study": effects[i]["label"],
            "k_remaining": k - 1,
            "estimate": fit["estimate"],
            "ci_low": fit["ci_low"],
            "ci_high": fit["ci_high"],
            "p_value": fit["p_value"],
            "tau2": tau2,
            "I2": het["I2"],
            "Q": het["Q"],
        })
    return out


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------


def _auto_measure(studies: Sequence[dict]) -> tuple[str, list[str]]:
    """Choose an effect measure from the fields that are actually present."""
    notes: list[str] = []
    n_binary = n_continuous = 0
    for raw in studies:
        if not isinstance(raw, dict):
            continue
        arm_i, arm_c, _ = _extract_arms(raw)
        kind = _classify(arm_i, arm_c)
        if kind == "binary":
            n_binary += 1
        elif kind == "continuous":
            n_continuous += 1

    if n_binary == 0 and n_continuous == 0:
        notes.append(
            "Auto-detection found neither complete binary (events/total) nor "
            "complete continuous (mean/SD/n) data in any study."
        )
        return "RR", notes

    if n_binary >= n_continuous:
        notes.append(
            f"Auto-detected binary outcome data in {n_binary} study/studies; "
            "using the Risk Ratio, which is the more interpretable of the "
            "ratio measures for clinicians."
        )
        if n_continuous:
            notes.append(
                f"{n_continuous} study/studies carried continuous data only "
                "and will be reported as excluded."
            )
        return "RR", notes

    notes.append(
        f"Auto-detected continuous outcome data in {n_continuous} "
        "study/studies; using the Standardised Mean Difference (Hedges' g). "
        "SMD is chosen because it cannot be verified programmatically that "
        "every study measured the outcome on the same scale. If they did, "
        "pass effect_measure='MD' for a more interpretable result."
    )
    if n_binary:
        notes.append(
            f"{n_binary} study/studies carried binary data only and will be "
            "reported as excluded."
        )
    return "SMD", notes


def _normalise_model(model: str) -> tuple[str, str, bool, list[str]]:
    """Map the user-facing `model` string onto (kind, tau2 estimator, hksj)."""
    key = (model or "random").strip().lower().replace("-", "_").replace(" ", "_")
    notes: list[str] = []
    table = {
        "fixed": ("fixed", "none", False),
        "fe": ("fixed", "none", False),
        "fixed_effect": ("fixed", "none", False),
        "common": ("fixed", "none", False),
        "random": ("random", "DL", False),
        "re": ("random", "DL", False),
        "random_effects": ("random", "DL", False),
        "dl": ("random", "DL", False),
        "random_dl": ("random", "DL", False),
        "dersimonian_laird": ("random", "DL", False),
        "reml": ("random", "REML", False),
        "random_reml": ("random", "REML", False),
        "hksj": ("random", "REML", True),
        "random_hksj": ("random", "DL", True),
        "random_dl_hksj": ("random", "DL", True),
        "random_reml_hksj": ("random", "REML", True),
        "reml_hksj": ("random", "REML", True),
    }
    if key not in table:
        notes.append(
            f"Unrecognised model {model!r}; defaulting to random effects with "
            "DerSimonian-Laird. Valid values: 'fixed', 'random', "
            "'random_reml', 'random_hksj', 'random_reml_hksj'."
        )
        key = "random"
    kind, tau2_est, hksj = table[key]
    if kind == "random" and tau2_est == "DL" and not hksj:
        notes.append(
            "Primary model is random effects with DerSimonian-Laird tau^2, "
            "the RevMan/Cochrane default, so the result is comparable with "
            "published reviews. REML and HKSJ results are reported alongside "
            "and should be preferred when k is small."
        )
    return kind, tau2_est, hksj, notes


def _summarise(fit: dict, measure: str) -> dict[str, Any]:
    """Add back-transformed values for ratio measures."""
    out = dict(fit)
    is_ratio = measure in RATIO_MEASURES
    out["scale"] = "log" if is_ratio else "raw"
    if is_ratio:
        out["estimate_transformed"] = _exp(fit["estimate"])
        out["ci_low_transformed"] = _exp(fit["ci_low"])
        out["ci_high_transformed"] = _exp(fit["ci_high"])
    else:
        out["estimate_transformed"] = fit["estimate"]
        out["ci_low_transformed"] = fit["ci_low"]
        out["ci_high_transformed"] = fit["ci_high"]
    return out


def run_meta_analysis(
    studies: list[dict],
    effect_measure: str = "auto",
    model: str = "random",
) -> dict[str, Any]:
    """Run a complete meta-analysis and return a JSON-serialisable summary.

    Args:
        studies: Study records. Each may be a `StudyExtraction.model_dump()`
            (nested `intervention_arm` / `control_arm` with `n_events`,
            `n_total`, `mean`, `sd`) or a flat dict using the aliases
            `events_intervention`/`n_intervention`/`events_control`/
            `n_control` or `mean_intervention`/`sd_intervention`/...
        effect_measure: "auto", "RR", "OR", "RD", "MD" or "SMD". With "auto"
            the measure is inferred from which fields are populated.
        model: "fixed", "random" (DerSimonian-Laird, the default),
            "random_reml", "random_hksj", "random_reml_hksj".

    Returns:
        A dict with the pooled estimate under every model, per-study effects
        and weights, full heterogeneity statistics, a prediction interval,
        publication-bias tests, leave-one-out results, the list of excluded
        studies with reasons, and human-readable warnings and flags. Ratio
        measures are reported both on the log scale (`estimate`) and
        back-transformed (`estimate_transformed`).

        On failure the dict has `ok=False` and an `error` string; it never
        raises for ordinary data problems.
    """
    notes: list[str] = []
    warnings: list[str] = []
    flags: list[dict[str, str]] = []

    if not isinstance(studies, Iterable) or isinstance(studies, (str, bytes)):
        return _jsonify({
            "ok": False,
            "error": "`studies` must be a list of study dicts.",
            "k_supplied": 0,
        })
    studies = list(studies)

    # --- effect measure -------------------------------------------------
    requested = (effect_measure or "auto").strip()
    if requested.lower() == "auto":
        measure, auto_notes = _auto_measure(studies)
        notes.extend(auto_notes)
    else:
        measure = requested.upper()
        if measure in ("HEDGES_G", "HEDGES G", "G"):
            measure = "SMD"
        if measure not in BINARY_MEASURES + CONTINUOUS_MEASURES:
            return _jsonify({
                "ok": False,
                "error": (f"Unsupported effect_measure {effect_measure!r}. "
                          f"Use one of {BINARY_MEASURES + CONTINUOUS_MEASURES} "
                          "or 'auto'."),
                "k_supplied": len(studies),
            })

    kind, tau2_estimator, hksj, model_notes = _normalise_model(model)
    notes.extend(model_notes)

    # --- per-study effect sizes -----------------------------------------
    included, excluded = compute_effect_sizes(studies, measure)
    k = len(included)

    if excluded:
        warnings.append(
            f"{len(excluded)} of {len(studies)} supplied study/studies could "
            "not be analysed; see `excluded_studies` for the reason for each. "
            "No study was dropped silently."
        )

    if k == 0:
        return _jsonify({
            "ok": False,
            "error": "No study contained data sufficient for this analysis.",
            "effect_measure": measure,
            "k_supplied": len(studies),
            "k_included": 0,
            "excluded_studies": excluded,
            "warnings": warnings,
            "notes": notes,
        })

    y = np.array([e["y"] for e in included], dtype=float)
    v = np.array([e["v"] for e in included], dtype=float)
    is_ratio = measure in RATIO_MEASURES

    if k == 1:
        warnings.append(
            "Only one study could be analysed. No pooling, heterogeneity or "
            "bias assessment is possible; the single study's effect is "
            "reported as-is."
        )

    # --- pooling --------------------------------------------------------
    fe = fixed_effect(y, v)
    tau2_dl = tau2_dersimonian_laird(y, v)
    reml_info = tau2_reml(y, v)
    tau2_re = reml_info["tau2"]

    re_dl = random_effects(y, v, tau2_dl, hksj=False, tau2_method="DL")
    re_reml = random_effects(y, v, tau2_re, hksj=False, tau2_method="REML")
    re_dl_hksj = random_effects(y, v, tau2_dl, hksj=True, tau2_method="DL")
    re_reml_hksj = random_effects(y, v, tau2_re, hksj=True, tau2_method="REML")

    if kind == "fixed":
        primary = fe
        primary_tau2 = 0.0
    else:
        primary_tau2 = tau2_dl if tau2_estimator == "DL" else tau2_re
        if tau2_estimator == "DL":
            primary = re_dl_hksj if hksj else re_dl
        else:
            primary = re_reml_hksj if hksj else re_reml

    if not reml_info["converged"]:
        warnings.append(
            "The REML iteration for tau^2 did not converge; the value was "
            "obtained by direct maximisation of the restricted likelihood "
            "instead. Treat the REML results with caution."
        )

    # --- heterogeneity ---------------------------------------------------
    het = heterogeneity(y, v)
    pred = prediction_interval(
        primary["estimate"], primary["se"], primary_tau2, k
    )

    if het["I2"] is not None and het["I2"] > I2_FLAG_THRESHOLD:
        flags.append({
            "code": "HIGH_HETEROGENEITY",
            "severity": "high",
            "message": (
                f"I^2 = {het['I2']:.1f}% exceeds the {I2_FLAG_THRESHOLD:.0f}% "
                "threshold. Subgroup and/or sensitivity analysis is REQUIRED "
                "before the pooled estimate may be reported as a single "
                "summary. Investigate clinical and methodological diversity "
                "first; do not simply switch models."
            ),
        })
    if kind == "fixed" and het["I2"] is not None and het["I2"] > 50:
        warnings.append(
            "A fixed-effect model was requested but heterogeneity is "
            "substantial. The fixed-effect confidence interval is too narrow "
            "under these conditions; the random-effects result is also "
            "reported."
        )

    n_corrected = sum(1 for e in included if e["continuity_corrected"])
    if n_corrected:
        warnings.append(
            f"A continuity correction of {CONTINUITY_CORRECTION} was added to "
            f"all four cells of {n_corrected} study/studies that contained a "
            "zero cell. This is the Cochrane/RevMan default; it biases "
            "estimates towards the null and is less reliable when arm sizes "
            "are very unequal."
        )

    # --- bias and robustness --------------------------------------------
    if k >= MIN_K_FOR_BIAS_TESTS:
        egger = eggers_test(y, v)
        begg = beggs_test(y, v)
        taf = trim_and_fill(
            y, v,
            tau2_estimator=("DL" if tau2_estimator in ("DL", "none")
                            else "REML"),
            use_random=(kind != "fixed"),
        )
    else:
        skip = (
            f"Skipped: only {k} studies are available and the protocol "
            f"requires at least {MIN_K_FOR_BIAS_TESTS}. Below that the test "
            "has too little power to distinguish real asymmetry from chance, "
            "so a result would be misleading rather than merely uncertain."
        )
        egger = {"performed": False, "reason": skip}
        begg = {"performed": False, "reason": skip}
        taf = {"performed": False, "reason": skip}
        flags.append({
            "code": "BIAS_TESTS_SKIPPED",
            "severity": "info",
            "message": (
                f"Publication-bias testing was not performed (k={k} < "
                f"{MIN_K_FOR_BIAS_TESTS}). Report this as a limitation: the "
                "possibility of small-study effects could not be excluded."
            ),
        })

    if egger.get("asymmetry_detected") or begg.get("asymmetry_detected"):
        flags.append({
            "code": "FUNNEL_ASYMMETRY",
            "severity": "high",
            "message": (
                "A test for funnel-plot asymmetry was statistically "
                "significant. Consider downgrading the certainty of evidence "
                "for publication bias in the GRADE assessment."
            ),
        })

    loo = leave_one_out(included, kind, tau2_estimator, hksj)
    if loo:
        ests = [row["estimate"] for row in loo]
        sig = [(row["ci_low"] > 0) or (row["ci_high"] < 0) for row in loo]
        primary_sig = (primary["ci_low"] > 0) or (primary["ci_high"] < 0)
        if any(s != primary_sig for s in sig):
            unstable = [
                loo[i]["omitted_study"] for i, s in enumerate(sig)
                if s != primary_sig
            ]
            flags.append({
                "code": "UNSTABLE_TO_SINGLE_STUDY",
                "severity": "high",
                "message": (
                    "The statistical significance of the pooled effect "
                    "changes when these studies are removed one at a time: "
                    + ", ".join(unstable) +
                    ". The conclusion is not robust and must be qualified."
                ),
            })
        loo_summary = {
            "min_estimate": float(min(ests)),
            "max_estimate": float(max(ests)),
            "range_transformed": (
                [_exp(min(ests)), _exp(max(ests))] if is_ratio
                else [min(ests), max(ests)]
            ),
        }
    else:
        loo_summary = {
            "note": f"Leave-one-out requires at least 3 studies (k={k})."
        }

    # --- per-study output -------------------------------------------------
    w_fe = 1.0 / v
    w_re = 1.0 / (v + primary_tau2)
    study_rows = []
    for i, e in enumerate(included):
        lo, hi = _ci(e["y"], e["se"], _Z)
        row = {
            "label": e["label"],
            "year": e["year"],
            "effect": e["y"],
            "se": e["se"],
            "variance": e["v"],
            "ci_low": lo,
            "ci_high": hi,
            "effect_transformed": _exp(e["y"]) if is_ratio else e["y"],
            "ci_low_transformed": _exp(lo) if is_ratio else lo,
            "ci_high_transformed": _exp(hi) if is_ratio else hi,
            "weight_fixed_pct": float(w_fe[i] / w_fe.sum() * 100.0),
            "weight_random_pct": float(w_re[i] / w_re.sum() * 100.0),
            "continuity_corrected": e["continuity_corrected"],
            "raw": e["raw"],
        }
        study_rows.append(row)

    result: dict[str, Any] = {
        "ok": True,
        "effect_measure": measure,
        "effect_measure_label": MEASURE_LABELS[measure],
        "is_ratio_measure": is_ratio,
        "analysis_scale": "log" if is_ratio else "raw",
        "null_value": 1.0 if is_ratio else 0.0,
        "requested_model": model,
        "model": primary["model"],
        "tau2_estimator": tau2_estimator,
        "hksj_applied": hksj,
        "k_supplied": len(studies),
        "k_included": k,
        "k_excluded": len(excluded),
        "total_participants": _total_participants(included),

        "pooled": _summarise(primary, measure),
        "models": {
            "fixed_effect": _summarise(fe, measure),
            "random_effects_DL": _summarise(re_dl, measure),
            "random_effects_REML": _summarise(re_reml, measure),
            "random_effects_DL_HKSJ": _summarise(re_dl_hksj, measure),
            "random_effects_REML_HKSJ": _summarise(re_reml_hksj, measure),
        },
        "heterogeneity": het,
        "prediction_interval": _pi_transformed(pred, is_ratio),
        "publication_bias": {
            "min_studies_required": MIN_K_FOR_BIAS_TESTS,
            "egger": egger,
            "begg": begg,
            "trim_and_fill": _taf_transformed(taf, is_ratio),
        },
        "leave_one_out": _loo_transformed(loo, is_ratio),
        "leave_one_out_summary": loo_summary,
        "studies": study_rows,
        "excluded_studies": excluded,
        "flags": flags,
        "warnings": warnings,
        "notes": notes,
        "interpretation": _interpretation(primary, het, measure, k),
        "methods_text": _methods_text(measure, kind, tau2_estimator, hksj, k,
                                      n_corrected),
    }
    return _jsonify(result)


def _total_participants(included: Sequence[dict]) -> int | None:
    total = 0.0
    for e in included:
        n_i = e["raw"].get("n_intervention")
        n_c = e["raw"].get("n_control")
        if n_i is None or n_c is None:
            return None
        total += n_i + n_c
    return int(total)


def _pi_transformed(pred: dict, is_ratio: bool) -> dict:
    out = dict(pred)
    if pred.get("available") and is_ratio:
        out["low_transformed"] = _exp(pred["low"])
        out["high_transformed"] = _exp(pred["high"])
    elif pred.get("available"):
        out["low_transformed"] = pred["low"]
        out["high_transformed"] = pred["high"]
    return out


def _taf_transformed(taf: dict, is_ratio: bool) -> dict:
    out = dict(taf)
    if taf.get("performed") and taf.get("adjusted_estimate") is not None:
        f = _exp if is_ratio else (lambda x: x)
        out["adjusted_estimate_transformed"] = f(taf["adjusted_estimate"])
        out["adjusted_ci_low_transformed"] = f(taf["adjusted_ci_low"])
        out["adjusted_ci_high_transformed"] = f(taf["adjusted_ci_high"])
    return out


def _loo_transformed(loo: list[dict], is_ratio: bool) -> list[dict]:
    if not is_ratio:
        return loo
    out = []
    for row in loo:
        r = dict(row)
        r["estimate_transformed"] = _exp(row["estimate"])
        r["ci_low_transformed"] = _exp(row["ci_low"])
        r["ci_high_transformed"] = _exp(row["ci_high"])
        out.append(r)
    return out


def _interpretation(fit: dict, het: dict, measure: str, k: int) -> str:
    is_ratio = measure in RATIO_MEASURES
    est = _exp(fit["estimate"]) if is_ratio else fit["estimate"]
    lo = _exp(fit["ci_low"]) if is_ratio else fit["ci_low"]
    hi = _exp(fit["ci_high"]) if is_ratio else fit["ci_high"]
    null = 1.0 if is_ratio else 0.0
    crosses_null = lo <= null <= hi

    direction = "favours the intervention" if est < null else (
        "favours the control" if est > null else "shows no difference")
    if crosses_null:
        verdict = (f"The 95% confidence interval includes the null value "
                   f"({null:g}), so no statistically significant difference "
                   "was demonstrated")
    else:
        verdict = (f"The 95% confidence interval excludes the null value "
                   f"({null:g}), indicating a statistically significant "
                   "difference")

    i2_txt = (f" Heterogeneity was I^2 = {het['I2']:.1f}%"
              if het["I2"] is not None else "")
    return (
        f"Pooled {MEASURE_LABELS[measure]} across {k} studies: "
        f"{est:.3f} (95% CI {lo:.3f} to {hi:.3f}), p = {fit['p_value']:.4g}. "
        f"The point estimate {direction}. {verdict}.{i2_txt}. "
        "These numbers are computed deterministically and must be quoted "
        "verbatim; they must never be re-derived or rounded by a language "
        "model."
    )


def _methods_text(
    measure: str,
    kind: str,
    tau2_estimator: str,
    hksj: bool,
    k: int,
    n_corrected: int,
) -> str:
    """A paragraph suitable for the Methods section of the review."""
    parts = [
        f"Data were pooled for {k} studies using the "
        f"{MEASURE_LABELS[measure]}."
    ]
    if measure in RATIO_MEASURES:
        parts.append(
            "Effects were combined on the natural-log scale and "
            "back-transformed for presentation."
        )
    if n_corrected:
        parts.append(
            f"A continuity correction of {CONTINUITY_CORRECTION} was applied "
            f"to all cells of {n_corrected} table(s) containing a zero cell."
        )
    if kind == "fixed":
        parts.append("A fixed-effect inverse-variance model was used.")
    else:
        est_name = ("DerSimonian and Laird" if tau2_estimator == "DL"
                    else "restricted maximum likelihood (REML)")
        parts.append(
            f"A random-effects model was fitted with tau^2 estimated by "
            f"{est_name}."
        )
        if hksj:
            parts.append(
                "Confidence intervals use the Hartung-Knapp-Sidik-Jonkman "
                "adjustment with a t reference distribution."
            )
    parts.append(
        "Heterogeneity was quantified with Cochran's Q, I^2, H^2 and tau^2, "
        "and a 95% prediction interval was calculated."
    )
    parts.append(
        "Publication bias was assessed by Egger's regression test and Begg's "
        "rank correlation test "
        + (f"({k} studies)." if k >= MIN_K_FOR_BIAS_TESTS else
           f"only where at least {MIN_K_FOR_BIAS_TESTS} studies were "
           f"available; with k={k} these tests were not performed.")
    )
    parts.append(
        "Robustness was examined by leave-one-out sensitivity analysis. All "
        "computation was performed in Python (numpy/scipy)."
    )
    return " ".join(parts)
