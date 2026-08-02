#!/usr/bin/env python3
"""
Polyoptic ingest.

Reads ingest/series.yaml, fetches each series from its publisher, normalises
everything to annual observations keyed by calendar year, and writes
data/bundle.json — the single file explore.html loads at runtime.

    python ingest/ingest.py --dry-run      # fetch and report, write nothing
    python ingest/ingest.py                # write data/bundle.json
    python ingest/ingest.py --only hpi,awe # work on a couple of series

Expect failures on the first run. Every `source.id` in series.yaml is marked
TODO or is unverified; identifiers move, datasets get renamed, and the ONS
website taxonomy occasionally reorganises underneath the timeseries URLs.
Work through them one at a time with --only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from statistics import mean

import requests
import yaml

ROOT    = Path(__file__).resolve().parent.parent
CONFIG  = ROOT / "ingest" / "series.yaml"
OUT     = ROOT / "data" / "bundle.json"
TIMEOUT = 45
UA      = {"User-Agent": "polyoptic-ingest/1.0 (+https://polyoptic.co)"}

# Areas the bundle carries. Must stay in step with the AREAS table in
# explore.html — the map's hex layout is driven by col/row here.
AREAS = [
    {"code":"UK",  "name":"United Kingdom",           "short":"UK",    "lvl":0, "col":None,"row":None,"parent":None},
    {"code":"ENG", "name":"England",                  "short":"Eng",   "lvl":1, "col":1, "row":1, "parent":"UK"},
    {"code":"SCT", "name":"Scotland",                 "short":"Sco",   "lvl":1, "col":1, "row":0, "parent":"UK"},
    {"code":"WLS", "name":"Wales",                    "short":"Wal",   "lvl":1, "col":0, "row":1, "parent":"UK"},
    {"code":"NIR", "name":"Northern Ireland",         "short":"NI",    "lvl":1, "col":0, "row":0, "parent":"UK"},
    {"code":"UKC", "name":"North East",               "short":"NE",    "lvl":2, "col":2, "row":1, "parent":"ENG"},
    {"code":"UKD", "name":"North West",               "short":"NW",    "lvl":2, "col":1, "row":2, "parent":"ENG"},
    {"code":"UKE", "name":"Yorkshire and The Humber", "short":"Y&H",   "lvl":2, "col":2, "row":2, "parent":"ENG"},
    {"code":"UKF", "name":"East Midlands",            "short":"E Mid", "lvl":2, "col":3, "row":3, "parent":"ENG"},
    {"code":"UKG", "name":"West Midlands",            "short":"W Mid", "lvl":2, "col":2, "row":3, "parent":"ENG"},
    {"code":"UKH", "name":"East of England",          "short":"East",  "lvl":2, "col":4, "row":3, "parent":"ENG"},
    {"code":"UKI", "name":"London",                   "short":"Ldn",   "lvl":2, "col":3, "row":4, "parent":"ENG"},
    {"code":"UKJ", "name":"South East",               "short":"SE",    "lvl":2, "col":2, "row":4, "parent":"ENG"},
    {"code":"UKK", "name":"South West",               "short":"SW",    "lvl":2, "col":1, "row":4, "parent":"ENG"},
    {"code":"SCT2","name":"Scotland",                 "short":"Sco",   "lvl":2, "col":2, "row":0, "parent":"UK"},
    {"code":"WLS2","name":"Wales",                    "short":"Wal",   "lvl":2, "col":1, "row":3, "parent":"UK"},
    {"code":"NIR2","name":"Northern Ireland",         "short":"NI",    "lvl":2, "col":0, "row":2, "parent":"UK"},
]

LEVEL_CODES = {
    "uk":     ["UK"],
    "nation": ["UK", "ENG", "SCT", "WLS", "NIR"],
    "region": ["UK", "ENG", "SCT", "WLS", "NIR",
               "UKC","UKD","UKE","UKF","UKG","UKH","UKI","UKJ","UKK",
               "SCT2","WLS2","NIR2"],
}


# ── period parsing ───────────────────────────────────────────────────────
def to_year(period: str, basis: str = "calendar") -> int | None:
    """
    Reduce a published period label to the calendar year it starts in.

    Everything ends up annual and plotted at its starting calendar year, so a
    financial-year point sits up to twelve months from a calendar-year point
    on the same vertical. The explorer warns about exactly this when two
    series with different bases are charted together — don't silently shift
    one to match the other here.
    """
    if not period:
        return None
    p = period.strip()

    # 2019/20, 2019-20, 2019/2020
    m = re.match(r"^(\d{4})\s*[/-]\s*(\d{2,4})$", p)
    if m:
        return int(m.group(1))
    # plain year, or a year with a quarter or month attached
    m = re.match(r"^(\d{4})", p)
    if m:
        return int(m.group(1))
    # 'Jan-19', 'Q1 2019'
    m = re.search(r"(\d{4})", p)
    return int(m.group(1)) if m else None


def to_annual(pairs: list[tuple[int, float]], how: str = "mean") -> dict[int, float]:
    """Collapse sub-annual observations to one value a year."""
    buckets: dict[int, list[float]] = {}
    for year, value in pairs:
        buckets.setdefault(year, []).append(value)
    out = {}
    for year, values in buckets.items():
        if how == "sum":
            out[year] = sum(values)
        elif how == "last":
            out[year] = values[-1]
        elif how == "max":
            out[year] = max(values)
        else:
            out[year] = mean(values)
    return out


def clean_number(raw) -> float | None:
    """ONS and DfE both use letter codes for suppressed or unavailable cells."""
    if raw in (None, "", "..", ":", "z", "x", "c", "u", "w", "-"):
        return None
    try:
        return float(str(raw).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


# ── adapters ─────────────────────────────────────────────────────────────
def fetch_ons_timeseries(cfg: dict) -> dict[int, float]:
    """
    ONS website series JSON — one request returns the whole history.

    Pragmatic and fast, but the URL encodes the site taxonomy
    (/economy/inflationandpriceindices/timeseries/d7bt/mm23), so paths
    occasionally move when ONS reorganises. Prefer ons_beta where the
    dataset is exposed there.
    """
    url = f"https://www.ons.gov.uk/{cfg['path'].strip('/')}/data"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()

    freq = cfg.get("frequency", "years")
    pairs: list[tuple[int, float]] = []
    for row in payload.get(freq, []):
        year = to_year(str(row.get("date", "")), cfg.get("basis", "calendar"))
        value = clean_number(row.get("value"))
        if year is not None and value is not None:
            pairs.append((year, value))
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_ons_beta(cfg: dict) -> dict[int, float]:
    """
    ONS Beta API at api.beta.ons.gov.uk/v1. Open, no key required.

    More stable than the website JSON, but you must know each dataset's
    dimension names and the option codes within them, which are not
    discoverable without walking /dimensions first.
    """
    base = "https://api.beta.ons.gov.uk/v1"
    ds, ed, ver = cfg["dataset"], cfg.get("edition", "time-series"), cfg.get("version", 1)
    params = {"limit": 10000}
    params.update(cfg.get("dimensions", {}))

    r = requests.get(f"{base}/datasets/{ds}/editions/{ed}/versions/{ver}/observations",
                     params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()

    pairs: list[tuple[int, float]] = []
    for obs in payload.get("observations", []):
        dims = obs.get("dimensions", {})
        period = (dims.get("Time") or dims.get("time") or {}).get("label", "")
        year = to_year(str(period), cfg.get("basis", "calendar"))
        value = clean_number(obs.get("observation"))
        if year is not None and value is not None:
            pairs.append((year, value))
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_dfe_ees(cfg: dict) -> dict[int, float]:
    """
    DfE Explore Education Statistics API.

        https://api.education.gov.uk/statistics/v1/data-sets/{id}/query

    POST with a JSON query is the supported production route; GET exists for
    exploration but cannot express conditions. Not every dataset in the EES
    catalogue is exposed through the API — some are CSV-only, which is why
    the csv adapter below exists as a fallback.
    """
    base = "https://api.education.gov.uk/statistics/v1"
    body = {
        "criteria":   cfg.get("criteria", {}),
        "indicators": [cfg["indicator"]],
        "page":       1,
        "pageSize":   10000,
    }
    r = requests.post(f"{base}/data-sets/{cfg['data_set_id']}/query",
                      json=body, headers={**UA, "Content-Type": "application/json"},
                      timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()

    pairs: list[tuple[int, float]] = []
    for row in payload.get("results", []):
        period = row.get("timePeriod", {})
        year = to_year(str(period.get("period", "")), "academic")
        value = clean_number((row.get("values") or {}).get(cfg["indicator"]))
        if year is not None and value is not None:
            pairs.append((year, value))
    return to_annual(pairs, cfg.get("aggregate", "mean"))


def fetch_csv(cfg: dict) -> dict[int, float]:
    """
    Generic CSV fallback — MHCLG live tables, OBR databank, anything published
    as a file rather than an API. Give it a URL, a year column and a value
    column. Unglamorous, and you will use it more than you expect.
    """
    import csv as _csv
    import io

    r = requests.get(cfg["url"], headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.content.decode(cfg.get("encoding", "utf-8-sig"), errors="replace")

    for _ in range(cfg.get("skip_rows", 0)):
        text = text.split("\n", 1)[1]

    reader = _csv.DictReader(io.StringIO(text))
    pairs: list[tuple[int, float]] = []
    for row in reader:
        if cfg.get("filter"):
            if any(str(row.get(k, "")).strip() != v for k, v in cfg["filter"].items()):
                continue
        year = to_year(str(row.get(cfg["year_column"], "")), cfg.get("basis", "calendar"))
        value = clean_number(row.get(cfg["value_column"]))
        if year is not None and value is not None:
            pairs.append((year, value))
    return to_annual(pairs, cfg.get("aggregate", "mean"))


ADAPTERS = {
    "ons_timeseries": fetch_ons_timeseries,
    "ons_beta":       fetch_ons_beta,
    "dfe_ees":        fetch_dfe_ees,
    "csv":            fetch_csv,
}


# ── assembly ─────────────────────────────────────────────────────────────
def to_dense(values: dict[int, float], start: int, end: int) -> list[float | None]:
    """explore.html expects a dense array from `start`, not a sparse map."""
    return [values.get(y) for y in range(start, end + 1)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build data/bundle.json from series.yaml")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    ap.add_argument("--only", default="", help="comma-separated series ids")
    ap.add_argument("--end", type=int, default=None, help="last year to include")
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG.read_text())
    entries = config["series"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        entries = [e for e in entries if e["id"] in wanted]
        if not entries:
            print(f"No series matched {args.only}", file=sys.stderr)
            return 1

    end = args.end or time.gmtime().tm_year
    built, failed, skipped = [], [], []

    for entry in entries:
        sid = entry["id"]
        src = entry.get("source") or {}
        stype = src.get("type")

        if stype in (None, "TODO") or src.get("id") == "TODO":
            skipped.append((sid, "no source configured"))
            continue
        if stype not in ADAPTERS:
            failed.append((sid, f"unknown source type {stype!r}"))
            continue

        codes = LEVEL_CODES[entry.get("geo", "uk")]
        data: dict[str, list] = {}
        try:
            for code in codes:
                cfg = dict(src)
                # per-area overrides live under source.areas.<CODE>
                override = (src.get("areas") or {}).get(code)
                if override is None and code != "UK" and len(codes) > 1:
                    continue
                if override:
                    cfg.update(override)
                values = ADAPTERS[stype](cfg)
                if not values:
                    continue
                start = entry.get("start") or min(values)
                data[code] = to_dense(values, start, end)
                entry["start"] = start
                time.sleep(0.25)   # be polite to the publishers
        except requests.HTTPError as exc:
            failed.append((sid, f"HTTP {exc.response.status_code}"))
            continue
        except Exception as exc:                       # noqa: BLE001
            failed.append((sid, f"{type(exc).__name__}: {exc}"))
            continue

        if not data:
            failed.append((sid, "no observations returned"))
            continue

        built.append({
            "id":     sid,
            "name":   entry["name"],
            "topic":  entry["topic"],
            "unit":   entry["unit"],
            "kind":   entry["kind"],
            "source": entry["publisher"],
            "geo":    entry.get("geo", "uk"),
            "basis":  entry.get("basis", "calendar"),
            "start":  entry["start"],
            "disc":   [{"y": d["year"], "note": d["note"]}
                       for d in entry.get("discontinuities", [])],
            "d":      data,
        })

    print(f"\n  built   {len(built)}")
    print(f"  skipped {len(skipped)}   (source still TODO)")
    print(f"  failed  {len(failed)}")
    for sid, why in failed:
        print(f"    ✗ {sid:<14} {why}")

    if args.dry_run:
        print("\n  --dry-run: nothing written")
        return 0
    if not built:
        print("\n  Nothing built — refusing to overwrite data/bundle.json", file=sys.stderr)
        return 1

    bundle = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "end":       end,
        "areas":     AREAS,
        "series":    built,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, separators=(",", ":")))
    print(f"\n  wrote {OUT.relative_to(ROOT)} — {OUT.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
