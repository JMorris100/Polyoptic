#!/usr/bin/env python3
"""
Polyoptic ingest.

Reads ingest/series.yaml, fetches each series from its source, normalises it
into the series-first schema, and writes data/bundle.json for the front end.

Design notes
------------
* One series = one object. Topics are tags, not folders. A series belongs to
  Housing AND Economy without being duplicated.
* Reference series (population, GDP deflator, GDP) live once, centrally, and
  power the per-person / real-terms / %-of-GDP transforms.
* Nothing is computed at ingest time that could be computed in the browser.
  Store what was published; derive the rest on demand.
* Every series carries geography, year_basis, unit and licence. The front end
  refuses to silently compare across mismatches.

Run:
    pip install -r ingest/requirements.txt
    python ingest/ingest.py            # all series
    python ingest/ingest.py --only hpe # one series
    python ingest/ingest.py --dry-run  # fetch and validate, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ingest" / "series.yaml"
OUT = ROOT / "data" / "bundle.json"
CACHE = ROOT / "ingest" / ".cache"

UA = {"User-Agent": "polyoptic-ingest/0.1 (+https://polyoptic.co)"}
TIMEOUT = 45


# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────

@dataclass
class Series:
    id: str
    name: str
    topics: list[str]
    unit: str
    geography: str
    year_basis: str            # calendar | financial | academic
    source: str
    source_url: str
    licence: str
    kind: str                  # money_cash | money_real | count | rate | ratio | index
    start: int
    values: list[float | None]
    discontinuities: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fetched: str = ""

    def validate(self) -> None:
        if self.year_basis not in {"calendar", "financial", "academic"}:
            raise ValueError(f"{self.id}: bad year_basis {self.year_basis!r}")
        if self.kind not in {"money_cash", "money_real", "count", "rate", "ratio", "index"}:
            raise ValueError(f"{self.id}: bad kind {self.kind!r}")
        if not self.values:
            raise ValueError(f"{self.id}: no observations")
        real = [v for v in self.values if v is not None]
        if len(real) < 3:
            raise ValueError(f"{self.id}: only {len(real)} usable observations")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def get(url: str, params: dict | None = None) -> requests.Response:
    CACHE.mkdir(exist_ok=True)
    r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def to_year(label: str, basis: str) -> int | None:
    """
    Collapse a period label to a single calendar year for plotting.

    Financial ('2023-24') and academic ('2023/24') years are plotted at their
    STARTING calendar year. This is a real decision with real consequences —
    a 2023/24 academic figure sits at 2023 even though most of it happened in
    2024. The front end surfaces this whenever bases are mixed on one chart.
    """
    label = str(label).strip()
    for sep in ("-", "/", " to "):
        if sep in label:
            head = label.split(sep)[0].strip()
            if head.isdigit() and len(head) == 4:
                return int(head)
    if len(label) >= 4 and label[:4].isdigit():
        return int(label[:4])
    return None


def to_annual(pairs: list[tuple[int, float]], how: str = "mean") -> dict[int, float]:
    """Collapse sub-annual observations to one value per year."""
    buckets: dict[int, list[float]] = {}
    for year, value in pairs:
        buckets.setdefault(year, []).append(value)
    if how == "last":
        return {y: v[-1] for y, v in buckets.items()}
    if how == "sum":
        return {y: sum(v) for y, v in buckets.items()}
    return {y: sum(v) / len(v) for y, v in buckets.items()}


def densify(by_year: dict[int, float]) -> tuple[int, list[float | None]]:
    """Turn a sparse year->value map into (start, [values]) with None for gaps."""
    if not by_year:
        return 0, []
    lo, hi = min(by_year), max(by_year)
    return lo, [by_year.get(y) for y in range(lo, hi + 1)]


# ─────────────────────────────────────────────────────────────
# Adapters
# ─────────────────────────────────────────────────────────────

def fetch_ons_timeseries(cfg: dict) -> dict[int, float]:
    """
    ONS website time-series JSON.

        https://www.ons.gov.uk/<path>/timeseries/<cdid>/<dataset>/data

    This is the pragmatic route for headline economic series — one request,
    everything in it. The trade-off is that the URL encodes the site's own
    taxonomy, so if ONS reorganises a page the URL moves. Pin the CDID in
    config and expect to fix paths occasionally.
    """
    url = f"https://www.ons.gov.uk/{cfg['path'].strip('/')}/timeseries/{cfg['cdid'].lower()}/{cfg['dataset'].lower()}/data"
    payload = get(url).json()

    granularity = cfg.get("granularity", "years")
    rows = payload.get(granularity) or payload.get("years") or []
    pairs: list[tuple[int, float]] = []
    for row in rows:
        year = to_year(row.get("year") or row.get("date", ""), "calendar")
        raw = row.get("value")
        if year is None or raw in (None, "", ".."):
            continue
        try:
            pairs.append((year, float(str(raw).replace(",", ""))))
        except ValueError:
            continue
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_ons_beta(cfg: dict) -> dict[int, float]:
    """
    ONS Beta API — https://api.beta.ons.gov.uk/v1

    Open, no key required. Structure is datasets -> editions -> versions ->
    observations, where you pin every dimension except one wildcard.

        /v1/datasets/{id}/editions/{edition}/versions/{v}/observations
            ?time=*&geography=K02000001&aggregate=...

    Richer and more stable than the website endpoint, but you have to know the
    dimension names for each dataset. `latest` resolves the version for you.
    """
    base = "https://api.beta.ons.gov.uk/v1"
    dataset, edition = cfg["dataset"], cfg.get("edition", "time-series")

    version = cfg.get("version")
    if version in (None, "latest"):
        meta = get(f"{base}/datasets/{dataset}").json()
        latest = meta.get("links", {}).get("latest_version", {})
        version = latest.get("id") or str(latest.get("href", "")).rstrip("/").split("/")[-1]

    params = {"time": "*", **cfg.get("dimensions", {})}
    payload = get(
        f"{base}/datasets/{dataset}/editions/{edition}/versions/{version}/observations",
        params=params,
    ).json()

    pairs: list[tuple[int, float]] = []
    for obs in payload.get("observations", []):
        label = (obs.get("dimensions", {}).get("time", {}) or {}).get("id") \
             or (obs.get("dimensions", {}).get("Time", {}) or {}).get("id", "")
        year = to_year(label, "calendar")
        try:
            value = float(obs["observation"])
        except (KeyError, TypeError, ValueError):
            continue
        if year is not None:
            pairs.append((year, value))
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_dfe_ees(cfg: dict) -> dict[int, float]:
    """
    DfE Explore Education Statistics API.

        https://api.education.gov.uk/statistics/v1/data-sets/{id}/query

    POST with a JSON query is the supported production route; GET exists for
    exploration but can't express conditions. Note that not every dataset in
    the EES catalogue is exposed through the API — some are CSV-only, which is
    why `csv` below exists as a fallback source type.
    """
    base = "https://api.education.gov.uk/statistics/v1"
    body = {
        "criteria": cfg.get("criteria", {}),
        "indicators": [cfg["indicator"]],
        "page": 1,
        "pageSize": 10000,
    }
    r = requests.post(
        f"{base}/data-sets/{cfg['data_set_id']}/query",
        json=body, headers={**UA, "Content-Type": "application/json"}, timeout=TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json()

    pairs: list[tuple[int, float]] = []
    for row in payload.get("results", []):
        period = row.get("timePeriod", {})
        year = to_year(str(period.get("period", "")), "academic")
        raw = (row.get("values") or {}).get(cfg["indicator"])
        if year is None or raw in (None, "", "z", "x", "c"):
            continue
        try:
            pairs.append((year, float(str(raw).replace(",", ""))))
        except ValueError:
            continue
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_csv(cfg: dict) -> dict[int, float]:
    """
    Generic CSV fallback — MHCLG live tables, OBR databases, anything published
    as a file rather than an API. Give it a URL, a year column and a value
    column. Unglamorous, and you'll use it more than you expect.
    """
    import csv
    import io

    text = get(cfg["url"]).text
    reader = csv.DictReader(io.StringIO(text))
    pairs: list[tuple[int, float]] = []
    for row in reader:
        for key, want in (cfg.get("filter") or {}).items():
            if str(row.get(key, "")).strip() != str(want):
                break
        else:
            year = to_year(row.get(cfg["year_column"], ""), cfg.get("year_basis", "calendar"))
            raw = row.get(cfg["value_column"], "")
            if year is None or raw in (None, "", ".."):
                continue
            try:
                pairs.append((year, float(str(raw).replace(",", "").replace("£", ""))))
            except ValueError:
                continue
    return to_annual(pairs, cfg.get("aggregate", "mean"))


ADAPTERS = {
    "ons_timeseries": fetch_ons_timeseries,
    "ons_beta": fetch_ons_beta,
    "dfe_ees": fetch_dfe_ees,
    "csv": fetch_csv,
}


# ─────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────

def build_series(spec: dict) -> Series:
    adapter = ADAPTERS[spec["source_type"]]
    by_year = adapter(spec["fetch"])
    start, values = densify(by_year)
    s = Series(
        id=spec["id"], name=spec["name"], topics=spec["topics"], unit=spec["unit"],
        geography=spec["geography"], year_basis=spec["year_basis"],
        source=spec["source"], source_url=spec.get("source_url", ""),
        licence=spec.get("licence", "OGL v3.0"), kind=spec["kind"],
        start=start, values=values,
        discontinuities=spec.get("discontinuities", []),
        notes=spec.get("notes", []),
        fetched=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    s.validate()
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="build a single series by id")
    ap.add_argument("--dry-run", action="store_true", help="fetch and validate, write nothing")
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG.read_text())
    specs = config["series"]
    if args.only:
        specs = [s for s in specs if s["id"] == args.only]
        if not specs:
            print(f"no series with id {args.only!r}", file=sys.stderr)
            return 1

    built, failed = [], []
    for spec in specs:
        try:
            s = build_series(spec)
            built.append(s)
            span = f"{s.start}–{s.start + len(s.values) - 1}"
            print(f"  ok   {s.id:<16} {span}  {len([v for v in s.values if v is not None]):>4} obs")
        except Exception as exc:                      # noqa: BLE001 — report and continue
            failed.append((spec["id"], exc))
            print(f"  FAIL {spec['id']:<16} {type(exc).__name__}: {exc}", file=sys.stderr)

    refs = {}
    for name, spec in config.get("references", {}).items():
        try:
            start, values = densify(ADAPTERS[spec["source_type"]](spec["fetch"]))
            refs[name] = {"start": start, "values": values}
            print(f"  ok   ref:{name}")
        except Exception as exc:                      # noqa: BLE001
            print(f"  FAIL ref:{name} — {exc}", file=sys.stderr)
            print("       transforms depending on this reference will be unavailable", file=sys.stderr)

    bundle = {
        "meta": {
            "provenance": "live" if not failed else "partial",
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "failed": [fid for fid, _ in failed],
        },
        "eras": config["eras"],
        "pms": config["pms"],
        "refs": refs,
        "series": [asdict(s) for s in built],
    }

    if args.dry_run:
        print(f"\ndry run: {len(built)} built, {len(failed)} failed, nothing written")
        return 1 if failed else 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, separators=(",", ":")))
    size = OUT.stat().st_size / 1024
    print(f"\nwrote {OUT.relative_to(ROOT)} — {len(built)} series, {size:.0f} KB")
    if failed:
        print(f"{len(failed)} failed; bundle marked 'partial'", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
