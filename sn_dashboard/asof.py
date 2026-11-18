"""What Studio North could have known at the end of one month.

Observed results come from the release's canonical SQL run on records cut off at that month's end.
Forecasts come from the release's own model (cohort_lab.model), refitted with the report's seed and step
budget on that cut-off data only. No parameter fitted on later data is ever reused.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .lab import SEED, STEPS, importable
from .sources import connect

MONTHS = [str(p) for p in pd.period_range("2024-01", "2025-12", freq="M")]


def _iso(frame, cols):
    for c in cols:
        frame[c] = pd.to_datetime(frame[c]).dt.strftime("%Y-%m-%d")
    return frame


def _num(frame, cols):
    for c in cols:
        frame[c] = frame[c].astype(float)
    return frame


def _q(x, p):
    return float(np.quantile(x, p))


def build(month: str) -> dict:
    importable()
    from cohort_lab import model as M

    as_of = (pd.Period(month, "M") + 1).to_timestamp().strftime("%Y-%m-%d 00:00:00")
    con = connect(as_of)
    frame = _iso(con.execute("SELECT * FROM cohort_age_summary ORDER BY cohort_month, channel, primary_need, age_month").df(), ["cohort_month", "calendar_month"])
    frame = M._validate(_num(frame, ["gross_payment_revenue", "net_revenue", "variable_cost", "contribution"]))
    costs = _num(_iso(con.execute("SELECT * FROM cohort_acquisition_costs").df(), ["cohort_month"]), ["acquisition_spend", "cac"])
    company_costs = _num(_iso(con.execute("SELECT * FROM cohort_cash_economics WHERE age_month = 0").df(), ["cohort_month"]), ["acquisition_spend"]).set_index("cohort_month")
    totals = _iso(con.execute("SELECT * FROM cohort_totals ORDER BY cohort_month, age_month").df(), ["cohort_month"])
    cash = _iso(con.execute("SELECT cohort_month, age_month, balance_per_customer::DOUBLE AS balance FROM cohort_cash_economics ORDER BY 1, 2").df(), ["cohort_month"])
    company = con.execute("""SELECT strftime(calendar_month, '%Y-%m') AS month, n_retained, net_revenue::DOUBLE AS net_revenue,
                                    contribution::DOUBLE AS contribution, acquisition_spend::DOUBLE AS acquisition_spend
                             FROM company_totals ORDER BY calendar_month""").df()
    tests = con.execute("""SELECT channel, primary_need, strftime(test_month, '%Y-%m') AS test_month,
                                  icac, icac_ci_lower, icac_ci_upper FROM channel_cac_current""").df()
    nan = lambda v: None if pd.isna(v) else float(v)
    result = {
        "month": month, "as_of_exclusive": as_of, "cohorts": sorted(frame.cohort_month.str[:7].unique()),
        "retention": {c[:7]: [round(100 * float(x), 2) for x in g.retained_share] for c, g in totals.groupby("cohort_month")},
        "revenue": {c[:7]: [round(float(x), 2) for x in g.revenue_per_acquired_customer] for c, g in totals.groupby("cohort_month")},
        "cash": {c[:7]: [round(float(x), 2) for x in g.sort_values("age_month").balance] for c, g in cash.groupby("cohort_month")},
        "mix": {c[:7]: {f"{r.channel}/{r.primary_need}": int(r.n_acquired) for r in g[g.age_month == 0].itertuples()} for c, g in frame.groupby("cohort_month")},
        "company": [{"month": r.month, "members": int(r.n_retained), "net_revenue": float(r.net_revenue),
                     "contribution": float(r.contribution), "acquisition_spend": float(r.acquisition_spend)} for r in company.itertuples()],
        "tests": [{"segment": f"{r.channel}/{r.primary_need}", "test_month": r.test_month, "icac": nan(r.icac),
                   "lo": nan(r.icac_ci_lower), "hi": nan(r.icac_ci_upper)} for r in tests.itertuples()],
        "fit": None, "cohort_values": [], "segment_values": [],
    }
    try:
        started = time.time()
        draws, diag = M._posterior(frame, SEED, STEPS)
    except ValueError as exc:            # the release model refuses too little history
        draws = None
        result["fit"] = {"status": "not fitted", "reason": str(exc)}
    else:
        result["fit"] = {"status": "fitted", "seconds": round(time.time() - started, 1), "max_r_hat": diag["max_r_hat"],
                         "min_ess": diag["min_ess"], "divergences": diag["divergences"],
                         "n_retention_cells": diag["n_retention_cells"], "n_revenue_cells": diag["n_revenue_cells"]}

    H, D = M.HORIZON, M.DRAWS
    cost_map = costs.set_index(M.KEYS)
    agg = {}
    for key, g in frame.groupby(M.KEYS, sort=True):
        g = g.sort_values("age_month")
        n0, obs_len = int(g.n_acquired.iloc[0]), min(len(g), M.HORIZON)
        revenue, contribution = np.zeros((D, H)), np.zeros((D, H))
        revenue[:, :obs_len] = g.net_revenue.to_numpy(float)[:obs_len]
        contribution[:, :obs_len] = g.contribution.to_numpy(float)[:obs_len]
        complete = obs_len == H
        if not complete and draws is not None:           # same forecast path as cohort_lab.model.fit_and_forecast
            ages = list(range(obs_len, H))
            _, gross = M._future(draws, g.iloc[-1], ages, float(g.n_retained.iloc[-1]))
            net_ratio, contribution_ratio = M._economic_ratios(frame, g.iloc[-1], ages)
            revenue[:, obs_len:] = gross * net_ratio
            contribution[:, obs_len:] = gross * contribution_ratio
            complete = True
        spend = float(cost_map.loc[key].acquisition_spend) if key in cost_map.index and pd.notna(cost_map.loc[key].acquisition_spend) else 0.0
        observed = np.arange(H) < obs_len
        rec = M._valuation_record(key, n0, spend, obs_len, contribution, observed)
        obs_cum = np.cumsum(g.contribution.to_numpy(float)[:obs_len]) - spend
        result["segment_values"].append({
            "cohort": key[0][:7], "segment": f"{key[1]}/{key[2]}", "n": n0, "cac": spend / n0, "observed_months": obs_len,
            "ltv": rec["ltv_before_cac_mean"] if complete else None, "forecast_share": rec["forecast_share"] if complete else None,
            "observed_value": rec["observed_discounted_contribution_per_customer"]})
        a = agg.setdefault(key[0], {"n": 0, "revenue": np.zeros((D, H)), "contribution": np.zeros((D, H)), "obs": obs_len, "complete": True})
        a["n"] += n0; a["revenue"] += revenue; a["contribution"] += contribution; a["complete"] &= complete

    for cohort, a in sorted(agg.items()):
        spend = float(company_costs.loc[cohort, "acquisition_spend"])   # whole-cohort ledger, as the report uses
        observed = np.arange(H) < a["obs"]
        rec = M._valuation_record((cohort,), a["n"], spend, a["obs"], a["contribution"], observed)
        complete, n = a["complete"], a["n"]
        observed_cum = np.cumsum(a["contribution"][0, : a["obs"]]) - spend
        rev = a["revenue"].sum(axis=1) / n
        result["cohort_values"].append({
            "cohort": cohort[:7], "n": n, "cac": spend / n, "observed_months": a["obs"],
            "observed_value": rec["observed_discounted_contribution_per_customer"],
            "observed_revenue": float(a["revenue"][0, : a["obs"]].sum() / n),
            "ltv": rec["ltv_before_cac_mean"] if complete else None,
            "ltv_p05": rec["ltv_before_cac_p05"] if complete else None,
            "ltv_p95": rec["ltv_before_cac_p95"] if complete else None,
            "net_ltv": rec["net_ltv_mean"] if complete else None,
            "ltv_to_cac": rec["ltv_to_cac_mean"] if complete else None,
            "forecast_share": rec["forecast_share"] if complete else None,
            "revenue_12m": float(rev.mean()) if complete else None,
            "revenue_12m_p05": _q(rev, .05) if complete else None, "revenue_12m_p95": _q(rev, .95) if complete else None,
            "payback_month": rec["payback_month"] if complete else (int(np.argmax(observed_cum >= 0) + 1) if (observed_cum >= 0).any() else None),
            "payback_status": rec["payback_status"] if complete else ("observed" if (observed_cum >= 0).any() else "not yet observed"),
        })
    return result
