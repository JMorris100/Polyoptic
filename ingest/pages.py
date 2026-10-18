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

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://polyoptic.co"
OGL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"

TOPICS = [
    ("economy", "Economy", "Prices, pay, jobs, productivity, business, trade and the public finances."),
    ("housing", "Housing", "Prices, rents, affordability, housebuilding, homelessness and waiting lists."),
    ("education", "Education", "Pupils, teachers, absence, GCSEs, early years, apprenticeships and NEET."),
    ("health", "Health", "NHS waiting lists, A&E, GPs, obesity, smoking, life expectancy and wellbeing."),
    ("crime", "Crime & justice", "Survey and recorded crime, charge rates, homicide, courts, prisons and police."),
    ("transport", "Transport", "Rail, buses, road traffic and casualties, travel times and electric cars."),
    ("environment", "Environment & energy", "Emissions, the electricity mix, energy use, recycling and sewage spills."),
    ("migration", "Population & migration", "Population, births, deaths and fertility, migration, visas and asylum."),
]
TOPIC_NAME = {k: n for k, n, _ in TOPICS}
GEO_RANK = ["UK", "Great Britain", "England and Wales", "England", "Wales", "Scotland", "Northern Ireland"]

esc = lambda s: html.escape(str(s), quote=True)


# ── numbers ──────────────────────────────────────────────────────────

def fmt(v: float | None) -> str:
    if v is None:
        return "–"
    a = abs(v)
    if a >= 10000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.0f}" if a >= 1000 else f"{v:.0f}"
    if a >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def with_unit(v: float, unit: str) -> str:
    u = unit or ""
    if u.startswith("%"):
        return f"{fmt(v)}%" + (u[1:] if u != "%" else "")
    if u.startswith("£") and not u.startswith("£ per") and " " not in u.strip():
        return f"£{fmt(v)}"
    return f"{fmt(v)} {u}".strip()


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
@media(max-width:640px){.topnav a:not(.btn){display:none}}
main{padding:40px 0 10px}
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
         ld: list[dict], body: str, explore: str = "explore.html") -> str:
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
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{json.dumps(ld if len(ld) > 1 else ld[0], ensure_ascii=False, separators=(",", ":"))}</script>
<script>(function(){{try{{if(localStorage.getItem("polyoptic-theme")==="dark")document.documentElement.dataset.theme="dark";}}catch(e){{}}}})();</script>
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <a class="brand" href="{up}index.html">{LOGO}<span class="wordmark">poly<span class="b">optic</span></span></a>
  <nav class="topnav"><a href="{up}indicator/">Indicators</a><a href="{up}data.html">Verify</a><a href="{up}about.html">About</a>
    <a class="btn" href="{up}{explore}">Open in the explorer</a></nav>
</div></div>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
  <p>Contains public sector information licensed under the Open Government Licence v3.0. Polyoptic publishes no data of its own: every figure links back to the release it came from.</p>
  <nav>{topics} · <a href="{up}indicator/">All indicators A–Z</a></nav>
</div></footer>
</body>
</html>
"""


def crumbs(depth: int, trail: list[tuple[str, str | None]]) -> str:
    up = "../" * depth
    parts = [f'<a href="{up}index.html">Home</a>'] + [
        f'<a href="{up}{href}">{esc(n)}</a>' if href else esc(n) for n, href in trail]
    return f'<nav class="crumbs" aria-label="Breadcrumb">{" › ".join(parts)}</nav>'


def breadcrumb_ld(trail: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": f"{SITE}/{u}"}
        for i, (n, u) in enumerate([("Polyoptic", "")] + trail)]}


# ── one indicator ───────────────────────────────────────────────────

def change_line(s: dict) -> tuple[str, str] | None:
    """The change over the last ten years (or the whole run, if shorter)."""
    pts = points(s)
    if len(pts) < 2:
        return None
    ly, lv = pts[-1]
    base = next(((y, v) for y, v in pts if y >= ly - 10), pts[0])
    by, bv = base
    if by == ly:
        return None
    unit = s["unit"] or ""
    if unit.startswith("%") or s["kind"] == "rate":
        d = lv - bv
        return (f'{"+" if d >= 0 else "−"}{fmt(abs(d))} pts' if unit.startswith("%") else
                f'{"+" if d >= 0 else "−"}{fmt(abs(d))}', f"change since {by}")
    if bv:
        pc = (lv / bv - 1) * 100
        return (f'{"+" if pc >= 0 else "−"}{abs(pc):.1f}%', f"change since {by}")
    return None


def indicator_page(s: dict, slug: str, by_id: dict, slugs: dict, ix: dict, pubs: dict) -> str:
    pts = points(s)
    ly, lv = pts[-1]
    fy = pts[0][0]
    topic = (s.get("topics") or ["economy"])[0]
    tname = TOPIC_NAME.get(topic, topic.title())
    geo = s.get("geography", "UK")
    unit = s.get("unit", "")
    snap = s.get("snapshot")
    years = f"{ly}" if snap or fy == ly else f"{fy}–{ly}"
    pub_full = s.get("publisher_full") or s.get("publisher") or s.get("source")
    latest = with_unit(lv, unit)
    title = f'{s["name"]}: {geo} {"figures" if snap else "data"}, {years} | Polyoptic'
    desc = (f'{s["name"]}, {geo}: {latest} in {ly}. '
            + ("" if snap else f"Every published year from {fy}, ")
            + f"from {pub_full}, with the source, caveats and a chart you can rebase or compare.")
    explore = (f'explore.html#p={s["id"]}~map~none~{fy}~{ly}~bands' if snap and s.get("areas")
               else f'explore.html#p={s["id"]}~line~none~{fy}~{ly}~bands')
    url = f"indicator/{slug}/"

    # a long unit ('house price to earnings ratio') goes under the number, not in it
    short = latest if len(latest) <= 14 else fmt(lv)
    facts = [f'<div class="fact"><b>{esc(short)}</b><span>Latest, {ly}{"" if short == latest else " · " + esc(unit)}</span></div>']
    ch = change_line(s)
    if ch and not snap:
        facts.append(f'<div class="fact"><b>{esc(ch[0])}</b><span>{esc(ch[1])}</span></div>')
    if len(pts) >= 3 and not snap:
        hy, hv = max(pts, key=lambda p: p[1])
        my, mv = min(pts, key=lambda p: p[1])
        facts.append(f'<div class="fact"><b>{esc(fmt(hv))}</b><span>Highest, {hy}</span></div>')
        facts.append(f'<div class="fact"><b>{esc(fmt(mv))}</b><span>Lowest, {my}</span></div>')

    breaks = s.get("discontinuities") or []
    chart = ""
    if len(pts) >= 2:
        chart = (f'<div class="card">{chart_svg(s)}<p class="cap">{esc(unit)} · {esc(geo)} · '
                 f'{"dashed lines mark breaks in the series · " if breaks else ""}source: {esc(s.get("source",""))}</p></div>')

    notes = "".join(f"<li>{esc(n)}</li>" for n in s.get("notes", []))
    brk = "".join(f'<li><b>{esc(d.get("year",""))}: {esc(d.get("label",""))}.</b> {esc(d.get("note",""))}</li>' for d in breaks)

    ex = area_extremes(s, ix) if s.get("areas") else None
    local = ""
    if ex:
        row = lambda r: f'<tr><td>{esc(r[0])}</td><td class="n">{esc(fmt(r[1]))}</td></tr>'
        local = f"""<h2>Highest and lowest areas, {ex['year']}</h2>
<p>Figures are published for {ex['n']} {esc(ex['level'].lower())}. The ten highest and lowest:</p>
<div class="two"><table><thead><tr><th>Highest</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{"".join(row(r) for r in ex['top'])}</tbody></table>
<table><thead><tr><th>Lowest</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{"".join(row(r) for r in ex['bottom'])}</tbody></table></div>
<p style="margin-top:12px"><a href="../../explore.html#p={s['id']}~map~none~{fy}~{ly}~bands">See every area on a map →</a></p>"""

    table = "".join(f'<tr><td>{y}</td><td class="n">{esc(fmt(v))}</td></tr>' for y, v in reversed(pts))
    data_tbl = f"""<h2>Every published year</h2>
<details{' open' if len(pts) <= 12 else ''}><summary>{len(pts)} value{'s' if len(pts) != 1 else ''}, {esc(unit)}</summary>
<table style="margin-top:10px"><thead><tr><th>Year</th><th class="n">{esc(unit)}</th></tr></thead><tbody>{table}</tbody></table></details>
<p style="margin-top:10px"><a href="data.csv">Download as CSV</a> · <a href="../../data.html#{esc(s['id'])}">Check it on Explorer Verify</a></p>"""

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
{f'<h2 style="margin-top:44px">More on {esc(tname.lower())}</h2><ul class="list">{rel}</ul>' if rel else ''}"""

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
        "includedInDataCatalog": {"@type": "DataCatalog", "name": "Polyoptic", "url": f"{SITE}/data.html"},
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
    pts = points(s)
    ly, lv = pts[-1]
    return (f'<li><a href="{href}"><b>{esc(s["name"])}</b>'
            f'<span>{esc(with_unit(lv, s.get("unit","")))} in {ly} · {esc(s.get("geography",""))}</span></a></li>')


def topic_page(k: str, name: str, blurb: str, series: list[dict], slugs: dict) -> str:
    groups: dict[str, list] = {}
    for s in sorted(series, key=lambda x: x["name"]):
        groups.setdefault(s.get("geography", "UK"), []).append(s)
    order = sorted(groups, key=lambda g: GEO_RANK.index(g) if g in GEO_RANK else 99)
    body = f"""{crumbs(2, [(name, None)])}
<h1>{esc(name)} statistics</h1>
<p class="sub">{esc(blurb)} {len(series)} official indicators, each with every published year, its source and its caveats.</p>
<a class="cta" href="../../explore.html#t={k}">Chart them in the explorer →</a>
""" + "".join(f'<div class="grp">{esc(g)} · {len(groups[g])}</div><ul class="list">'
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
<p>{" · ".join(f'<a href="#l-{c}">{c}</a>' for c in letters)}</p>
""" + "".join(f'<div class="grp" id="l-{c}">{c}</div><ul class="list">'
              + "".join(card(s, f'{slugs[s["id"]]}/') for s in letters[c]) + "</ul>" for c in letters)
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "Every indicator, A–Z",
           "url": f"{SITE}/indicator/", "isPartOf": {"@type": "WebSite", "name": "Polyoptic", "url": f"{SITE}/"}}]
    return page(path="indicator/", depth=1, title="Every UK statistic on Polyoptic, A–Z | Polyoptic",
                desc=f"All {len(series)} official UK indicators on Polyoptic, A–Z: economy, housing, education, health, crime, transport, environment and population.",
                og_image="og/home.png", og_alt="Polyoptic", ld=ld, body=body)


# ── the sitemap ─────────────────────────────────────────────────────

def sitemap(entries: list[tuple[str, str, str, str]]) -> str:
    rows = "".join(f"  <url><loc>{SITE}/{p}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq><priority>{pr}</priority></url>\n"
                   for p, m, c, pr in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            "<!-- Written by ingest/pages.py. board.html is deliberately absent: it is a\n"
            "     working page, not a published one, and carries noindex to match. -->\n"
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n")


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

    for d in ("indicator", "topic"):
        shutil.rmtree(ROOT / d, ignore_errors=True)
    today = datetime.now(timezone.utc).date().isoformat()
    entries = [("", today, "weekly", "1.0"), ("explore.html", today, "weekly", "0.9"),
               ("indicator/", today, "weekly", "0.8"), ("data.html", today, "weekly", "0.7"),
               ("about.html", today, "monthly", "0.5")]
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

    (ROOT / "indicator" / "index.html").write_text(index_page(series, slugs))
    (ROOT / "data" / "pages.json").write_text(json.dumps(slugs, separators=(",", ":")))
    (ROOT / "sitemap.xml").write_text(sitemap(entries))
    print(f"pages: {len(series)} indicators, {sum(1 for e in entries if e[0].startswith('topic/'))} topics, sitemap {len(entries)} urls")


if __name__ == "__main__":
    main()
