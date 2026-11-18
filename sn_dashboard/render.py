"""Assemble the cached as-of months into one self-contained HTML dashboard and a reconciliation report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .lab import BASELINE, CACHE, LOCK, SITE

SEGMENTS = ["search/build_skill", "partner/build_skill", "search/save_time", "partner/save_time"]
COLORS = {"search/build_skill": "#1b6e5a", "partner/build_skill": "#7a4ea3", "search/save_time": "#c9822b", "partner/save_time": "#b0413e"}
TEMPLATE = Path(__file__).with_name("template.html")


def load_months() -> list[dict]:
    paths = sorted((CACHE / "asof").glob("*.json"))
    if len(paths) != 24:
        raise SystemExit(f"Expected 24 cached months, found {len(paths)}. Run: uv run python dashboard.py build")
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def decision(month: dict) -> dict | None:
    """Latest cohort with six observed receipts versus each segment's latest completed holdout (the report's rule)."""
    tests = {t["segment"]: t for t in month["tests"] if t["icac"] is not None}
    eligible = sorted({s["cohort"] for s in month["segment_values"] if s["observed_months"] >= 6 and s["ltv"] is not None})
    if len(tests) < 4 or not eligible:
        return None
    bench = eligible[-1]
    values = {s["segment"]: s for s in month["segment_values"] if s["cohort"] == bench}
    rows = [{"segment": s, "value": values[s]["ltv"], "forecast_share": values[s]["forecast_share"], "icac": tests[s]["icac"],
             "lo": tests[s]["lo"], "hi": tests[s]["hi"], "test_month": tests[s]["test_month"],
             "margin": values[s]["ltv"] - tests[s]["icac"]} for s in SEGMENTS]
    m = {r["segment"]: r["margin"] for r in rows}
    return {"benchmark": bench, "rows": rows,
            "supported": m["search/build_skill"] > 0 and m["partner/build_skill"] > 0 and m["search/save_time"] < 0 and m["partner/save_time"] < 0,
            "build_leader": max(["search/build_skill", "partner/build_skill"], key=m.get)}


def _cmp(name, ours, theirs, tol):
    diff = np.abs(np.asarray(ours, float) - np.asarray(theirs, float))
    return {"check": name, "cells": int(diff.size), "max_abs_diff": float(diff.max()) if diff.size else None,
            "tolerance": tol, "match": bool(diff.size and diff.max() <= tol)}


def reconcile(final: dict) -> list[dict]:
    """The December 2025 view must reproduce the original report's saved tables."""
    t = lambda name: pd.read_csv(BASELINE / "tables" / name)
    out = []
    val = t("cohort_valuation.csv"); val["cohort"] = val.cohort_month.str[:7]
    ours = pd.DataFrame(final["cohort_values"]).set_index("cohort").loc[val.cohort]
    out.append(_cmp("Cohort CAC ($ per customer)", ours.cac, val.cac, 1e-6))
    out.append(_cmp("12-month contribution value, mean ($)", ours.ltv, val.ltv_before_cac_mean, 1e-6))
    out.append(_cmp("12-month value, 5th percentile ($)", ours.ltv_p05, val.ltv_before_cac_p05, 1e-6))
    out.append(_cmp("12-month value, 95th percentile ($)", ours.ltv_p95, val.ltv_before_cac_p95, 1e-6))
    out.append(_cmp("Payback receipt month", ours.payback_month, val.payback_month, 0))
    curve = t("forecast_curve.csv"); curve["cohort"] = curve.cohort_month.str[:7]
    rev = curve[curve.age_month < 12].groupby("cohort").net_revenue_mean.sum() / val.set_index("cohort").n_acquired
    out.append(_cmp("12-month net revenue per customer ($)", ours.revenue_12m, rev.loc[ours.index], 1e-6))
    tot = t("cohort_totals.csv"); tot["cohort"] = tot.cohort_month.str[:7]
    a, b = [], []
    for r in tot.itertuples():
        a += [final["retention"][r.cohort][r.age_month], final["revenue"][r.cohort][r.age_month]]
        b += [round(100 * r.retained_share, 2), round(r.revenue_per_acquired_customer, 2)]
    out.append(_cmp("Retention and revenue triangles (every observed cell)", a, b, 0.005))
    seg = t("cohort_valuation_by_segment.csv"); seg["key"] = seg.cohort_month.str[:7] + "|" + seg.channel + "/" + seg.primary_need
    ours_seg = {f"{s['cohort']}|{s['segment']}": s["ltv"] for s in final["segment_values"]}
    out.append(_cmp("Segment 12-month values (96 cells)", [ours_seg[k] for k in seg.key], seg.ltv_before_cac_mean, 1e-6))
    comp = t("company_totals.csv")
    ours_c = pd.DataFrame(final["company"])
    out.append(_cmp("Company monthly net revenue, contribution, spend", ours_c[["net_revenue", "contribution", "acquisition_spend"]].to_numpy().ravel(),
                    comp[["net_revenue", "contribution", "acquisition_spend"]].to_numpy().ravel(), 0.005))
    cur = t("channel_cac_current.csv"); cur["segment"] = cur.channel + "/" + cur.primary_need
    tests = {x["segment"]: x["icac"] for x in final["tests"]}
    out.append(_cmp("Current incremental CAC by segment", [tests[s] for s in cur.segment], cur.icac, 1e-6))
    return out


def forecast_track(months: list[dict]) -> pd.DataFrame:
    """How well each earlier month's forecast of 12-month value held up, for cohorts now fully observed."""
    final = {c["cohort"]: c for c in months[-1]["cohort_values"]}
    actual = {c: v["ltv"] for c, v in final.items() if v["observed_months"] >= 12}
    rows = []
    for m in months:
        for c in m["cohort_values"]:
            if c["cohort"] in actual and c["ltv"] is not None and c["observed_months"] < 12:
                rows.append({"as_of": m["month"], "cohort": c["cohort"], "observed_months": c["observed_months"],
                             "forecast": c["ltv"], "actual": actual[c["cohort"]],
                             "inside_band": c["ltv_p05"] <= actual[c["cohort"]] <= c["ltv_p95"]})
    df = pd.DataFrame(rows)
    df["pct_error"] = 100 * (df.forecast - df.actual) / df.actual
    return df


def answers(months, decisions, track) -> dict:
    final = months[-1]["cohort_values"]
    first = final[0]
    latest = [c for c in final if c["observed_months"] >= 6][-1]
    ret = months[-1]["retention"]
    sup = [m["month"] for m, d in zip(months, decisions) if d and d["supported"]]
    tested = [m["month"] for m, d in zip(months, decisions) if d]
    leaders = {m["month"]: d["build_leader"] for m, d in zip(months, decisions) if d}
    early = track[track.observed_months <= 3]
    late = track[track.observed_months >= 6]
    ratio = [c["ltv_to_cac"] for c in final]
    yr = lambda y: float(np.mean([c["ltv_to_cac"] for c in final if c["cohort"].startswith(y)]))
    return {
        "first": first, "latest": latest,
        "ret6_first": ret[first["cohort"]][5], "ret6_latest": ret[latest["cohort"]][5],
        "ratio_2024": yr("2024"), "ratio_2025": yr("2025"), "ratio_min": min(ratio), "ratio_min_cohort": final[int(np.argmin(ratio))]["cohort"],
        "supported_months": sup, "tested_months": tested, "first_supported": sup[0] if sup else None,
        "always_since": bool(sup) and sup == tested[tested.index(sup[0]):],
        "leaders": leaders,
        "mape_early": float(early.pct_error.abs().mean()), "mape_late": float(late.pct_error.abs().mean()),
        "bias_early": float(early.pct_error.mean()), "inside_band": float(track.inside_band.mean()),
    }


def _md(df, fmt="{:,.2f}"):
    cell = lambda v: (fmt.format(v) if isinstance(v, float) else str(v))
    return "\n".join(["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)] +
                     ["| " + " | ".join(cell(v) for v in r) + " |" for r in df.itertuples(index=False)])


def render() -> dict:
    months = load_months()
    decisions = [decision(m) for m in months]
    for m, d in zip(months, decisions):
        m["decision"] = d
    recon = reconcile(months[-1])
    track = forecast_track(months)
    ans = answers(months, decisions, track)
    check_path = CACHE / "check.json"
    check = json.loads(check_path.read_text(encoding="utf-8")) if check_path.exists() else None
    by_maturity = track.groupby("observed_months").agg(forecasts=("pct_error", "size"), mean_abs_pct_error=("pct_error", lambda s: s.abs().mean()),
                                                       mean_pct_error=("pct_error", "mean"), share_inside_5_95_band=("inside_band", "mean")).reset_index()
    meta = {"lock": LOCK, "reconciliation": recon, "check": check, "answers": ans,
            "track": by_maturity.to_dict(orient="records"), "colors": COLORS, "segments": SEGMENTS}
    html = (TEMPLATE.read_text(encoding="utf-8")
            .replace("__DATA__", json.dumps(months, separators=(",", ":")))
            .replace("__META__", json.dumps(meta, separators=(",", ":"), default=float)))
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(html, encoding="utf-8", newline="\n")

    recon_df = pd.DataFrame(recon)
    dec = pd.DataFrame([{"as-of month": m["month"], "benchmark cohort": d["benchmark"], **{s: next(r["margin"] for r in d["rows"] if r["segment"] == s) for s in SEGMENTS},
                         "build skill clears iCAC, save time does not": d["supported"], "wider build-skill margin": d["build_leader"]}
                        for m, d in zip(months, decisions) if d])
    fits = pd.DataFrame([{"as-of month": m["month"], "fit": m["fit"]["status"], "max R-hat": m["fit"].get("max_r_hat", ""),
                          "min ESS": m["fit"].get("min_ess", ""), "divergences": m["fit"].get("divergences", "")} for m in months])
    (Path(SITE.parent) / "reconciliation.md").write_text(f"""# Reconciliation and checks

Generated by `uv run python dashboard.py render`.

## The December 2025 view reproduces the original report

The last as-of month uses all observed records and the report's model with the same seed ({LOCK['model_seed']})
and step budget ({LOCK['model_steps']}). It is compared with the report's saved tables in `baseline/tables/`.

{_md(recon_df, "{:,.10g}")}

All checks match: **{all(r['match'] for r in recon)}**. Differences are at floating-point rounding level, because
the code, data, seed, settings and library versions are the same as the run that produced the report.

## Cut-off check

{"Month " + check["month"] + " rebuilt from scratch, from records cut off at that month: identical to the cached view: **" + str(check["identical"]) + "**." if check else "Not run. Use `uv run python dashboard.py check 2024-12`."}

## Model fit in every as-of month

{_md(fits, "{:,.4f}")}

January and February 2024 have too little renewal history for the report's model, so their forecasts are blank.

## How earlier forecasts held up

For cohorts with all twelve receipts observed by December 2025, the 12-month value each earlier month forecast:

{_md(by_maturity, "{:,.2f}")}

## Acquisition decision by month

Latest cohort with six observed receipts, valued at 12 months, minus each segment's latest completed holdout iCAC:

{_md(dec, "{:,.2f}")}
""", encoding="utf-8", newline="\n")
    return {"site": str(SITE / "index.html"), "reconciled": all(r["match"] for r in recon),
            "first_supported": ans["first_supported"], "mape_early": ans["mape_early"], "mape_late": ans["mape_late"],
            "leaders": ans["leaders"], "check": check}
