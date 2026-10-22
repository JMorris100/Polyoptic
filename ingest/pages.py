"""
Static pages for search engines, built from data/bundle.json.

The explorer is an app: its HTML holds a couple of dozen words until the
script runs, so nothing in the catalogue can be found by searching for it.
This writes a plain page for every indicator and every topic, each one
readable with no JavaScript at all, plus an A–Z index and the sitemap:

    indicator/<slug>/index.html   the figure, a chart, the table, the source
    indicator/<slug>/data.csv     the same values, for Dataset Search
    indicator/index.html          every indicator, A–Z
    topic/<topic>/index.html      one topic's indicators
    q/<slug>/index.html           one page per question in ingest/questions.py
    q/index.html                  every question, featured and not
    data/questions-more.json      the same questions, worked out, for the homepage
    sitemap.xml                   all of the above and the hand-written pages

Run after ingest.py (the weekly refresh does both):

    python ingest/pages.py
"""
from __future__ import annotations

import csv
import html
import io
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import questions as more_questions   # the questions answered in the homepage drawer

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://polyoptic.co"
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

TOPICS = [
    ("work", "Work, pay & living standards", "Jobs, pay, prices, household income, child poverty and the cost of living."),
    ("economy", "Economy & public finances", "Growth, productivity, business, trade, investment, borrowing, debt and tax."),
    ("housing", "Housing", "Prices, rents, affordability, housebuilding, homelessness and waiting lists."),
    ("education", "Education", "Pupils, teachers, absence, GCSEs, early years, apprenticeships and NEET."),
    ("health", "Health", "NHS waiting lists, A&E, GPs, obesity, smoking, life expectancy and wellbeing."),
    ("crime", "Crime & justice", "Survey and recorded crime, charge rates, homicide, courts, prisons and police."),
    ("transport", "Transport", "Rail, buses, road traffic and casualties, travel times and electric cars."),
    ("environment", "Environment & energy", "Emissions, the electricity mix, energy use, recycling and sewage spills."),
    ("migration", "Population & migration", "Population, births, deaths and fertility, migration, visas and asylum."),
    ("culture", "Culture & leisure", "Arts, heritage sites, museums and galleries, libraries and sports facilities."),
]
TOPIC_NAME = {k: n for k, n, _ in TOPICS}
GEO_RANK = ["UK", "Great Britain", "England and Wales", "England", "Wales", "Scotland", "Northern Ireland"]

esc = lambda s: html.escape(str(s), quote=True)


# ── numbers ──────────────────────────────────────────────────────────

def fmt(v: float | None, dp: int | None = None) -> str:
    """A figure to the precision a reader can use, with no trailing zeros:
    4.9 not 4.92, 8 not 8.00, 69.3 million not 69,281,437. Given `dp`, a
    figure under 100 keeps that many places, so one series reads 83.0 beside
    79.2 rather than 83 beside 79.2."""
    if v is None:
        return "–"
    a = abs(v)
    if dp is not None and a < 100:
        return f"{v:,.{dp}f}".replace("-", "−", 1)
    if a >= 10_000_000:
        return (f"{v / 1e6:,.1f}".rstrip("0").rstrip(".") + " million").replace("-", "−", 1)
    if a >= 100:
        return f"{v:,.0f}".replace("-", "−", 1)
    if a >= 1:
        out = f"{v:.1f}"
    else:
        out = f"{v:.2f}"
    out = out.rstrip("0").rstrip(".") if "." in out else out
    return out.replace("-", "−", 1) if out.startswith("-") else out


def with_unit(v: float, unit: str, dp: int | None = None) -> str:
    u = unit or ""
    f = lambda x: fmt(x, dp)
    if u.startswith("£") and v < 0:                  # −£151,296m, not £-151,296m
        return "−" + with_unit(-v, u, dp)
    if u.startswith("£ per "):                       # £752 per week
        return f"£{f(v)} {u[2:]}"
    if u.startswith("%"):
        return f"{f(v)}%" + (u[1:] if u != "%" else "")
    # £m and £bn wrap the number: £867,021m, £2.3bn, then anything after the comma
    for scale in ("m", "bn"):
        if u == f"£{scale}" or u.startswith(f"£{scale},"):
            return f"£{f(v)}{scale}" + u[len(scale) + 1:]
    if u.startswith("£") and not u.startswith("£ per") and " " not in u.strip():
        return f"£{f(v)}"
    return f"{f(v)} {u}".strip()


def series_dp(s: dict) -> int | None:
    """The decimal places a series' figures under 100 are shown to, the same
    for every year so 83.0 sits beside 79.2: none for a series of whole
    numbers, two where it dips under 1, one otherwise."""
    return values_dp(v for _, v in points(s))


def values_dp(vals) -> int | None:
    small = [v for v in vals if v is not None and abs(v) < 100]
    if not small:
        return None
    places = max(len(f"{v:.6f}".rstrip("0").split(".")[1]) for v in small)
    if places == 0:
        return 0                                     # whole numbers stay whole
    return min(2, places) if any(abs(v) < 1 for v in small) else 1


def nice_step(span: float, n: int = 5) -> float:
    raw = span / max(1, n)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def slugify(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("%", " percent ")
    s = re.sub(r"\([^)]*\)", lambda m: " " + m.group(0)[1:-1] + " ", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)[:80].strip("-")


def points(s: dict) -> list[tuple[int, float]]:
    return [(s["start"] + i, v) for i, v in enumerate(s["values"]) if v is not None]


def full_points(s: dict) -> list[tuple[int, float]]:
    """Whole years only: a final year the source is part-way through is left out,
    so 'latest', changes and highs and lows compare like with like."""
    p = s.get("partial") or {}
    return [(y, v) for y, v in points(s) if y != p.get("year")] or points(s)


def year_figure(s: dict, y: int) -> str:
    """A year as the figure for it was made: '2025 average', 'Dec 2025' for
    the last month of a stock, '2025 total' — or just '2025' for a source that
    publishes one figure a year. A reader checking against the publisher's
    monthly table then knows which figure to look for."""
    a = s.get("annual") or {}
    how, per = a.get("how"), a.get("per")
    basis = s.get("year_basis", "calendar")
    yl = year_label(y, basis)                        # 2025-26 for a financial year
    if how == "mean":
        return f"{yl} average"
    if how == "sum":
        return f"{yl} total"
    if how == "last" and per == 12:
        return {"financial": f"Mar {y + 1}", "academic": f"Aug {y + 1}"}.get(basis, f"Dec {y}")
    if how == "last" and per == 4:
        return f"Q4 {yl}"
    return yl


def last_break(s: dict) -> int | None:
    """The last year the series changed basis, if it did inside its run: the
    first year measured the new way. Figures from it on compare like with like."""
    pts = full_points(s)
    ys = [int(d["year"]) for d in s.get("discontinuities") or [] if d.get("year")]
    ys = [y for y in ys if pts and pts[0][0] < y <= pts[-1][0]]
    return max(ys) if ys else None


def part_label(s: dict) -> str:
    """'Jan–Mar 2026' for a part-year figure, or '' when there is none."""
    p = s.get("partial") or {}
    if not p:
        return ""
    span = p.get("label") or f'{p.get("have")} of {p.get("of")} periods'
    return f'{span} {p["year"]}'


# ── the chart, drawn here so the page needs no script ───────────────

def chart_svg(s: dict) -> str:
    pts = points(s)
    W, H, L, R, T, B = 760, 300, 54, 18, 14, 26
    xs = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(vs), max(vs)
    if lo > 0 and lo < (hi - lo) * 0.6:
        lo = 0                                   # small positives read best from zero
    pad = (hi - lo) * 0.08 or abs(hi) * 0.1 or 1
    lo2, hi2 = lo - (0 if lo == 0 else pad), hi + pad
    step = nice_step(hi2 - lo2)
    t0 = math.floor(lo2 / step) * step
    ticks = []
    t = t0
    while t <= hi2 + 1e-9:
        if t >= lo2 - 1e-9:
            ticks.append(t)
        t += step
    lo2, hi2 = min(lo2, ticks[0]), max(hi2, ticks[-1])
    X = lambda x: L + (x - x0) / max(1, x1 - x0) * (W - L - R)
    Y = lambda v: T + (1 - (v - lo2) / ((hi2 - lo2) or 1)) * (H - T - B)
    g = []
    for t in ticks:
        g.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="g"/>')
        g.append(f'<text x="{L-8}" y="{Y(t)+3.5:.1f}" text-anchor="end" class="a">{esc(fmt(t))}</text>')
    span = x1 - x0
    ys = 1 if span <= 12 else 2 if span <= 24 else 5 if span <= 60 else 10 if span <= 120 else 20
    for yr in range(math.ceil(x0 / ys) * ys, x1 + 1, ys):
        g.append(f'<text x="{X(yr):.1f}" y="{H-6}" text-anchor="middle" class="a">{yr}</text>')
    for d in s.get("discontinuities", []):
        y = d.get("year")
        if y and x0 < y <= x1:
            g.append(f'<line x1="{X(y):.1f}" x2="{X(y):.1f}" y1="{T}" y2="{H-B}" class="brk"/>')
    # a gap in the published years is a gap in the line, not a straight bridge
    segs, cur, prev = [], [], None
    for x, v in pts:
        if prev is not None and x != prev + 1:
            segs.append(cur); cur = []
        cur.append((x, v)); prev = x
    segs.append(cur)
    for seg in segs:
        if len(seg) == 1:
            x, v = seg[0]
            g.append(f'<circle cx="{X(x):.1f}" cy="{Y(v):.1f}" r="3" class="dot"/>')
        else:
            d = "M" + " L".join(f"{X(x):.1f} {Y(v):.1f}" for x, v in seg)
            g.append(f'<path d="{d}" class="ln"/>')
    lx, lv = pts[-1]
    g.append(f'<circle cx="{X(lx):.1f}" cy="{Y(lv):.1f}" r="4" class="end"/>')
    label = f'{s["name"]}, {x0} to {x1}, {s["unit"]}'
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}">'
            f'<title>{esc(label)}</title>{"".join(g)}</svg>')


# ── local areas: the top and bottom of the latest year ──────────────

def area_extremes(s: dict, ix: dict) -> dict | None:
    f = ROOT / "data" / "areas" / f'{s["id"]}.json'
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    areas = ix.get("areas", {})
    by_level: dict[str, list] = {}
    for code, vals in d["values"].items():
        lvl = (areas.get(code) or {}).get("l")
        if lvl not in ("la", "district", "county", "region", "itl3"):
            continue
        by_level.setdefault(lvl, []).append((code, vals))
    lvl = "la" if "la" in by_level else max(by_level, key=lambda k: len(by_level[k]), default=None)
    if not lvl:
        return None
    rows = by_level[lvl]
    length = max(len(v) for _, v in rows)
    for k in range(length - 1, -1, -1):
        got = [(c, v[k]) for c, v in rows if k < len(v) and v[k] is not None]
        if len(got) >= 10:
            got.sort(key=lambda r: -r[1])
            name = lambda c: (areas.get(c) or {}).get("n", c)
            return {"year": d["start"] + k, "level": (ix.get("levelNames") or {}).get(lvl, lvl),
                    "n": len(got), "top": [(name(c), v) for c, v in got[:10]],
                    "bottom": [(name(c), v) for c, v in got[-10:][::-1]]}
    return None


# ── page furniture ──────────────────────────────────────────────────

CSS = """
:root{--paper:#EDEFF1;--surface:#fff;--ink:#0F1419;--muted:#5C6672;--rule:#D3D8DD;--purple:#4633A8;--soft:#F4F2FA;--prule:#D8D2EC;--line:#6D4AE0;--warn:#B45309}
html[data-theme="dark"]{--paper:#0B0D12;--surface:#151823;--ink:#E8ECF1;--muted:#8A93A0;--rule:#262B36;--purple:#8B6BFF;--soft:#241E3E;--prule:#3A3260;--line:#9B84F0;--warn:#E0B45C;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px}
.topbar{background:#4633A8;color:#fff}
.topbar .wrap{display:flex;align-items:center;gap:22px;height:60px}
.brand{display:flex;align-items:center;gap:9px;text-decoration:none;color:#fff}
.brand svg{width:38px;height:27px}
.wordmark{font-weight:800;font-size:19px;letter-spacing:-0.02em}.wordmark .b{font-weight:500;opacity:.85}
.topnav{margin-left:auto;display:flex;align-items:center;gap:18px}
.topnav a{color:#fff;text-decoration:none;font-size:14px;opacity:.9}
.topnav .btn{background:#fff;color:#4633A8;padding:7px 14px;border-radius:100px;font-size:13.5px;font-weight:600;opacity:1}
@media(max-width:820px){.topnav a:not(.btn){display:none}}
main.wrap{padding-top:40px;padding-bottom:10px}
.crumbs{font-family:"IBM Plex Mono";font-size:11px;letter-spacing:.06em;color:var(--muted);margin:0 0 14px}
.crumbs a{color:var(--muted)}
h1{font-size:clamp(28px,4vw,40px);font-weight:800;letter-spacing:-0.02em;line-height:1.1;margin:0 0 8px}
.sub{color:var(--muted);font-size:16px;margin:0 0 24px;max-width:70ch}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:0 0 18px}
.fact{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:14px 16px}
.fact b{display:block;font-family:"IBM Plex Mono";font-weight:500;font-size:22px;letter-spacing:-.01em;color:var(--purple)}
.fact span{font-size:12.5px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:18px 20px}
.card svg{width:100%;height:auto;display:block}
.card .g{stroke:var(--rule);stroke-width:1}.card .a{font-family:"IBM Plex Mono",monospace;font-size:10px;fill:var(--muted)}
.card .ln{fill:none;stroke:var(--line);stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round}
.card .dot,.card .end{fill:var(--line)}.card .brk{stroke:var(--warn);stroke-width:1;stroke-dasharray:3 3}
.cap{font-size:12.5px;color:var(--muted);margin:8px 0 0}
.cta{display:inline-block;margin:20px 10px 0 0;background:var(--purple);color:#fff;text-decoration:none;font-weight:600;font-size:15px;padding:11px 20px;border-radius:100px}
.cta.ghost{background:transparent;color:var(--purple);border:1.5px solid var(--prule)}
.cols{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:40px;margin-top:38px;align-items:start}
@media(max-width:880px){.cols{grid-template-columns:1fr;gap:26px}}
h2{font-size:19px;font-weight:700;letter-spacing:-0.015em;margin:28px 0 8px}
h2:first-child{margin-top:0}
p{margin:0 0 12px;max-width:68ch}
a{color:var(--purple)}
ul.notes{padding-left:18px;margin:0 0 12px}ul.notes li{margin-bottom:6px;max-width:66ch}
.side{background:var(--soft);border:1px solid var(--prule);border-radius:12px;padding:16px 18px;font-size:14px}
.side h2{font-size:15px;margin:0 0 8px}.side dl{margin:0}.side dt{font-family:"IBM Plex Mono";font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-top:10px}
.side dd{margin:2px 0 0;overflow-wrap:anywhere}
table{border-collapse:collapse;width:100%;font-size:14px;background:var(--surface);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
th,td{padding:6px 12px;border-bottom:1px solid var(--rule);text-align:left}
td.n,th.n{text-align:right;font-family:"IBM Plex Mono";font-variant-numeric:tabular-nums}
details{margin-top:10px}summary{cursor:pointer;color:var(--purple);font-weight:600}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:640px){.two{grid-template-columns:1fr}}
.list{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}
.list a{display:block;height:100%;background:var(--surface);border:1px solid var(--rule);border-radius:10px;padding:11px 14px;text-decoration:none;color:var(--ink)}
.list a:hover{border-color:var(--purple)}
.list b{display:block;font-size:14.5px;line-height:1.3}.list span{display:block;font-size:12.5px;color:var(--muted);margin-top:3px}
.grp{font-family:"IBM Plex Mono";font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:26px 0 10px}
footer{margin-top:56px;padding:30px 0 56px;border-top:1px solid var(--rule);font-size:13px;color:var(--muted)}
footer .wrap{display:flex;justify-content:space-between;gap:28px;flex-wrap:wrap}footer p{max-width:56ch;margin:0}
footer nav{display:flex;flex-wrap:wrap;gap:6px 16px}footer nav a{color:var(--muted)}
"""

LOGO = """<svg viewBox="6.5 16.5 87 63" role="img" aria-label="Polyoptic"><defs><clipPath id="lgw"><path d="M10 50 Q50 -10 90 50 Q50 102 10 50 Z"/></clipPath></defs><path d="M10 50 Q50 -10 90 50 Q50 102 10 50 Z" fill="none" stroke="#fff" stroke-width="5" stroke-linejoin="round"/><g clip-path="url(#lgw)" fill="#fff"><rect x="29.75" y="46.56" width="6" height="18.72"/><rect x="41.25" y="36.48" width="6" height="28.80"/><rect x="52.75" y="42.60" width="6" height="22.68"/><rect x="64.25" y="30.72" width="6" height="34.56"/></g></svg>"""


def page(*, path: str, depth: int, title: str, desc: str, og_image: str, og_alt: str,
         ld: list[dict], body: str, explore: str = "explore.html", css: str = "", og_type: str = "article") -> str:
    up = "../" * depth
    url = f"{SITE}/{path}"
    topics = " · ".join(f'<a href="{up}topic/{k}/">{esc(n)}</a>' for k, n, _ in TOPICS)
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:site_name" content="Polyoptic">
<meta property="og:title" content="{esc(title.replace(' | Polyoptic', ''))}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(og_alt)}">
<meta property="og:url" content="{url}">
<meta property="og:type" content="{og_type}">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{json.dumps(ld if len(ld) > 1 else ld[0], ensure_ascii=False, separators=(",", ":"))}</script>
<script>(function(){{try{{if(localStorage.getItem("polyoptic-theme")==="dark")document.documentElement.dataset.theme="dark";}}catch(e){{}}}})();</script>
<script src="{up}feedback.js" defer></script>
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}{css}</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <a class="brand" href="{up or './'}">{LOGO}<span class="wordmark">poly<span class="b">optic</span></span></a>
  <nav class="topnav"><a href="{up}#questions">Questions</a><a href="{up}#topics">Topics</a><a href="{up}indicator/">Indicators</a><a href="{up}about.html">About</a><a href="{up}data.html">Fetch log</a>
    <a class="btn" href="{up}{explore}">Open the explorer</a></nav>
</div></div>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
  <p>Contains public sector information licensed under the Open Government Licence v3.0. Polyoptic publishes no data of its own: every figure links back to the release it came from. Built in the UK by <a href="{up}about.html">Josh Morris</a>.</p>
  <nav>{topics} · <a href="{up}indicator/">All indicators A–Z</a></nav>
</div></footer>
</body>
</html>
"""


def crumbs(depth: int, trail: list[tuple[str, str | None]]) -> str:
    up = "../" * depth
    parts = [f'<a href="{up or "./"}">Home</a>'] + [
        f'<a href="{up}{href}">{esc(n)}</a>' if href else esc(n) for n, href in trail]
    return f'<nav class="crumbs" aria-label="Breadcrumb">{" › ".join(parts)}</nav>'


def breadcrumb_ld(trail: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{SITE}/{u}"}
        for i, (n, u) in enumerate([("Polyoptic", "")] + trail)]}


# ── one indicator ───────────────────────────────────────────────────

def change_line(s: dict) -> tuple[str, str] | None:
    """The change over the last ten years (or the whole run, if shorter) —
    never across a break: if the series changed basis inside that window, the
    change is measured from the break, and says so."""
    pts = full_points(s)
    if len(pts) < 2:
        return None
    ly, lv = pts[-1]
    brk = last_break(s)
    yl = lambda y: year_label(y, s.get("year_basis", "calendar"))
    inside = brk is not None and brk > ly - 10
    # a break with three or more years after it: measure from it; one too
    # recent to measure from: keep the ten years, and say they cross it
    since = brk if inside and ly - brk >= 3 else ly - 10
    base = next(((y, v) for y, v in pts if y >= since), pts[0])
    by, bv = base
    if by == ly:
        return None
    note = (", when the series changed" if inside and by == brk else
            f", across the {brk} break" if inside else "")
    label = f"change since {yl(by)}{note}"
    unit = s["unit"] or ""
    dp = series_dp(s)
    if unit.startswith("%") or s["kind"] == "rate":
        d = lv - bv
        return (f'{"+" if d >= 0 else "−"}{fmt(abs(d), dp)} pts' if unit.startswith("%") else
                f'{"+" if d >= 0 else "−"}{fmt(abs(d), dp)}', label)
    if bv:
        pc = (lv / bv - 1) * 100
        # from a small base a percentage or a multiple is the misleading
        # headline (299 to 41,472 is "+13,770%"); give the change in the unit
        # itself, and past 100% drop the decimal place
        if abs(pc) >= 300:
            d = lv - bv
            return (f'{"+" if d >= 0 else "−"}{fmt(abs(d), dp)}', f"since {yl(by)} (from {fmt(bv, dp)}){note}")
        return (f'{"+" if pc >= 0 else "−"}{abs(pc):,.{0 if abs(pc) >= 100 else 1}f}%', label)
    return None


def indicator_page(s: dict, slug: str, by_id: dict, slugs: dict, ix: dict, pubs: dict) -> str:
    pts = full_points(s)
    ly, lv = pts[-1]
    fy = pts[0][0]
    part = s.get("partial") or {}
    topic = (s.get("topics") or ["economy"])[0]
    tname = TOPIC_NAME.get(topic, topic.title())
    geo = s.get("geography", "UK")
    unit = s.get("unit", "")
    snap = s.get("snapshot")
    years = f"{ly}" if snap or fy == ly else f"{fy}–{ly}"
    pub_full = s.get("publisher_full") or s.get("publisher") or s.get("source")
    dp = series_dp(s)
    yl = lambda y: year_label(y, s.get("year_basis", "calendar"))
    latest = with_unit(lv, unit, dp)
    title = f'{s["name"]}: {geo} {"figures" if snap else "data"}, {years} | Polyoptic'
    desc = (f'{s["name"]}, {geo}: {latest}, {year_figure(s, ly)}. '
            + ("" if snap else f"Every published year from {fy}, ")
            + f"from {pub_full}, with the source, caveats and a chart you can rebase or compare.")
    explore = (f'explore.html#p={s["id"]}~map~none~{fy}~{ly}~bands' if snap and s.get("areas")
               else f'explore.html#p={s["id"]}~line~none~{fy}~{ly}~bands')
    url = f"indicator/{slug}/"

    # a long unit ('house price to earnings ratio') goes under the number, not in it
    short = latest if len(latest) <= 14 else fmt(lv, dp)
    whole = (f'<div class="fact"><b>{esc(short)}</b><span>{"Latest" if not part else "Latest whole year"}, '
             f'{esc(year_figure(s, ly))}{"" if short == latest else " · " + esc(unit)}</span></div>')
    facts = [whole]
    if part and part.get("value") is not None:
        what = {"sum": "So far in", "mean": "Average so far,", "last": "Latest,"}.get(part.get("how"), "So far,")
        # a stock's part-year figure is its latest month, not a span of months —
        # and the most recent figure there is, so it leads
        when = (f'{(part.get("label") or "").split("–")[-1]} {part["year"]}'.strip()
                if part.get("how") == "last" else part_label(s))
        pv = with_unit(part["value"], unit, dp)
        fact = (f'<div class="fact part"><b>{esc(pv if len(pv) <= 14 else fmt(part["value"], dp))}</b>'
                f'<span>{esc(what)} {esc(when)}{"" if part.get("how") == "last" else " · part-year"}</span></div>')
        if part.get("how") == "last":
            facts.insert(0, fact)
        else:
            facts.append(fact)
    ch = change_line(s)
    if ch and not snap:
        facts.append(f'<div class="fact"><b>{esc(ch[0])}</b><span>{esc(ch[1])}</span></div>')
    if len(pts) >= 3 and not snap:
        # highs and lows never straddle a break: measured from the last one,
        # when enough years follow it, and said so
        brk = last_break(s)
        after = [p for p in pts if brk is not None and p[0] >= brk]
        span = after if len(after) >= 3 else pts
        note = f" (since the {brk} break)" if span is after else (" (across a break)" if brk is not None else "")
        hy, hv = max(span, key=lambda p: p[1])
        my, mv = min(span, key=lambda p: p[1])
        facts.append(f'<div class="fact"><b>{esc(fmt(hv, dp))}</b><span>Highest, {esc(yl(hy))}{esc(note)}</span></div>')
        facts.append(f'<div class="fact"><b>{esc(fmt(mv, dp))}</b><span>Lowest, {esc(yl(my))}{esc(note)}</span></div>')

    breaks = s.get("discontinuities") or []
    chart = ""
    if len(pts) >= 2:
        pnote = ""
        if part:
            pnote = (f"{part['year']} covers {part_label(s).rsplit(' ', 1)[0]} only · " if part.get("plotted")
                     else f"{part['year']} is left off until the year is complete · ")
        basis = {"financial": "financial years (April to March), plotted at the year they start · ",
                 "academic": "school years, plotted at the year they start · "}.get(s.get("year_basis"), "")
        chart = (f'<div class="card">{chart_svg(s)}<p class="cap">{esc(unit)} · {esc(geo)} · {esc(basis)}'
                 f'{"dashed lines mark breaks in the series · " if breaks else ""}{esc(pnote)}source: {esc(s.get("source",""))}</p></div>')

    notes = "".join(f"<li>{esc(n)}</li>" for n in s.get("notes", []))
    # an old latest year reads as a stalled refresh unless the page says why
    checked = (s.get("fetched") or "")[:10]
    if checked and ly < int(checked[:4]) - 2:
        notes += (f"<li>{esc(yl(ly))} is the latest year the source has published here. Polyoptic checks it "
                  f"every Monday (last on {esc(checked)}) and adds a new year when one appears.</li>")
    brk = "".join(f'<li><b>{esc(d.get("year",""))}: {esc(d.get("label",""))}.</b> {esc(d.get("note",""))}</li>' for d in breaks)

    ex = area_extremes(s, ix) if s.get("areas") else None
    local = ""
    if ex:
        adp = values_dp(v for _, v in ex["top"] + ex["bottom"])
        row = lambda r: f'<tr><td>{esc(r[0])}</td><td class="n">{esc(fmt(r[1], adp))}</td></tr>'
        local = f"""<h2>Highest and lowest areas, {ex['year']}</h2>
<p>Figures are published for {ex['n']} {esc(ex['level'].lower())}. The ten highest and lowest:</p>
<div class="two"><table><thead><tr><th>Highest</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{"".join(row(r) for r in ex['top'])}</tbody></table>
<table><thead><tr><th>Lowest</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{"".join(row(r) for r in ex['bottom'])}</tbody></table></div>
<p style="margin-top:12px"><a href="../../explore.html#p={s['id']}~map~none~{fy}~{ly}~bands">See every area on a map →</a></p>"""

    table = "".join(f'<tr><td>{esc(yl(y))}</td><td class="n">{esc(fmt(v, dp))}</td></tr>' for y, v in reversed(pts))
    if part and part.get("value") is not None:
        table = (f'<tr><td>{esc(part_label(s))} <small>(part-year)</small></td>'
                 f'<td class="n">{esc(fmt(part["value"], dp))}</td></tr>') + table
    data_tbl = f"""<h2>Every published year</h2>
<details{' open' if len(pts) <= 12 else ''}><summary>{len(pts)} value{'s' if len(pts) != 1 else ''}, {esc(unit)}</summary>
<table style="margin-top:10px"><thead><tr><th>Year</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{table}</tbody></table></details>
<p style="margin-top:10px"><a href="data.csv">Download as CSV</a> · <a href="../../data.html#{esc(s['id'])}">See it in the fetch log</a></p>"""

    related = [x for x in by_id.values() if x["id"] != s["id"] and topic in (x.get("topics") or [])]
    related.sort(key=lambda x: (x.get("geography") != geo, x["name"]))
    rel = "".join(f'<li><a href="../{slugs[x["id"]]}/"><b>{esc(x["name"])}</b><span>{esc(x.get("geography",""))}</span></a></li>'
                  for x in related[:9])

    pub_url = pubs.get(s.get("publisher"), "")
    side = f"""<aside class="side"><h2>Where it comes from</h2><dl>
<dt>Publisher</dt><dd>{f'<a href="{esc(pub_url)}">{esc(pub_full)}</a>' if pub_url else esc(pub_full)}</dd>
<dt>Release</dt><dd>{f'<a href="{esc(s.get("source_url"))}">{esc(s.get("source"))}</a>' if s.get("source_url") else esc(s.get("source"))}</dd>
<dt>Covers</dt><dd>{esc(geo)}</dd>
<dt>Years</dt><dd>{esc(years)} ({esc({'financial':'financial years','academic':'academic years'}.get(s.get('year_basis'),'calendar years'))})</dd>
<dt>Licence</dt><dd><a href="{OGL}">{esc(s.get('licence','OGL v3.0'))}</a></dd>
<dt>Last fetched</dt><dd>{esc((s.get('fetched') or '')[:10])}</dd>
</dl></aside>"""

    body = f"""{crumbs(2, [(tname, f'topic/{topic}/'), (s['name'], None)])}
<h1>{esc(s['name'])}</h1>
<p class="sub">{esc(geo)} · {esc(years)} · {esc(unit)} · from {esc(pub_full)}</p>
<div class="facts">{''.join(facts)}</div>
{chart}
<a class="cta" href="../../{explore}">{'Open it on a map' if snap and s.get('areas') else 'Open in the explorer'} →</a>
<a class="cta ghost" href="data.csv">Download CSV</a>
<div class="cols"><div>
<h2>About this figure</h2>
{f'<ul class="notes">{notes}</ul>' if notes else f'<p>{esc(s["name"])}, as published by {esc(pub_full)}.</p>'}
{f'<h2>Breaks in the series</h2><ul class="notes">{brk}</ul>' if brk else ''}
{local}
{data_tbl}
</div>{side}</div>
{asked_list(ASKED.get(s['id'], []), 2, "Questions this figure helps answer")}{f'<h2 style="margin-top:44px">More on {esc(tname.lower())}</h2><ul class="list">{rel}</ul>' if rel else ''}"""

    ld = [{
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f'{s["name"]} ({geo})', "description": desc,
        "url": f"{SITE}/{url}", "identifier": s["id"],
        "keywords": [tname, geo, s.get("publisher", ""), unit],
        "creator": {"@type": "Organization", "name": pub_full, **({"url": pub_url} if pub_url else {})},
        "license": OGL, "isAccessibleForFree": True,
        "temporalCoverage": f"{fy}/{ly}",
        "spatialCoverage": {"@type": "Place", "name": "United Kingdom" if geo == "UK" else geo},
        "variableMeasured": {"@type": "PropertyValue", "name": s["name"], "unitText": unit},
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}/{url}data.csv"}],
        "includedInDataCatalog": {"@type": "DataCatalog", "name": "Polyoptic", "url": f"{SITE}/indicator/"},
        **({"isBasedOn": s["source_url"]} if s.get("source_url") else {}),
        **({"dateModified": s["fetched"][:10]} if s.get("fetched") else {}),
    }, breadcrumb_ld([(tname, f"topic/{topic}/"), (s["name"], url)])]
    return page(path=url, depth=2, title=title, desc=desc[:300], og_image=f"og/topic-{topic}.png",
                og_alt=f"{tname} on Polyoptic", ld=ld, body=body, explore=explore)


def csv_text(s: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["year", "value", "unit", "geography", "series", "source", "licence"])
    for y, v in points(s):
        w.writerow([y, v, s.get("unit", ""), s.get("geography", ""), s["name"], s.get("source", ""), "OGL v3.0"])
    return out.getvalue()


# ── topics and the index ────────────────────────────────────────────

def card(s: dict, href: str) -> str:
    pts = full_points(s)
    ly, lv = pts[-1]
    return (f'<li><a href="{href}"><b>{esc(s["name"])}</b>'
            f'<span>{esc(with_unit(lv, s.get("unit",""), series_dp(s)))}, {esc(year_figure(s, ly))} · {esc(s.get("geography",""))}</span></a></li>')


def topic_page(k: str, name: str, blurb: str, series: list[dict], slugs: dict) -> str:
    groups: dict[str, list] = {}
    for s in sorted(series, key=lambda x: x["name"]):
        groups.setdefault(s.get("geography", "UK"), []).append(s)
    order = sorted(groups, key=lambda g: GEO_RANK.index(g) if g in GEO_RANK else 99)
    body = f"""{crumbs(2, [(name, None)])}
<h1>{esc(name)} statistics</h1>
<p class="sub">{esc(blurb)} {len(series)} official indicators, each with every published year, its source and its caveats.</p>
<a class="cta" href="../../explore.html#t={k}">Chart them in the explorer →</a>
{asked_list([q for q in ALL_QUESTIONS if k in q["topics"]], 2, f"Questions about {name.lower()}")}""" + "".join(f'<div class="grp">{esc(g)} · {len(groups[g])}</div><ul class="list">'
              + "".join(card(s, f'../../indicator/{slugs[s["id"]]}/') for s in groups[g]) + "</ul>" for g in order)
    url = f"topic/{k}/"
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{name} statistics", "url": f"{SITE}/{url}",
           "description": blurb, "isPartOf": {"@type": "WebSite", "name": "Polyoptic", "url": f"{SITE}/"}},
          breadcrumb_ld([(name, url)])]
    return page(path=url, depth=2, title=f"{name} statistics for the UK | Polyoptic",
                desc=f"{blurb} {len(series)} official UK indicators, charted with their sources and caveats.",
                og_image=f"og/topic-{k}.png", og_alt=f"{name} on Polyoptic", ld=ld, body=body, explore=f"explore.html#t={k}")


def index_page(series: list[dict], slugs: dict) -> str:
    letters: dict[str, list] = {}
    for s in sorted(series, key=lambda x: x["name"].lower()):
        c = s["name"][0].upper()
        letters.setdefault(c if c.isalpha() else "#", []).append(s)
    body = f"""{crumbs(1, [("All indicators", None)])}
<h1>Every indicator, A–Z</h1>
<p class="sub">{len(series)} official UK statistics from {len({s.get('publisher') for s in series})} publishers. Each page has every published year, a chart, the source and the caveats.</p>
<p>Want the exact address each one was fetched from, when, and every value as it arrived? See the <a href="../data.html">fetch log</a>.</p>
<p>{" · ".join(f'<a href="#l-{c}">{c}</a>' for c in letters)}</p>
""" + "".join(f'<div class="grp" id="l-{c}">{c}</div><ul class="list">'
              + "".join(card(s, f'{slugs[s["id"]]}/') for s in letters[c]) + "</ul>" for c in letters)
    # the catalogue every indicator page's Dataset markup says it belongs to
    ld = [{"@context": "https://schema.org", "@type": ["CollectionPage", "DataCatalog"], "name": "Every indicator, A–Z",
           "url": f"{SITE}/indicator/", "inLanguage": "en-GB", "license": OGL,
           "isPartOf": {"@type": "WebSite", "name": "Polyoptic", "url": f"{SITE}/"}}]
    return page(path="indicator/", depth=1, title="Every UK statistic on Polyoptic, A–Z | Polyoptic",
                desc=f"All {len(series)} official UK indicators on Polyoptic, A–Z: work and pay, the economy, housing, education, health, crime, transport, environment, population and culture.",
                og_image="og/home.png", og_alt="Polyoptic", ld=ld, body=body)


# ── the four featured questions ─────────────────────────────────────
# Answered here, each its own way, because one sentence shape does not fit
# every question:
#   ratio         two series that are both money or price indexes, rebased to
#                 the same year; "A ended N% ahead of B" is meaningful because
#                 both are growth in the same kind of thing. `also` gives the
#                 answer from a second start year, because the start year can
#                 decide the verdict and a page should not pick the kind one
#   same_unit     convert one series into the other's unit first (debt interest
#                 in £m into % of GDP, beside debt in % of GDP) and derive what
#                 the pair means (interest ÷ debt, the effective rate)
#   before_after  a question about an event: the last year before it against
#                 the first year after it and the latest, naming any break in
#                 the series that falls between them
# Each returns a lead — one sentence that answers the question, both halves
# where it has two — and the fuller numbers under it. The generator refuses to
# write a ratio between series in units that cannot be compared, rather than
# writing a sentence that sounds right.

QUESTIONS = {
    # 2008 first: "pay hasn't kept up" means since the financial crisis, and
    # from 2000 the answer is a different one; the page gives both
    "has-pay-kept-up-with-prices": {"kind": "ratio", "ids": ["pay", "cpih"], "from": 2008, "also": 2000},
    "have-rents-outrun-pay": {"kind": "ratio", "ids": ["rents", "pay"], "from": 2015},
    "what-does-the-debt-cost-to-carry": {"kind": "same_unit", "ids": ["psnd", "debtint"], "from": 1993},
    "did-lost-schooling-widen-the-gap": {
        "kind": "before_after", "ids": ["gap", "absence"], "from": 2010,
        "before": 2018, "after": 2021, "event": "the pandemic",
        # a higher gap index means disadvantaged pupils are further behind
        "words": {"gap": ("widened", "narrowed")},
    },
}

QUESTION_NAMES = {
    "pay": "average pay", "cpih": "prices", "rents": "private rents",
    "psnd": "public sector net debt", "debtint": "debt interest",
    "absence": "persistent absence", "gap": "the disadvantage gap index",
}
# names that take "are": "private rents are", "prices are"
PLURAL = {"rents", "cpih"}
# the names on the chart, short enough to sit at the line ends
CHART_NAMES = {"pay": "Average pay", "cpih": "Prices (CPIH)", "rents": "Private rents",
               "gap": "Disadvantage gap index", "absence": "Persistent absence"}

# units that can be rebased against each other: both growth in money or prices
RATIO_KINDS = {"money_cash", "index"}


def pct(v: float) -> str:
    return f'{"+" if v >= 0 else "−"}{abs(v):.0f}%'


def year_label(y: int, basis: str) -> str:
    if basis == "academic":
        return f"{y}/{(y + 1) % 100:02d}"
    if basis == "financial":
        return f"{y}-{(y + 1) % 100:02d}"
    return str(y)


def qname(s: dict) -> str:
    return QUESTION_NAMES.get(s["id"], s["name"])


def cap(t: str) -> str:
    return t[0].upper() + t[1:]


def verdict(r: float) -> str:
    """How far ahead A ended against B, as a one-word answer to 'did A keep up
    with / outrun B?' — within 10% either way is too close for a plain yes or no."""
    return "Yes" if r >= 10 else "Only just" if r >= 0 else "Not quite" if r > -10 else "No"


def q_ratio(cfg: dict, by_id: dict) -> dict:
    a, b = (by_id[i] for i in cfg["ids"])
    for s in (a, b):
        if s["kind"] not in RATIO_KINDS:
            raise ValueError(f'{s["id"]} is {s["kind"]} ({s["unit"]}): a ratio question needs money or price '
                             f"indexes on both sides — give this question another kind")
    full = [dict(full_points(s)) for s in (a, b)]

    def rebase(frm):
        runs = [{y: v for y, v in r.items() if y >= frm} for r in full]
        start, end = max(min(r) for r in runs), min(max(r) for r in runs)
        A, B = ({y: r[y] / r[start] * 100 for y in sorted(r) if start <= y <= end} for r in runs)
        both = sorted(set(A) & set(B))
        return start, end, A, B, both, {y: (A[y] / B[y] - 1) * 100 for y in both}

    start, end, A, B, both, rel = rebase(cfg["from"])
    na, nb = qname(a), qname(b)
    ga, gb = A[end] - 100, B[end] - 100
    r = rel[end]
    if ga >= 0 and gb >= 0:
        faster = (f"{cap(na)} rose faster" if ga > gb + 1 else
                  f"{cap(nb)} rose faster" if gb > ga + 1 else "The two rose by about the same")
    elif ga < 0 and gb < 0:
        faster = f"Both fell, {na if ga > gb else nb} by less"
    else:
        faster = f"{cap(na if ga > gb else nb)} rose while {nb if ga > gb else na} fell"
    # the stretch spent on the other side before ending where it did
    other = [y for y in both[1:-1] if (rel[y] < 0) != (r < 0)]
    run = (f", after {'trailing' if r >= 0 else 'leading'} {nb} every year from {other[0]} to {other[-1]}"
           if other and other[-1] - other[0] + 1 == len(other) and len(other) >= 3 else "")
    far = max(both, key=lambda y: abs(rel[y]))
    widest = (f", having been {abs(rel[far]):.0f}% {'ahead' if rel[far] > 0 else 'behind'} at the widest, in {far}"
              if not run and far != end and abs(rel[far]) > abs(r) + 2 else "")
    where = (f"level with {nb}" if abs(r) < 1 else f"{abs(r):.0f}% {'ahead of' if r > 0 else 'behind'} {nb}")
    is_ = "are" if a["id"] in PLURAL else "is"
    lead = f"{verdict(r)}, measured from {start}: {na} {is_} {where}{run or widest}."
    line = (f"Rebased to {start} = 100, {na} reached {A[end]:.0f} by {end} and {nb} {B[end]:.0f}: "
            f"{na} {pct(ga)}, {nb} {pct(gb)}. {faster}.")
    if cfg.get("also"):
        s2, e2, A2, B2, _, rel2 = rebase(cfg["also"])
        r2 = rel2[e2]
        lead += f" From {s2}, {'they are' if a['id'] in PLURAL else 'it is'} {abs(r2):.0f}% {'ahead' if r2 > 0 else 'behind'}."
        line += (f" Measured from {s2} instead, {na} {pct(A2[e2] - 100)} and {nb} {pct(B2[e2] - 100)}, "
                 f"so {na} ended {abs(r2):.0f}% {'ahead of' if r2 > 0 else 'behind'} {nb}: the start year changes the answer.")
    return {"kind": "ratio", "lead": lead, "sentence": line, "start": start, "end": end, "baseline": 100,
            "unit": f"index, {start} = 100", "explore": f"{a['id']},{b['id']}~line~index~{start}~{end}~pm",
            "sets": [{"id": s["id"], "name": CHART_NAMES.get(s["id"], s["name"]), "pts": [[y, round(R[y], 3)] for y in sorted(R)]}
                     for s, R in ((a, A), (b, B))]}


def q_same_unit(cfg: dict, by_id: dict, refs: dict) -> dict:
    """Debt in % of GDP beside interest in £m: put interest into % of GDP too,
    and derive the effective rate, interest ÷ debt."""
    debt, intr = (by_id[i] for i in cfg["ids"])
    if not (debt["unit"].startswith("% of GDP") and intr["kind"] == "money_cash" and intr["unit"].startswith("£m")):
        raise ValueError("same_unit expects a % of GDP stock and a £m cash flow")
    g = refs["gdp"]
    gdp = {g["start"] + i: v for i, v in enumerate(g["values"]) if v}
    D = {y: v for y, v in full_points(debt) if y >= cfg["from"]}
    I = {y: v for y, v in full_points(intr) if y >= cfg["from"]}
    years = sorted(y for y in D if y in I and y in gdp)
    start, end = years[0], years[-1]
    ish = {y: I[y] / gdp[y] * 100 for y in years}                     # interest, % of GDP
    eff = {y: I[y] / (D[y] / 100 * gdp[y]) * 100 for y in years}      # interest ÷ debt
    low = min(years, key=lambda y: eff[y])
    peak_i = max(years, key=lambda y: ish[y])
    f1 = lambda v: f"{v:.1f}"
    xi, xd = ish[end] / ish[start], D[end] / D[start]
    rise = ("a much smaller rise than the debt’s" if xi < xd * 0.7 else
            "a bigger rise than the debt’s" if xi > xd * 1.3 else "about the same rise as the debt’s")
    lead = (f"{f1(ish[end])}% of GDP in {end}: the interest bill is up from {f1(ish[start])}% in {start}, {rise}, "
            f"which went from {f1(D[start])}% to {f1(D[end])}% of GDP.")
    line = (f"In {start} net debt was {f1(D[start])}% of GDP and the interest on it cost {f1(ish[start])}% of GDP. "
            f"By {end} the debt was {f1(D[end])}% of GDP, {xd:.1f} times its {start} share of the economy, "
            f"but interest cost {f1(ish[end])}% — {xi:.1f} times"
            + (f", and it peaked at {f1(ish[peak_i])}% in {peak_i}" if peak_i not in (start, end) else "")
            + f". The difference is the rate: interest ÷ debt, the effective rate the state pays, "
            f"went from {f1(eff[start])}% in {start} to a low of {f1(eff[low])}% in {low}"
            + (f", and is back to {f1(eff[end])}% in {end}." if low != end else ".")
            + " Interest and debt are both set against the size of the economy here, so rising prices and growth"
            " do not flatter or inflate either one.")
    return {"kind": "same_unit", "lead": lead, "sentence": line, "start": start, "end": end, "baseline": None, "zero": True,
            "unit": "% of GDP, and % of the debt", "explore": f"{debt['id']},{intr['id']}~line~pctgdp~{start}~{end}~pm",
            "sets": [{"id": "debtint_gdp", "name": "Debt interest, % of GDP",
                      "pts": [[y, round(ish[y], 3)] for y in years]},
                     {"id": "effrate", "name": "Interest ÷ debt, the effective rate",
                      "pts": [[y, round(eff[y], 3)] for y in years]}]}


def q_before_after(cfg: dict, by_id: dict) -> dict:
    main, other = (by_id[i] for i in cfg["ids"])
    bef, aft, ev = cfg["before"], cfg["after"], cfg["event"]

    def frame(s):
        pts = {y: v for y, v in full_points(s) if y >= cfg["from"]}
        b = max(y for y in pts if y <= bef)
        a = min(y for y in pts if y >= aft)
        return pts, b, a, max(pts)

    def crossing(s, b, a):
        return [d for d in s.get("discontinuities") or [] if b < int(d.get("year", 0)) <= a]

    yl = lambda s, y: year_label(y, s.get("year_basis", "calendar"))
    num = lambda s, v: f"{v:.1f}%" if (s.get("unit") or "").startswith("%") else f"{v:.2f}"

    P, b, a, l = frame(main)
    e = min(P)
    up, down = cfg.get("words", {}).get(main["id"], ("rose", "fell"))
    nm = qname(main)
    worse = P[a] > P[b]
    lead = (f"The gap {'did widen' if worse else 'did not widen'} after {ev}, "
            f"{'from' if worse else 'staying at'} {num(main, P[b])} in {yl(main, b)}"
            + (f" to {num(main, P[a])} in {yl(main, a)}" if worse else f" against {num(main, P[a])} in {yl(main, a)}")
            + ", but these figures cannot show whether lost schooling was the cause.")
    parts = [f"{cap(nm)} {down if P[b] < P[e] else up} from {num(main, P[e])} in {yl(main, e)} "
             f"to {num(main, P[b])} in {yl(main, b)}, the last year before {ev}."]
    ch = (P[a] / P[b] - 1) * 100
    parts.append(f"When it was next measured, in {yl(main, a)}, it was {num(main, P[a])}, "
                 f"{'up' if ch >= 0 else 'down'} {abs(ch):.0f}% on {yl(main, b)}, and it is {num(main, P[l])} in {yl(main, l)}.")
    if (P[b] - P[e]) * (P[l] - P[b]) < 0 and P[e] != P[b]:
        share = (P[l] - P[b]) / (P[e] - P[b]) * 100
        noun = (down if P[b] < P[e] else up)[:-2] + "ing"                # narrowed -> narrowing
        parts.append(f"That is more than the whole of the {noun} before it." if share >= 100 else
                     f"That undoes {share:.0f}% of the {noun} between {yl(main, e)} and {yl(main, b)}.")
    O, ob, oa, ol = frame(other)
    peak = max((y for y in O if y >= oa), key=lambda y: O[y])
    on = qname(other)
    parts.append(f"{cap(on)} was {num(other, O[ob])} of pupils in {yl(other, ob)}" if (other.get("unit") or "").startswith("%")
                 else f"{cap(on)} was {num(other, O[ob])} in {yl(other, ob)}")
    parts[-1] += (f" and peaked at {num(other, O[peak])} in {yl(other, peak)}; it is {num(other, O[ol])} in {yl(other, ol)}."
                  if peak != ol else f" and is {num(other, O[ol])} in {yl(other, ol)}.")
    # any break between "before" and "after" is said, in one clause
    brk = []
    for s, (sb, sa) in ((main, (b, a)), (other, (ob, oa))):
        for d in crossing(s, sb, sa):
            lab = d.get("label") or "the series breaks"
            lab = lab[0].lower() + lab[1:]                                      # keep KS2 as KS2
            brk.append(f"{qname(s)} ({lab}{'' if re.search(r'[0-9]{4}', lab) else ' in ' + str(d['year'])})")
    if brk:
        parts.append(("Neither series is" if len(brk) > 1 else "The series is not") +
                     f" measured identically either side of {ev}: " + " and ".join(brk) +
                     ", so compare the before and after figures with care.")
    start = min(min(P), min(O))
    end = max(l, ol)
    sets = []
    for s, pts, base in ((main, P, b), (other, O, ob)):
        sets.append({"id": s["id"], "name": CHART_NAMES.get(s["id"], s["name"]),
                     "pts": [[y, round(pts[y] / pts[base] * 100, 3) if y in pts else None] for y in range(start, end + 1)]})
    breaks = [{"year": int(d["year"]), "label": d.get("label", "")} for s in (main, other)
              for d in (s.get("discontinuities") or [])]
    return {"kind": "before_after", "lead": lead, "sentence": " ".join(parts), "start": start, "end": end, "baseline": 100,
            "unit": f"index, {yl(main, b)} = 100", "band": [b + 1, a, ev], "breaks": breaks,
            "explore": f"{main['id']},{other['id']}~line~index~{start}~{end}~pm", "sets": sets}


def build_question(slug: str, by_id: dict, refs: dict) -> dict | None:
    cfg = QUESTIONS.get(slug)
    if not cfg or any(i not in by_id for i in cfg["ids"]):
        return None
    fn = {"ratio": q_ratio, "before_after": q_before_after}.get(cfg["kind"])
    q = q_same_unit(cfg, by_id, refs) if cfg["kind"] == "same_unit" else fn(cfg, by_id)
    q["names"] = {s["id"]: s["name"] for s in q["sets"]}
    return q


def write_questions(by_id: dict, refs: dict) -> dict:
    """Work out the featured questions; data/questions.json carries the numbers
    for the homepage's thumbnails and the share-image builder."""
    out = {}
    for slug in QUESTIONS:
        q = build_question(slug, by_id, refs)
        if not q:
            print(f"  question {slug}: a series is missing, left out")
            continue
        out[slug] = q
    (ROOT / "data" / "questions.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


# The hand-written half of each featured page: what people claim, what the
# numbers can and cannot show, and the caveat. The answer and the chart come
# from the data, above.
FEATURED = {
    "has-pay-kept-up-with-prices": dict(
        q="Has pay kept up with prices?", title="Has pay kept up with prices in the UK?",
        claim="Pay has not kept up with the cost of living.",
        shows=["This is the whole-economy average, so it answers the question for the economy and not for any "
               "particular person. A mean is pulled up by high earners; it moves when the mix of who is employed "
               "changes, not only when anyone gets a rise.",
               "And it is cumulative from the start year. From 2008, the year most people mean, pay spent twelve "
               "years behind prices; from 2000 it was ahead the whole time. Both are true, which is why both are here."],
        why="Two growth rates from one start: rebasing both to 100 in the same year shows which pulled ahead, and "
            "when. The start year decides the answer, so the page gives the answer from a second one too.",
        care="CPIH includes owner-occupiers’ housing costs, which CPI does not, and runs below CPI in most periods — "
             "the choice of price index changes the answer. Earnings here are total pay including bonuses, "
             "seasonally adjusted."),
    "have-rents-outrun-pay": dict(
        q="Have rents outrun pay?", title="Have rents outrun pay in the UK?",
        claim="Rents are rising faster than wages.",
        shows=["An index of rents on new and existing tenancies is not the same as what a mover pays. Advertised "
               "rents for new lets have risen faster than this index over the same years, because existing "
               "tenancies reprice slowly. So this understates the change facing someone moving today, and "
               "overstates it for someone who has not moved."],
        why="Rents and pay are in different units; rebasing both to 2015 = 100, the first year the rents index "
            "covers, makes their growth comparable on one axis.",
        care="<b>The index you pick changes the answer.</b> This page used ONS’s old Index of Private Housing Rental "
             "Prices until it stopped in March 2025. Over 2015 to 2024, the years both cover, that index had rents up "
             "23%; its replacement, the Price Index of Private Rents used here, has them up 37%. PIPR is published as "
             "official statistics in development, so ONS may still revise it, and it is UK-wide, which hides a wide "
             "spread between London and everywhere else.", care_html=True),
    "what-does-the-debt-cost-to-carry": dict(
        q="What does the debt cost to carry?", title="What does UK government debt cost to carry?",
        claim="Government debt is at a record high, so debt interest must be too.",
        shows=["Two different kinds of number, made comparable. Debt is a stock measured at a point in time; interest "
               "is a flow paid across a year, so in cash the two cannot be set side by side. Against GDP, the interest "
               "bill is what weighs on a budget; against the debt, it is the price of borrowing.",
               "A bigger debt costs more to carry only if that price holds, and when rates move the bill follows with "
               "a lag, as old borrowing is refinanced."],
        why="Both lines are percentages: interest as a share of the economy, and as a share of the debt. On one axis "
            "from zero, the space between them is the price of borrowing.",
        care="Both series exclude public sector banks. Debt interest is interest and dividends paid to the private "
             "sector and the rest of the world, and a large share of it in recent years reflects RPI uplift on "
             "index-linked gilts rather than coupon payments. The effective rate is approximate: it divides interest "
             "paid across a year by the debt at the end of it."),
    "did-lost-schooling-widen-the-gap": dict(
        q="Did lost schooling widen the attainment gap?", title="Did lost schooling widen the attainment gap in England?",
        claim="Absence since the pandemic has widened the gap between disadvantaged pupils and everyone else.",
        shows=["Two lines moving at the same time. It does not show that one caused the other, and nothing on this "
               "chart could: absence and attainment share most of their plausible causes, and pupils missing school "
               "are disproportionately the same pupils the gap index measures. Read it as a question worth asking "
               "of the underlying data, not as an answer."],
        why="Each series is set to 100 in 2018/19, the last year before the pandemic, so the change after it reads "
            "the same way for both. The shaded years are the ones the pandemic interrupted.",
        care="England only, and academic years, which plot at their starting calendar year — a point labelled 2020 is "
             "the 2020/21 school year. Both series changed collection or definition during the pandemic, so the break "
             "either side of 2020 is partly a change in measurement."),
}


def featured_items(featured: dict, by_id: dict) -> list[dict]:
    """The featured questions in the shape every question page is written from."""
    out = []
    for slug, fq in featured.items():
        text = FEATURED.get(slug)
        if not text:
            continue
        cfg = QUESTIONS[slug]
        series = [by_id[i] for i in cfg["ids"]]
        sets = fq["sets"]
        ys = [y for s in sets for y, v in s["pts"] if v is not None]
        out.append({
            **text, "key": slug, "slug": slug, "group": "featured", "chart": "line", "era": "off",
            "trans": "none" if fq.get("zero") else "index", "zero": bool(fq.get("zero")),
            "ids": cfg["ids"], "sets": sets, "band": fq.get("band"),
            "from": fq["start"], "to": fq["end"], "x0": min(ys), "x1": max(ys), "unit": fq["unit"],
            "lead": fq["lead"], "sentence": fq["sentence"], "description": more_questions.description(fq["lead"]),
            "geos": list(dict.fromkeys(s.get("geography", "") for s in series if s.get("geography"))),
            "sources": list(dict.fromkeys(s.get("source", "") for s in series)),
            "topics": list(dict.fromkeys(t for s in series for t in (s.get("topics") or []))),
            "explore": fq["explore"],
        })
    return out


# ── the drawer's questions, each a page of its own ──────────────────
# The homepage shows these in a drawer, drawn in the page; that is the
# better way to browse them, but a search engine sees one URL for all of
# them and a shared link previews as the homepage. So each also gets a
# plain page here, written from the same computed answer and numbers: the
# question as its heading, the answer first, the chart drawn as SVG, the
# caveat, and links to its indicators and to the other questions.

# every question, featured and not, and the questions each indicator is in;
# filled by write_more_questions before the indicator and topic pages
ALL_QUESTIONS: list[dict] = []
ASKED: dict[str, list[dict]] = {}
GENERATED = "<!-- written by ingest/pages.py (questions: FEATURED there, the rest in ingest/questions.py): edit there, not here -->"

Q_CSS = """
:root{--s1:#6D4AE0;--s2:#0E9384;--s3:#D97706;--s4:#DB2777}
html[data-theme="dark"]{--s1:#8367E8;--s2:#17A394;--s3:#C58207;--s4:#DE5A96}
.kick{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;color:var(--muted);margin:0 0 10px}
.tag{font-weight:600;color:var(--purple);background:var(--soft);border:1px solid var(--prule);border-radius:100px;padding:2px 10px}
h1{max-width:24ch}
.lead{font-size:19px;line-height:1.5;font-weight:600;max-width:62ch;margin:8px 0 24px}
.claim{font-size:17px;font-style:italic;color:var(--muted)}
.card .cap.top{margin:0 0 8px}
.key{display:inline-flex;align-items:center;gap:5px;margin-right:12px;font-weight:600;color:var(--ink)}
.key i{width:9px;height:9px;border-radius:2px;display:inline-block}
.card .gridline{stroke:var(--rule);stroke-width:1;opacity:.7}
.card .baseline{stroke:var(--muted);stroke-width:1;opacity:.75}
.card .axlabel,.card .axunit,.card .endlbl,.card .endval,.card .bandlbl,.card .qnote,.card .qsmt,.card .qyr{font-family:"IBM Plex Sans",system-ui,sans-serif;font-variant-numeric:tabular-nums}
.card .axlabel{font-size:11.5px;fill:var(--muted)}.card .axlabel.strong{font-weight:600;fill:var(--ink)}
.card .axunit{font-size:11.5px;font-weight:500;fill:var(--muted)}
.card .line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.card .endlbl{font-size:11px;font-weight:600}.card .endval{font-size:11px;fill:var(--muted)}
.card .enddot,.card .qdot{stroke:var(--surface);stroke-width:1.5}.card .hollow{fill:var(--surface)}
.card .leader{fill:none;stroke-width:1;opacity:.45}
.card .band{fill-opacity:.07}html[data-theme="dark"] .card .band{fill-opacity:.09}
.card .banddiv{stroke:var(--rule);stroke-width:1}.card .bandlbl{font-size:10px;font-weight:500;fill:var(--muted)}
.card .qmean{stroke:var(--ink);stroke-width:1.2;stroke-dasharray:5 4;opacity:.5}
.card .qnote{font-size:11px;font-weight:600;fill:var(--muted)}.card .qnote.strong{fill:var(--ink)}
.card .qsmt{font-size:12px;font-weight:700}.card .qyr{font-size:10.5px;fill:var(--muted)}
.why{background:var(--soft);border:1px solid var(--prule);border-radius:12px;padding:14px 16px;margin:0 0 6px}
.why h2{margin:0 0 6px;font-size:16px}
.care h2{color:var(--warn)}
.list .tg{color:var(--purple);font-weight:600}
/* the chart is drawn twice at build time, wide and phone-sized, so its
   labels stay readable rather than shrinking with the screen */
.qnarrow{display:none}
@media(max-width:600px){.qwide{display:none}.qnarrow{display:block}.card{padding:14px 12px}}
"""


def asked_list(items: list[dict], depth: int, heading: str) -> str:
    if not items:
        return ""
    up = "../" * depth
    li = "".join(f'<li><a href="{up}q/{q["slug"]}/"><b>{esc(q["title"])}</b>'
                 f'<span>{esc(more_questions.GROUP_NAME.get(q["group"], "Answered in depth"))}</span></a></li>'
                 for q in items)
    return f'<h2 style="margin-top:44px">{esc(heading)}</h2><ul class="list">{li}</ul>'


def question_page(q: dict, db: dict, by_id: dict, slugs: dict) -> str:
    url = f'q/{q["slug"]}/'
    tname = more_questions.TYPE_NAME[q["chart"]]
    geos = ", ".join(q["geos"])
    keys = ""
    if q.get("signs"):
        keys = "".join(f'<span class="key"><i style="background:var(--s{k + 1})"></i>{esc(n)}</span>'
                       for k, n in enumerate(q["signs"]))
    series = [by_id[i] for i in q["ids"]]
    inds = "".join(card(s, f'../../indicator/{slugs[s["id"]]}/') for s in series)
    def src_dd(x: dict) -> str:
        name = esc(x.get("source", ""))
        return f'<dd><a href="{esc(x["source_url"])}">{name}</a></dd>' if x.get("source_url") else f"<dd>{name}</dd>"
    src = "".join(src_dd(x) for x in {x.get("source"): x for x in series}.values())
    fetched = max((s.get("fetched") or "")[:10] for s in series)
    others = [x for x in ALL_QUESTIONS if x["slug"] != q["slug"]]
    others.sort(key=lambda x: (x["group"] != q["group"], not set(x["topics"]) & set(q["topics"]), x["title"]))
    an = "an" if tname[0].lower() in "aeiou" else "a"
    care = q["care"] if q.get("care_html") else esc(q["care"])
    claim = f'<h2>The claim</h2><p class="claim">{esc(q["claim"])}</p>' if q.get("claim") else ""
    shows = (f'<h2>What it actually shows</h2>' + "".join(f"<p>{esc(t)}</p>" for t in q["shows"])) if q.get("shows") else ""
    back = "../../#questions" if q["group"] == "featured" else f"../../#q-{q['key']}"
    body = f"""{GENERATED}
{crumbs(2, [("Questions", "q/"), (q["title"], None)])}
<p class="kick"><span class="tag">{esc(more_questions.GROUP_NAME[q['group']])}</span>{esc(tname)} chart · {esc(geos)} · {q['x0']}–{q['x1']}</p>
<h1>{esc(q['title'])}</h1>
<p class="lead">{esc(q['lead'])}</p>
<div class="card">{f'<p class="cap top">{keys}</p>' if keys else ''}
<div class="qwide">{more_questions.svg(q, db)}</div><div class="qnarrow">{more_questions.svg(q, db, 420)}</div>
<p class="cap">Source: {esc("; ".join(q['sources']))} · Open Government Licence v3.0{' · a year still in progress is left out' if any(s.get('partial') for s in series) else ''}</p></div>
<a class="cta" href="../../explore.html#p={q['explore']}">Open this in the explorer →</a>
<a class="cta ghost" href="{back}">See it with the other questions</a>
<div class="cols"><div>
{claim}
<h2>The numbers</h2>
<p>{esc(q['sentence'])}</p>
{shows}
<div class="why" style="margin-top:24px"><h2>Why {an} {esc(tname.lower())}{'' if q['chart'] == 'small' else ' chart'}</h2><p>{esc(q['why'])}</p></div>
<h2 style="margin-top:28px">The indicators</h2>
<ul class="list">{inds}</ul>
</div>
<aside class="side care"><h2>Read it carefully</h2><p>{care}</p><dl>
<dt>Covers</dt><dd>{esc(geos)}</dd>
<dt>Years</dt><dd>{q['x0']}–{q['x1']}</dd>
<dt>Shown as</dt><dd>{esc(q['unit'])}</dd>
<dt>Sources</dt>{src}
<dt>Last fetched</dt><dd>{esc(fetched)}</dd>
<dt>Licence</dt><dd><a href="{OGL}">Open Government Licence v3.0</a></dd>
</dl></aside></div>
{asked_list(others[:9], 2, "More questions")}
<p style="margin-top:14px"><a href="../">Every question →</a></p>"""
    og = f'og/{q["slug"]}.png' if (ROOT / "og" / f'{q["slug"]}.png').exists() else "og/home.png"
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": q["title"], "url": f"{SITE}/{url}",
           "description": q["description"], "inLanguage": "en-GB", "license": OGL,
           "primaryImageOfPage": {"@type": "ImageObject", "url": f"{SITE}/{og}", "width": 1200, "height": 630},
           "about": [{"@type": "Dataset", "name": f'{s["name"]} ({s.get("geography", "UK")})',
                      "url": f'{SITE}/indicator/{slugs[s["id"]]}/'} for s in series],
           "isPartOf": {"@type": "WebSite", "name": "Polyoptic", "url": f"{SITE}/"}},
          {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{
              "@type": "Question", "name": q["title"],
              "acceptedAnswer": {"@type": "Answer", "text": f'{q["lead"]} {q["sentence"]}'}}]},
          breadcrumb_ld([("Questions", "q/"), (q["title"], url)])]
    return page(path=url, depth=2, title=f'{q["title"]} | Polyoptic', desc=q["description"], og_image=og,
                og_alt=q["title"], ld=ld, body=body, explore=f'explore.html#p={q["explore"]}', css=Q_CSS)


def hub_page() -> str:
    groups = [(n, [q for q in ALL_QUESTIONS if q["group"] == k]) for k, n in more_questions.GROUP_NAME.items()]
    body = f"""{GENERATED}
{crumbs(1, [("Questions", None)])}
<h1>Questions worth asking</h1>
<p class="sub">{len(ALL_QUESTIONS)} questions people actually ask about the UK, answered with the official numbers: each with its chart, the caveats and a link to the working.</p>
""" + "".join(f'<div class="grp">{esc(n)} · {len(qs)}</div><ul class="list">'
              + "".join(f'<li><a href="{q["slug"]}/"><b>{esc(q["title"])}</b><span>{esc(q["description"])}</span></a></li>' for q in qs)
              + "</ul>" for n, qs in groups if qs)
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Questions worth asking", "url": f"{SITE}/q/",
           "description": "Questions about the UK answered with official statistics.",
           "isPartOf": {"@type": "WebSite", "name": "Polyoptic", "url": f"{SITE}/"}},
          breadcrumb_ld([("Questions", "q/")])]
    return page(path="q/", depth=1, title="Questions worth asking about the UK, answered with official statistics | Polyoptic",
                desc=f"{len(ALL_QUESTIONS)} questions about the UK — crime, the NHS, migration, housing, pay and more — answered with official statistics, each with its chart and caveats.",
                og_image="og/home.png", og_alt="Polyoptic", ld=ld, body=body, og_type="website")


def write_more_questions(db: dict, by_id: dict, slugs: dict, featured: dict) -> None:
    """Every question page — the four featured and the drawer's — the hub that
    lists them, the drawer's data for the homepage, and its plain links."""
    qs = more_questions.build(db)
    (ROOT / "data" / "questions-more.json").write_text(
        json.dumps({"questions": qs}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # every question, so indicator, topic and question pages can link to them
    ALL_QUESTIONS.clear()
    ALL_QUESTIONS.extend(featured_items(featured, by_id))
    ALL_QUESTIONS.extend(qs)
    ASKED.clear()
    for q in ALL_QUESTIONS:
        for i in q["ids"]:
            ASKED.setdefault(i, []).append(q)

    # a question taken out takes its page with it; a page this did not write
    # is never touched
    live = {q["slug"] for q in ALL_QUESTIONS}
    for p in sorted((ROOT / "q").glob("*/index.html")):
        if p.parent.name not in live and "<!-- written by ingest/pages.py" in p.read_text(encoding="utf-8"):
            shutil.rmtree(p.parent)
    for q in ALL_QUESTIONS:
        out = ROOT / "q" / q["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(question_page(q, db, by_id, slugs), encoding="utf-8")
    (ROOT / "q" / "index.html").write_text(hub_page(), encoding="utf-8")

    # The homepage builds its drawer from the JSON, but a crawler that does
    # not run scripts should still find every question: the same links,
    # written into the drawer's list, which the script then replaces.
    home = ROOT / "index.html"
    text = home.read_text(encoding="utf-8")
    links = "".join(f'\n        <a class="qstatic" href="q/{q["slug"]}/">{esc(q["title"])}</a>' for q in qs)
    new = re.sub(r"(<!-- more-questions -->).*?(\s*<!-- /more-questions -->)",
                 lambda m: m.group(1) + links + m.group(2), text, count=1, flags=re.S)
    if new != text:
        home.write_text(new, encoding="utf-8")
    print(f"  questions: {len(ALL_QUESTIONS)} pages, {len(qs)} of them in the homepage drawer")


# Indicator pages whose address changed when the series was renamed or
# merged. Each old address gets a small page that forwards to the new one, so
# a link someone already shared still lands.
MOVED = {
    "private-rents-index-iphrp": "rents",
    "employment-rate": "emprate",
    "economic-inactivity-rate": "inactive",
    "persistent-absences-for-all-pupils": "absence",
}


def write_moved(slugs: dict) -> None:
    for old, sid in MOVED.items():
        new = slugs.get(sid)
        if not new or new == old:
            continue
        d = ROOT / "indicator" / old
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            f'<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><title>Moved</title>'
            f'<link rel="canonical" href="{SITE}/indicator/{new}/">'
            f'<meta http-equiv="refresh" content="0; url=../{new}/"><meta name="robots" content="noindex"></head>'
            f'<body><p>This indicator has moved to <a href="../{new}/">its new page</a>.</p></body></html>',
            encoding="utf-8")


# ── the sitemap ─────────────────────────────────────────────────────

def sitemap(entries: list[tuple[str, str, str, str]]) -> str:
    rows = "".join(f"  <url><loc>{SITE}/{p}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>\n"
                   for p, m, c, pr in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            "<!-- Written by ingest/pages.py. board.html is deliberately absent: it is a\n"
            "     working page, not a published one, and carries noindex to match. -->\n"
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n")


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
REF_NAMES = {"population": "UK population (mid-year estimate)",
             "deflator": "GDP deflator (ONS implied, L8GG)", "gdp": "Nominal GDP (YBHA)"}


def endpoint_short(u: str) -> tuple[str, str]:
    """The address, short enough for a column: the host, then the part that
    names the series. Mirrors endpointShort() in data.html."""
    from urllib.parse import urlsplit, parse_qs
    try:
        x = urlsplit(u or "")
    except ValueError:
        return "", u or ""
    host = re.sub(r"^www\.", "", x.hostname or "")
    q = parse_qs(x.query)
    if q.get("indicator"):
        tail = q["indicator"][0]
    elif q.get("uri"):
        tail = ([p for p in q["uri"][0].split("/") if p] or [""])[-1]
    else:
        seg = [p for p in x.path.split("/") if p]
        tail = "/".join(seg[-3:] if len(seg) >= 3 and len(seg[-1]) < 6 else seg[-1:])
    if len(tail) > 40:
        tail = tail[:20] + "…" + tail[-17:]
    return host, tail


def write_fetchlog(db: dict, slugs: dict) -> None:
    """The fetch log (data.html) draws itself from bundle.json in the browser.
    Write the same run summary, alerts and rows into the page as well, so it
    reads without JavaScript and search engines see it; the script redraws
    them as soon as it runs. Keep in step with rowHtml() in data.html."""
    f = ROOT / "data.html"
    h = f.read_text()
    m = db.get("meta") or {}
    gen = m.get("generated") or ""
    build_year = int(gen[:4]) if gen[:4].isdigit() else datetime.now(timezone.utc).year

    def when(iso: str, time: bool = True) -> str:
        g = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?", iso or "")
        if not g:
            return "—"
        yr = "" if int(g[1]) == build_year else f" {g[1]}"
        return f"{int(g[3])} {MONTHS[int(g[2]) - 1]}{yr}" + (f", {g[4]}:{g[5]}" if g[4] and time else "")

    def latest(s: dict) -> tuple[str, bool]:
        p = s.get("partial") or {}
        if p.get("value") is not None and p.get("year"):
            span = (p.get("label") or "").split("–")[-1] if p.get("how") == "last" else (p.get("label") or "")
            return f"{span} {p['year']}".strip(), p["year"] < build_year - 2
        vals = s.get("values") or []
        i = len(vals) - 1
        while i >= 0 and vals[i] is None:
            i -= 1
        if i < 0:
            return "—", False
        y = s["start"] + i
        return year_label(y, s.get("year_basis", "calendar")), y < build_year - 2

    failed = set(m.get("failed") or [])
    status = lambda s: "fail" if s["id"] in failed else "stale" if s.get("stale") else "ok"
    LABEL = {"ok": "Fetched", "stale": "Last good copy", "fail": "Failed"}

    def row(s: dict, ref: bool = False) -> str:
        st, (lt, old) = status(s), latest(s)
        host, tail = endpoint_short(s.get("source_api") or "")
        sl = None if ref else slugs.get(s["id"])
        name = f'<a class="pglink" href="indicator/{sl}/">{esc(s["name"])}</a>' if sl else esc(s["name"])
        ep = (f'<a class="ep" href="{esc(s["source_api"])}" title="{esc(s["source_api"])}"><span>{esc(host)}</span>'
              f'{" › " + esc(tail) if tail else ""}</a>' if s.get("source_api") else "—")
        return (f'<tr><td class="cx"></td><td><span class="st st-{st}">{LABEL[st]}</span></td>'
                f'<td class="cname">{name}</td><td class="c-pub">{esc(s.get("publisher") or s.get("source") or "Unknown")}</td>'
                f'<td class="c-ep">{ep}</td><td class="cmono c-fe{"" if st == "ok" else " warm"}">{esc(when(s.get("fetched")))}</td>'
                f'<td class="cmono{" old" if old else ""}">{esc(lt)}</td></tr>')

    head = ('<thead><tr><th></th><th>Status</th><th>Series</th><th class="c-pub">Publisher</th>'
            '<th class="c-ep">Endpoint</th><th class="c-fe">Fetched</th><th>Latest data</th></tr></thead>')
    # problems first, then the newest fetch: the order a log reads in
    rank = {"fail": 0, "stale": 1, "ok": 2}
    ordered = sorted(db["series"], key=lambda s: s.get("fetched") or "", reverse=True)
    ordered.sort(key=lambda s: rank[status(s)])
    table = (f'<div class="tblwrap"><table class="idx log">{head}<tbody>'
             f'{"".join(row(s) for s in ordered)}</tbody></table></div>')
    refs = [{"id": k, "name": REF_NAMES.get(k, k), "values": r.get("values") or [], "start": r.get("start"),
             "publisher": "ONS", "source_api": r.get("source_api"), "fetched": gen, "year_basis": "calendar"}
            for k, r in (db.get("refs") or {}).items()]
    reftbl = (f'<div class="tblwrap"><table class="idx log">{head}<tbody>'
              f'{"".join(row(s, True) for s in refs)}</tbody></table></div>')

    stale = [s for s in db["series"] if s.get("stale")]
    dropped = m.get("dropped") or []
    prov = m.get("provenance") or "unknown"
    gd = datetime.fromisoformat(gen) if gen else datetime.now(timezone.utc)
    nxt = gd.replace(hour=6, minute=0, second=0, microsecond=0)
    add = (7 - nxt.weekday()) % 7                    # Monday is 0
    if add == 0 and nxt <= gd:
        add = 7
    from datetime import timedelta
    nxt += timedelta(days=add)
    hot = lambda n: " hot" if n else ""
    run = (f'<div class="rs"><i>Data</i><b><span class="dot{"" if prov == "live" else " warn"}"></span>'
           f'{"Live" if prov == "live" else esc(prov.capitalize())}</b></div>'
           f'<div class="rs"><i>Last refresh</i><b>{esc(when(gen))} UTC</b></div>'
           f'<div class="rs"><i>Series fetched</i><b>{len(db["series"]) - len(stale)}</b></div>'
           f'<div class="rs{hot(stale)}"><i>Last good copy</i><b>{len(stale)}</b></div>'
           f'<div class="rs{hot(dropped)}"><i>Not available</i><b>{len(dropped)}</b></div>'
           f'<div class="rs"><i>Next refresh</i><b>Mon {nxt.day} {MONTHS[nxt.month - 1]}, 06:00 UTC</b></div>'
           f'<a class="rsl" href="data/bundle.json">bundle.json ↗</a>')
    warn = []
    if stale:
        warn.append("<b>Couldn’t refresh, showing the last good copy:</b> " + ", ".join(
            esc(s["name"] + (f' (fetched {when(s.get("fetched"), False)})' if s.get("fetched") else "")) for s in stale))
    if dropped:
        warn.append(f"<b>Not available yet:</b> {esc(', '.join(dropped))}")
    alerts = "".join(f'<div class="valert">{w}</div>' for w in warn)

    for key, html_ in (("run", run), ("alerts", alerts), ("table", table), ("refs", reftbl)):
        h, k = re.subn(rf"<!-- log:{key} -->.*?<!-- /log:{key} -->",
                       lambda _m: f"<!-- log:{key} -->{html_}<!-- /log:{key} -->", h, count=1, flags=re.S)
        if not k:
            print(f"  fetch log: no <!-- log:{key} --> marker in data.html, left as it was")
    f.write_text(h)


def main() -> None:
    db = json.loads((ROOT / "data" / "bundle.json").read_text())
    ix_path = ROOT / "data" / "areas" / "index.json"
    ix = json.loads(ix_path.read_text()) if ix_path.exists() else {}
    series = [s for s in db["series"] if points(s)]
    by_id = {s["id"]: s for s in series}
    pubs = {p["short"]: p.get("url", "") for p in db.get("publishers", [])}

    # one slug per series, from its name; a clash takes the id as well
    slugs, seen = {}, set()
    for s in sorted(series, key=lambda x: x["id"]):
        sl = slugify(s["name"]) or s["id"]
        if sl in seen:
            sl = f'{sl}-{s["id"]}'
        seen.add(sl); slugs[s["id"]] = sl

    featured = write_questions(by_id, db.get("refs", {}))
    write_more_questions(db, by_id, slugs, featured)

    for d in ("indicator", "topic"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    today = datetime.now(timezone.utc).date().isoformat()
    # The host serves /explore, /data and /about, and redirects the .html
    # addresses to them, so the sitemap names the addresses that answer
    # directly. Links between pages keep .html, which also works from a
    # local file server.
    entries = [("", today, "weekly", "1.0"), ("explore", today, "weekly", "0.9"),
               ("indicator/", today, "weekly", "0.8"), ("data", today, "weekly", "0.7"),
               ("about", today, "monthly", "0.5")]
    entries.append(("q/", today, "weekly", "0.8"))
    entries += [(f"q/{p.parent.name}/", today, "weekly", "0.7") for p in sorted((ROOT / "q").glob("*/index.html"))]

    for k, name, blurb in TOPICS:
        ts = [s for s in series if k in (s.get("topics") or [])]
        if not ts:
            continue
        out = ROOT / "topic" / k
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(topic_page(k, name, blurb, ts, slugs))
        entries.append((f"topic/{k}/", today, "weekly", "0.8"))

    for s in series:
        out = ROOT / "indicator" / slugs[s["id"]]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(indicator_page(s, slugs[s["id"]], by_id, slugs, ix, pubs))
        (out / "data.csv").write_text(csv_text(s))
        entries.append((f"indicator/{slugs[s['id']]}/", (s.get("fetched") or today)[:10], "weekly", "0.6"))

    write_moved(slugs)
    write_fetchlog(db, slugs)

    (ROOT / "indicator" / "index.html").write_text(index_page(series, slugs))
    (ROOT / "data" / "pages.json").write_text(json.dumps(slugs, separators=(",", ":")))
    (ROOT / "sitemap.xml").write_text(sitemap(entries))
    print(f"pages: {len(series)} indicators, {sum(1 for e in entries if e[0].startswith('topic/'))} topics, sitemap {len(entries)} urls")


if __name__ == "__main__":
    main()
