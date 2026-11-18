# Studio North, replayed one month at a time

**Path A (FAQ 4): a month-by-month dashboard of Studio North's customer economics.**
MBA 743, Topic 5: Agentic AI Lab.

The managerial question is the report's: *are we moving in the right direction as a company?* The dashboard
lets you step from January 2024 to December 2025 and see only what Studio North could have known at the end
of each month: cohort retention, revenue, 12-month contribution value (LTV), CAC and payback, with observed
results kept visibly separate from forecasts.

**Open the dashboard: https://getpending.github.io/studio-north-dashboard/site/**

The same page is [`site/index.html`](site/index.html) in this repository: one self-contained file that also
works offline if you download it and open it in a browser.

## Findings

**Yes, Studio North is moving in the right direction, and the replay shows it building month by month.**

| | January 2024 cohort | July 2025 cohort |
|---|---|---|
| CAC per customer | $111 | $80 |
| Still paying at month 6 | 51% | 66% |
| 12-month contribution value | $167 (observed) | $244 (43% forecast) |
| Payback | receipt month 7 | receipt month 4 |

Value per dollar of CAC averages 1.87x for 2024 cohorts and 3.02x for 2025 cohorts. Stepping through the
months, the improvement arrives gradually from mid-2024 rather than in one jump, and company net revenue and
contribution rise steadily while acquisition spend stays roughly flat.

**When did the evidence first support the report's recommendation?** In **July 2025**, the first month with a
completed randomized holdout test. From then on, in every month, both build-skill segments cleared their
incremental acquisition cost and both save-time segments did not. Which build-skill channel had the wider
margin kept changing (partner in July, August, September and November; search in October and December), which
is why the report treats search and partner as roughly equal.

**How reliable were the forecasts along the way?** For the 13 cohorts that are now fully observed, the
forecast of 12-month value made after one observed month was off by 9% on average, after six months by 2.4%,
and after eleven months by 0.2%. Forecasts ran slightly low on average.

## What the dashboard shows

| Panel | Contents | Observed or forecast |
|---|---|---|
| Company at a glance | Members paying, net revenue and contribution in the as-of month; CAC and value of the newest cohorts | Observed, except value (labelled) |
| Company trajectory | Monthly net revenue, contribution and acquisition spend | Observed |
| 12-month value versus CAC | Per joining cohort: observed value (solid), forecast value (dashed), CAC (black line) | Both, drawn differently |
| Cohort economics | CAC, value so far, 12-month value with 5-95% band, forecast share, value/CAC, 12-month net revenue, payback month | Forecast figures in purple italic; payback marked observed or forecast |
| Retention triangle | % of each joining cohort still paying, by month since joining | Observed; future months blank, not zero |
| Revenue triangle | Net revenue per originally acquired customer, by month since joining | Observed |
| Channel-by-need mix | Who joined each month | Observed |
| Acquisition decision check | Latest cohort with six observed months, valued at 12 months, minus each segment's latest holdout iCAC | Forecast value, observed tests |
| How earlier forecasts held up | Each month's forecast of now-complete cohorts versus what happened | Backtest |
| Reconciliation and checks | December 2025 view versus the original report; cut-off check | Checks |

Definitions are the report's: a customer is acquired at their first positive payment; retention and revenue
are divided by the original customers acquired; value is twelve monthly receipts of contribution (net revenue
minus variable cost) discounted 1% a month, before CAC; CAC is all acquisition spend in the joining month
divided by customers acquired; payback is the receipt month in which cumulative undiscounted contribution
covers that spend; iCAC comes from randomized holdout tests.

## How each month is built

For every as-of month M:

1. **Cut off the data.** Records dated after the end of M are removed from the eight frozen source files:
   payments and refunds, subscription periods, product events, feedback and campaign spend by their own
   dates, and holdout tests unless their fixed follow-up window had ended. (`sn_dashboard/sources.py`)
2. **Re-run the report's SQL.** The release's own source loader and `sql/01_views.sql` rebuild the cohort
   tables on the cut-off data. Observed figures come straight from these views.
3. **Refit the report's model.** The release's hierarchical shifted-beta-geometric retention and Gamma revenue
   model (`cohort_lab/model.py`) is refitted on M's data alone, with the report's seed (20261116) and step
   budget (3,000). Forecasts extend each cohort to twelve receipts exactly as the report does.
   No parameter fitted on later data is ever reused. (`sn_dashboard/asof.py`)
4. **Too little history:** January and February 2024 have no usable renewal history, so the model refuses to
   fit and those months show no forecasts.

The dashboard uses the Studio North code and data unchanged; this repository adds only the cut-off, the
month loop and the presentation.

## Checks

- **Reconciliation to the report:** the December 2025 view uses all records and must equal the report.
  `dashboard.py render` compares it with the report's saved tables in `baseline/` (CAC, value and its band,
  payback, net revenue, every triangle cell, all 96 segment values, company totals and iCAC). Results are in
  [`reconciliation.md`](reconciliation.md).
- **Cut-off check:** `dashboard.py check 2024-12` rebuilds December 2024 from scratch and confirms the view
  does not change.
- **Forecast backtest:** for cohorts now fully observed, each earlier month's forecast is compared with what
  happened (bottom of the dashboard and `reconciliation.md`).

## Run it

Requires [uv](https://docs.astral.sh/uv/) and an internet connection the first time. No GPU.

```text
uv sync --frozen
uv run python dashboard.py all
```

`all` runs four steps, which can also be run one at a time:

| Command | What it does | Time |
|---|---|---|
| `uv run python dashboard.py fetch` | Downloads the Studio North release at the pinned commit into `lab/` and verifies every data file's hash | under a minute |
| `uv run python dashboard.py build` | Builds all 24 as-of months, refitting the model each month; results cached in `cache/` | about 15-25 minutes on a laptop CPU |
| `uv run python dashboard.py check 2024-12` | Cut-off check for one month | under a minute |
| `uv run python dashboard.py render` | Writes `site/index.html` and `reconciliation.md` | seconds |

Dependencies are pinned in `pyproject.toml` and locked in `uv.lock` to the same versions as the Studio North
release, which is what lets the final month reproduce the report to floating-point precision.

If the pinned commit ever becomes unavailable, point `fetch` at a local copy of the release:
`uv run python dashboard.py fetch --from-path /path/to/customer-economics-lab`. The data hashes are verified
either way.

## Repository layout

```text
dashboard.py             command-line entry point
sn_dashboard/
  lab.py                 fetch and verify the pinned Studio North release
  sources.py             load the frozen data with the release's SQL, cut off at an as-of date
  asof.py                one month: observed tables plus the refitted forecast
  render.py              assemble the dashboard, reconciliation and backtest
  template.html          dashboard page (data is inlined at render time)
baseline/                the original report PDF and its saved tables (unchanged)
site/index.html          the built dashboard
reconciliation.md        reconciliation, cut-off check, fit diagnostics and decision table by month
lab.lock.json            pinned release, data hash, seed and step budget
```

## Source and limits

- Studio North code and synthetic data: [longxiutian/customer-economics-lab](https://github.com/longxiutian/customer-economics-lab)
  (MIT licence), pinned in `lab.lock.json`. The baseline report was produced from commit `0e40ce3`, which is
  no longer on GitHub; the pinned commit has byte-identical data, SQL, model code and locked dependencies,
  and the reconciliation confirms the result.
- Forecast bands cover model-parameter uncertainty only, as in the report, so actual outcomes often fall
  outside them.
- Each month's view is what the data available then would show. It is not a record of what management
  actually knew or decided at the time.
