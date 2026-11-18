"""In-memory DuckDB with the release's own source loader and canonical views, cut off at an as-of date."""
from __future__ import annotations

import json

import duckdb

from .lab import LAB, importable

CUTOFF = "2026-01-01 00:00:00"

# Each source's own event date. Rows dated on or after the as-of cut-off did not exist yet.
CUT = {
    "transactions": "occurred_at < {ts}",
    "subscription_periods": "period_start < CAST({ts} AS DATE)",
    "product_events": "occurred_at < {ts}",
    "feedback": "submitted_at < {ts}",
    "campaign_spend": "spend_date < CAST({ts} AS DATE)",
    "channel_holdouts": "followup_end_at <= {ts}",   # only tests whose fixed follow-up window had finished
}


def connect(as_of: str = CUTOFF) -> duckdb.DuckDBPyConnection:
    """Load the eight frozen CSVs exactly as the lab does, optionally cut off, then build the canonical views.

    `as_of` is an exclusive timestamp: everything dated before it is visible, nothing after.
    People and attribution rows carry no outcome on their own; a person only enters an analysis once a
    payment dated before the cut-off makes them an acquired customer.
    """
    importable()
    from cohort_lab.analysis import _source_sql
    manifest = json.loads((LAB / "data" / "data_manifest.json").read_text(encoding="utf-8"))
    con = duckdb.connect()
    con.execute(_source_sql(LAB / "data", manifest))
    if as_of != CUTOFF:
        ts = f"TIMESTAMP '{as_of}'"
        con.execute(f"CREATE OR REPLACE VIEW lab_settings AS SELECT {ts} AS data_as_of")
        for name, condition in CUT.items():
            con.execute(f"CREATE OR REPLACE TABLE {name}__asof AS SELECT * FROM {name} WHERE {condition.format(ts=ts)}")
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {name}__asof")
    con.execute((LAB / "sql" / "01_views.sql").read_text(encoding="utf-8"))
    return con
