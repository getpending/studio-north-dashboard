# Baseline: the original Studio North report

These files are the unmodified outputs of the completed Studio North lab run that this dashboard extends.
The dashboard never edits them; `dashboard.py render` reads them only to check that its December 2025 view
reproduces the report.

| File | What it is |
|---|---|
| `studio-north-report.pdf` | The executive report (report ID `SN-5BDD6FD6DCE24D29A3AF0EE9825343F5`) |
| `tables/cohort_valuation.csv` | 12-month contribution value, CAC and payback by joining cohort |
| `tables/cohort_valuation_by_segment.csv` | The same by cohort and channel-by-need segment |
| `tables/forecast_curve.csv` | Monthly retained members, net revenue and contribution, observed and forecast |
| `tables/cohort_totals.csv` | Retention and revenue triangle cells |
| `tables/cohort_cash_economics.csv` | Cumulative cash after acquisition cost |
| `tables/company_totals.csv` | Company-level monthly totals |
| `tables/channel_cac_current.csv` | Latest holdout-based incremental CAC by segment |
| `tables/channel_value_decision.csv` | The report's value-versus-iCAC decision table |

Provenance: Studio North release `0e40ce3` (dataset 5.1, data manifest SHA-256 `557d88a8…1e43`), model seed
20261116, 3,000-step NUTS budget, run locally on CPU. The report was produced through the lab's guided
19-checkpoint workflow.
