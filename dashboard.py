"""Studio North month-by-month dashboard.

  uv run python dashboard.py fetch            download and verify the pinned Studio North release into ./lab
  uv run python dashboard.py build            rebuild every as-of month (Jan 2024 - Dec 2025); cached in ./cache
  uv run python dashboard.py check 2024-12    rebuild one month from scratch and confirm it matches the cache
  uv run python dashboard.py render           write site/index.html and reconciliation.md
  uv run python dashboard.py all              fetch, build, check, render
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from sn_dashboard.lab import CACHE, fetch


def build(only=None, force=False):
    from sn_dashboard.asof import MONTHS, build as build_month
    (CACHE / "asof").mkdir(parents=True, exist_ok=True)
    for month in ([only] if only else MONTHS):
        path = CACHE / "asof" / f"{month}.json"
        if path.exists() and not force:
            continue
        started = time.time()
        result = build_month(month)
        path.write_text(json.dumps(result), encoding="utf-8")
        fit = result["fit"]
        status = fit["status"] if fit["status"] != "fitted" else f"fitted (R-hat {fit['max_r_hat']:.4f}, {fit['divergences']} divergences)"
        print(f"{month}: {status}, {time.time() - started:.0f} s", flush=True)


def check(month):
    """The cut-off test from FAQ 4: an independent rebuild of one month must reproduce the dashboard's view."""
    from sn_dashboard.asof import build as build_month
    cached = json.loads((CACHE / "asof" / f"{month}.json").read_text(encoding="utf-8"))
    fresh = build_month(month)
    for item in (cached, fresh):
        if item["fit"]:
            item["fit"].pop("seconds", None)
    same = json.loads(json.dumps(fresh)) == cached
    result = {"month": month, "identical": same}
    (CACHE / "check.json").write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result))
    if not same:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    fp = sub.add_parser("fetch"); fp.add_argument("--force", action="store_true")
    fp.add_argument("--from-path", help="copy a local Studio North checkout instead of downloading")
    b = sub.add_parser("build"); b.add_argument("--only"); b.add_argument("--force", action="store_true")
    sub.add_parser("check").add_argument("month", nargs="?", default="2024-12")
    sub.add_parser("render")
    sub.add_parser("all")
    args = parser.parse_args()
    if args.command in ("fetch", "all"):
        print(json.dumps(fetch(getattr(args, "force", False), getattr(args, "from_path", None)), indent=2))
    if args.command in ("build", "all"):
        build(getattr(args, "only", None), getattr(args, "force", False))
    if args.command in ("check", "all"):
        check(getattr(args, "month", "2024-12"))
    if args.command in ("render", "all"):
        from sn_dashboard.render import render
        print(json.dumps(render(), indent=2))


if __name__ == "__main__":
    main()
