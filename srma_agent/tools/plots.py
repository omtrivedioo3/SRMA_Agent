"""Publication-quality meta-analysis figures, rendered headlessly.

Two plots are produced, both in the conventional Cochrane style so that a
reviewer can read them without a legend:

    forest_plot  study labels, effect squares sized by weight, confidence
                 whiskers, a pooled diamond, the no-effect line, and the
                 heterogeneity statistics printed on the figure.
    funnel_plot  effect against standard error with the y-axis inverted and
                 pseudo 95% confidence limits.

Both take the dict returned by `meta_analysis.run_meta_analysis`, so the
figures can never disagree with the numbers in the report: there is exactly
one computation and the plots merely draw it. Neither function computes a
statistic of its own.

The 'Agg' backend is selected before pyplot is imported, so nothing here
needs a display, an X server or a GUI toolkit.
"""

from __future__ import annotations

import math
import os

import matplotlib

matplotlib.use("Agg")  # must precede the pyplot import

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

__all__ = ["forest_plot", "funnel_plot"]

_COLOUR_SQUARE = "#2b6cb0"
_COLOUR_DIAMOND = "#1a365d"
_COLOUR_LINE = "#4a5568"
_COLOUR_GRID = "#cbd5e0"
_COLOUR_PRED = "#c05621"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _ensure_parent(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def _check(result: dict) -> None:
    if not isinstance(result, dict):
        raise TypeError("result must be the dict returned by run_meta_analysis")
    if not result.get("ok"):
        raise ValueError(
            "Cannot plot a failed analysis: "
            f"{result.get('error', 'run_meta_analysis returned ok=False')}"
        )
    if not result.get("studies"):
        raise ValueError("Cannot plot: the analysis included no studies.")


def _display_values(result: dict) -> tuple[str, float, bool]:
    """(axis label, null value, log-scale flag) for the current measure."""
    is_ratio = bool(result.get("is_ratio_measure"))
    label = result.get("effect_measure_label", result.get("effect_measure", ""))
    return label, (1.0 if is_ratio else 0.0), is_ratio


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def _fmt_ci(est: float, lo: float, hi: float, digits: int = 2) -> str:
    return f"{_fmt(est, digits)} [{_fmt(lo, digits)}, {_fmt(hi, digits)}]"


def _het_caption(result: dict) -> str:
    het = result.get("heterogeneity", {})
    q, df = het.get("Q"), het.get("df")
    p, i2 = het.get("p_value"), het.get("I2")
    tau2 = het.get("tau2")
    bits = []
    if tau2 is not None:
        bits.append(f"$\\tau^2$ = {tau2:.4f}")
    if q is not None and df is not None:
        p_txt = "< 0.0001" if (p is not None and p < 0.0001) else f"= {p:.3f}"
        bits.append(f"Q = {q:.2f}, df = {df}, p {p_txt}")
    if i2 is not None:
        bits.append(f"$I^2$ = {i2:.0f}%")
    text = "Heterogeneity: " + "; ".join(bits) if bits else ""
    pooled = result.get("pooled", {})
    stat_type = pooled.get("statistic_type", "z")
    stat, pval = pooled.get("statistic"), pooled.get("p_value")
    if stat is not None and pval is not None:
        p_txt = "< 0.0001" if pval < 0.0001 else f"= {pval:.3f}"
        text += (f"\nTest for overall effect: {stat_type} = {stat:.2f}, "
                 f"p {p_txt}")
    if i2 is not None and i2 > 50:
        text += ("\nI$^2$ > 50%: subgroup / sensitivity analysis required "
                 "before quoting a single summary effect.")
    return text


# --------------------------------------------------------------------------
# forest plot
# --------------------------------------------------------------------------


def forest_plot(
    result: dict,
    path: str,
    title: str | None = None,
    show_prediction_interval: bool = True,
    dpi: int = 150,
) -> str:
    """Draw a Cochrane-style forest plot and save it as a PNG.

    Args:
        result: The dict returned by `run_meta_analysis`.
        path: Destination PNG path. Parent directories are created.
        title: Figure title; a sensible one is generated if omitted.
        show_prediction_interval: Draw the 95% prediction interval as a bar
            through the diamond (random-effects analyses only).
        dpi: Output resolution.

    Returns:
        The absolute path of the file written.
    """
    _check(result)
    path = _ensure_parent(path)

    studies = result["studies"]
    pooled = result["pooled"]
    measure_label, null, log_scale = _display_values(result)
    key = "effect_transformed"
    k = len(studies)

    est = [s[key] for s in studies]
    lo = [s["ci_low_transformed"] for s in studies]
    hi = [s["ci_high_transformed"] for s in studies]
    is_random = bool(result.get("tau2_estimator") not in (None, "none"))
    weights = [
        s["weight_random_pct"] if is_random else s["weight_fixed_pct"]
        for s in studies
    ]

    p_est = pooled["estimate_transformed"]
    p_lo = pooled["ci_low_transformed"]
    p_hi = pooled["ci_high_transformed"]

    pi = result.get("prediction_interval", {})
    pi_lo = pi.get("low_transformed") if pi.get("available") else None
    pi_hi = pi.get("high_transformed") if pi.get("available") else None

    # ---- layout --------------------------------------------------------
    height = max(3.2, 0.42 * k + 3.0)
    fig = plt.figure(figsize=(11.5, height), dpi=dpi)
    grid = fig.add_gridspec(
        1, 3, width_ratios=[1.35, 1.75, 1.25], wspace=0.02,
        left=0.02, right=0.98, top=0.90, bottom=0.14,
    )
    ax_lbl = fig.add_subplot(grid[0, 0])
    ax = fig.add_subplot(grid[0, 1])
    ax_num = fig.add_subplot(grid[0, 2])

    y_pos = list(range(k, 0, -1))      # first study at the top
    y_pooled = -0.6
    y_pred = -1.5 if (pi_lo is not None and show_prediction_interval) else None

    # ---- axis limits ---------------------------------------------------
    finite = [x for x in (est + lo + hi + [p_est, p_lo, p_hi])
              if x is not None and math.isfinite(x)]
    if pi_lo is not None and math.isfinite(pi_lo):
        finite.append(pi_lo)
    if pi_hi is not None and math.isfinite(pi_hi):
        finite.append(pi_hi)
    x_min, x_max = min(finite), max(finite)

    if log_scale:
        x_min = max(min(x_min, null * 0.85), 1e-4)
        x_max = max(x_max, null * 1.18)
        pad = (math.log(x_max) - math.log(x_min)) * 0.12 or 0.3
        lim_lo, lim_hi = math.exp(math.log(x_min) - pad), math.exp(
            math.log(x_max) + pad)
        ax.set_xscale("log")
    else:
        x_min, x_max = min(x_min, null), max(x_max, null)
        pad = (x_max - x_min) * 0.12 or 1.0
        lim_lo, lim_hi = x_min - pad, x_max + pad

    # ---- study rows ----------------------------------------------------
    max_w = max(weights) if weights else 1.0
    for yi, e, l, h, w in zip(y_pos, est, lo, hi, weights):
        l_c, h_c = max(l, lim_lo), min(h, lim_hi)
        ax.plot([l_c, h_c], [yi, yi], color=_COLOUR_LINE, lw=1.3,
                solid_capstyle="butt", zorder=2)
        # whisker end caps
        for xc, clipped in ((l_c, l < lim_lo), (h_c, h > lim_hi)):
            if clipped:
                ax.plot(xc, yi, marker=("<" if xc == l_c else ">"),
                        color=_COLOUR_LINE, markersize=5, zorder=3)
            else:
                ax.plot([xc, xc], [yi - 0.16, yi + 0.16], color=_COLOUR_LINE,
                        lw=1.3, zorder=2)
        # square area proportional to weight
        size = 30.0 + 190.0 * (w / max_w if max_w > 0 else 1.0)
        ax.scatter([e], [yi], s=size, marker="s", color=_COLOUR_SQUARE,
                   zorder=4, edgecolors="white", linewidths=0.5)

    # ---- pooled diamond -------------------------------------------------
    half = 0.32
    ax.add_patch(Polygon(
        [[p_lo, y_pooled], [p_est, y_pooled + half],
         [p_hi, y_pooled], [p_est, y_pooled - half]],
        closed=True, facecolor=_COLOUR_DIAMOND, edgecolor=_COLOUR_DIAMOND,
        zorder=5,
    ))

    # ---- prediction interval -------------------------------------------
    if y_pred is not None:
        ax.plot([max(pi_lo, lim_lo), min(pi_hi, lim_hi)], [y_pred, y_pred],
                color=_COLOUR_PRED, lw=2.4, solid_capstyle="butt", zorder=5)
        for xc in (max(pi_lo, lim_lo), min(pi_hi, lim_hi)):
            ax.plot([xc, xc], [y_pred - 0.2, y_pred + 0.2],
                    color=_COLOUR_PRED, lw=2.0, zorder=5)

    # ---- reference lines -------------------------------------------------
    ax.axvline(null, color="black", lw=1.0, zorder=1)
    ax.axvline(p_est, color=_COLOUR_DIAMOND, lw=0.9, ls="--", alpha=0.6,
               zorder=1)
    ax.axhline(0.15, color=_COLOUR_GRID, lw=0.8)

    bottom = (y_pred if y_pred is not None else y_pooled) - 0.9
    ax.set_xlim(lim_lo, lim_hi)
    ax.set_ylim(bottom, k + 0.9)
    ax.set_yticks([])
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_COLOUR_LINE)
    ax.tick_params(axis="x", labelsize=8.5, colors="#2d3748")
    if log_scale:
        from matplotlib.ticker import FuncFormatter, LogLocator
        ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1, 2, 5)))
        ax.xaxis.set_minor_locator(LogLocator(base=10.0,
                                              subs=np.arange(2, 10) * 0.1))
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda v, _p: f"{v:g}" if v >= 0.01 else f"{v:.3f}"))
        ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_xlabel(f"{measure_label} (95% CI)", fontsize=9.5, labelpad=6)

    # directional hints under the axis
    ax.annotate("favours intervention", xy=(0.28, -0.085),
                xycoords="axes fraction", ha="center", fontsize=8,
                color="#4a5568")
    ax.annotate("favours control", xy=(0.72, -0.085),
                xycoords="axes fraction", ha="center", fontsize=8,
                color="#4a5568")

    # ---- text columns ---------------------------------------------------
    for axis in (ax_lbl, ax_num):
        axis.set_xlim(0, 1)
        axis.set_ylim(bottom, k + 0.9)
        axis.axis("off")

    ax_lbl.text(0.0, k + 0.55, "Study", fontsize=9.5, fontweight="bold",
                va="center")
    header_right = f"{result['effect_measure']} [95% CI]        Weight"
    ax_num.text(0.02, k + 0.55, header_right, fontsize=9.5,
                fontweight="bold", va="center")

    for yi, s, e, l, h, w in zip(y_pos, studies, est, lo, hi, weights):
        label = s["label"]
        if s.get("continuity_corrected"):
            label += " †"
        ax_lbl.text(0.0, yi, label, fontsize=8.8, va="center")
        raw = s.get("raw") or {}
        if raw.get("events_intervention") is not None:
            detail = (f"{raw['events_intervention']:.0f}/"
                      f"{raw['n_intervention']:.0f} vs "
                      f"{raw['events_control']:.0f}/"
                      f"{raw['n_control']:.0f}")
            ax_lbl.text(0.99, yi, detail, fontsize=7.6, va="center",
                        ha="right", color="#718096")
        ax_num.text(0.02, yi, _fmt_ci(e, l, h), fontsize=8.6, va="center")
        ax_num.text(0.99, yi, f"{w:.1f}%", fontsize=8.6, va="center",
                    ha="right", color="#4a5568")

    model_name = result.get("model", "pooled")
    ax_lbl.text(0.0, y_pooled, f"Pooled ({model_name})", fontsize=9.2,
                fontweight="bold", va="center")
    ax_num.text(0.02, y_pooled, _fmt_ci(p_est, p_lo, p_hi), fontsize=9.0,
                fontweight="bold", va="center")
    ax_num.text(0.99, y_pooled, "100.0%", fontsize=8.6, va="center",
                ha="right", color="#4a5568")
    if y_pred is not None:
        ax_lbl.text(0.0, y_pred, "95% prediction interval", fontsize=8.6,
                    va="center", color=_COLOUR_PRED)
        ax_num.text(0.02, y_pred, f"[{_fmt(pi_lo)}, {_fmt(pi_hi)}]",
                    fontsize=8.6, va="center", color=_COLOUR_PRED)

    # ---- heterogeneity block --------------------------------------------
    fig.text(0.02, 0.015, _het_caption(result), fontsize=8.2, va="bottom",
             color="#2d3748")
    if any(s.get("continuity_corrected") for s in studies):
        fig.text(0.98, 0.015,
                 "† continuity correction of 0.5 applied (zero cell)",
                 fontsize=7.5, va="bottom", ha="right", color="#718096")

    if title is None:
        title = (f"{result['effect_measure_label']} — "
                 f"{result['k_included']} studies")
        if result.get("k_excluded"):
            title += f" ({result['k_excluded']} excluded)"
    fig.suptitle(title, fontsize=12, fontweight="bold", x=0.02, ha="left",
                 y=0.975)

    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# funnel plot
# --------------------------------------------------------------------------


def funnel_plot(
    result: dict,
    path: str,
    title: str | None = None,
    annotate_labels: bool = False,
    dpi: int = 150,
) -> str:
    """Draw a funnel plot with pseudo 95% confidence limits and save a PNG.

    The x-axis is the effect estimate (log-scaled for ratio measures), the
    y-axis is the study standard error, inverted so the most precise studies
    sit at the top. The dashed triangle is the region within which 95% of
    studies would be expected to fall in the absence of bias and
    heterogeneity, given the pooled estimate.

    Args:
        result: The dict returned by `run_meta_analysis`.
        path: Destination PNG path. Parent directories are created.
        title: Figure title; generated if omitted.
        annotate_labels: Print study labels beside each point.
        dpi: Output resolution.

    Returns:
        The absolute path of the file written.
    """
    _check(result)
    path = _ensure_parent(path)

    studies = result["studies"]
    measure_label, null, log_scale = _display_values(result)

    # Work on the analysis scale (log for ratios), transform only for drawing.
    y_eff = np.array([s["effect"] for s in studies], dtype=float)
    se = np.array([s["se"] for s in studies], dtype=float)
    centre = float(result["pooled"]["estimate"])

    se_max = float(se.max()) * 1.10 if se.size else 1.0
    se_grid = np.linspace(0.0, se_max, 100)
    lo95 = centre - 1.959963984540054 * se_grid
    hi95 = centre + 1.959963984540054 * se_grid
    lo99 = centre - 2.5758293035489004 * se_grid
    hi99 = centre + 2.5758293035489004 * se_grid

    def to_x(values):
        return np.exp(values) if log_scale else values

    fig, ax = plt.subplots(figsize=(7.2, 6.4), dpi=dpi)

    ax.fill_betweenx(se_grid, to_x(lo99), to_x(hi99), color="#edf2f7",
                     zorder=0, label="pseudo 99% limits")
    ax.fill_betweenx(se_grid, to_x(lo95), to_x(hi95), color="#e2e8f0",
                     zorder=0)
    ax.plot(to_x(lo95), se_grid, ls="--", lw=1.0, color=_COLOUR_LINE, zorder=2)
    ax.plot(to_x(hi95), se_grid, ls="--", lw=1.0, color=_COLOUR_LINE, zorder=2,
            label="pseudo 95% confidence limits")
    ax.axvline(to_x(np.array([centre]))[0], color=_COLOUR_DIAMOND, lw=1.2,
               zorder=2, label="pooled estimate")
    ax.axvline(null, color="black", lw=0.9, ls=":", zorder=2,
               label="no effect")

    ax.scatter(to_x(y_eff), se, s=42, color=_COLOUR_SQUARE, alpha=0.85,
               edgecolors="white", linewidths=0.6, zorder=4)

    if annotate_labels:
        for s, xv, yv in zip(studies, to_x(y_eff), se):
            ax.annotate(s["label"], (xv, yv), fontsize=7,
                        textcoords="offset points", xytext=(6, 3),
                        color="#4a5568")

    if log_scale:
        ax.set_xscale("log")
        from matplotlib.ticker import FuncFormatter, LogLocator
        ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1, 2, 5)))
        ax.xaxis.set_major_formatter(FuncFormatter(
            lambda v, _p: f"{v:g}" if v >= 0.01 else f"{v:.3f}"))
        ax.xaxis.set_minor_formatter(plt.NullFormatter())

    ax.set_ylim(se_max, 0.0)                     # inverted: precise at top
    ax.set_xlabel(measure_label, fontsize=10)
    ax.set_ylabel("Standard error of the effect estimate", fontsize=10)
    ax.grid(alpha=0.25, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7.8, loc="lower left", framealpha=0.9)

    bias = result.get("publication_bias", {})
    egger = bias.get("egger", {})
    begg = bias.get("begg", {})
    if egger.get("performed"):
        caption = (f"Egger's test: intercept = {egger['intercept']:.3f}, "
                   f"t({egger['df']}) = {egger['t']:.2f}, "
                   f"p = {egger['p_value']:.3f}")
        if begg.get("performed"):
            caption += (f"\nBegg's test: Kendall's tau = "
                        f"{begg['kendall_tau']:.3f}, "
                        f"p = {begg['p_value']:.3f}")
    else:
        caption = ("Asymmetry tests not performed — "
                   + str(egger.get("reason", "")).split(".")[0] + ".")
    taf = bias.get("trim_and_fill", {})
    if taf.get("performed") and taf.get("n_missing_estimated"):
        # _fmt, not an f-string format spec: the adjusted estimate is None
        # when the value was non-finite, and "{None:.3f}" raises.
        adjusted = taf.get("adjusted_estimate_transformed")
        if adjusted is None:
            adjusted = taf.get("adjusted_estimate")
        caption += (f"\nTrim-and-fill: {taf['n_missing_estimated']} study/ies "
                    f"imputed on the {taf['side_imputed']}; adjusted estimate "
                    f"{_fmt(adjusted, 3)}")
    fig.text(0.01, 0.005, caption, fontsize=8, va="bottom", color="#2d3748")

    if title is None:
        title = (f"Funnel plot — {result['effect_measure_label']} "
                 f"({result['k_included']} studies)")
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left", pad=10)

    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
