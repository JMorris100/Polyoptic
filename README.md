# Polyoptic

UK official statistics, plotted against who was in power at the time.

A static site. No server, no database, no runtime cost beyond hosting a
few hundred kilobytes of JSON. Built to run on Cloudflare Pages from a
GitHub repo.

```
polyoptic/
├── index.html                  home — explorer walkthrough, process, questions (and a drawer of more), topics
├── indicator/, topic/          plain pages for search, written by ingest/pages.py
├── explore.html                the explorer — compare, transform, export
├── chartkit.js, chart.css      the chart drawing rules every page shares
├── data.html                   provenance — every raw value, source and API endpoint
├── about.html                  who builds it, and what it deliberately doesn't do
├── q/<slug>/index.html         one page per question: four written by hand, the rest by pages.py
├── og/
│   └── build.html              draws the 1200×630 share images (see below)
├── sitemap.xml                 board.html is deliberately absent
├── data/
│   ├── bundle.json             written by the ingest, committed to git
│   └── areas/                  per-series local figures, lazily fetched
├── ingest/
│   ├── ingest.py               pipeline: fetch → normalise → validate → write
│   ├── series.yaml             the whole catalogue, declarative
│   ├── questions.py            the questions in the homepage drawer, and their answers
│   └── requirements.txt
└── .github/workflows/
    └── refresh.yml             weekly refresh, commits if anything changed
```

---

## Run it

Nothing to build. Open `index.html`, or serve the folder:

```bash
python -m http.server 8000
```

Without `data/bundle.json` the explorer falls back to placeholder data
embedded in the page and says so on every chart. To pull the real thing:

```bash
pip install -r ingest/requirements.txt
python ingest/ingest.py --dry-run     # fetch and validate, write nothing
python ingest/ingest.py               # write data/bundle.json
```

---

## Deploy

Cloudflare Pages, connected to the GitHub repo:

- **Build command:** *(leave empty)*
- **Output directory:** `/`
- **Framework preset:** None

Point `polyoptic.co` at it in the Pages custom-domain settings. The weekly
GitHub Action regenerates `data/bundle.json` and pushes; Pages redeploys on
the commit. No secrets needed — every source used is open and unauthenticated.

---

## The data model

One decision drives everything: **a series is an object, not a page.**

```jsonc
{
  "id": "hpe",
  "name": "House price to earnings ratio",
  "topics": ["housing"],          // tags, not folders — a series can be in several
  "unit": "ratio",
  "kind": "ratio",                // decides which transforms are legal
  "geography": "England & Wales",
  "year_basis": "calendar",       // calendar | financial | academic
  "source": "ONS / HM Land Registry",
  "licence": "OGL v3.0",
  "start": 1997,
  "values": [3.5, 3.8, null, 4.6],  // null is a real gap, not a zero
  "discontinuities": [{ "year": 2020, "note": "…" }]
}
```

A topic page is a filter over series. A lens is a filter on a different
axis. Adding a tenth section costs a query, not a rebuild — which is the
whole argument for doing it this way before you have three hundred series
rather than after.

**Transforms are computed in the browser, never at ingest.** Store what was
published; derive the rest on demand. `kind` decides what's legal: you can
deflate a cash figure, you can't deflate a ratio, and the UI greys out what
doesn't apply rather than quietly producing nonsense.

Reference series — population, GDP deflator, GDP — live once in `refs` and
power per-person, real-terms and %-of-GDP everywhere.

---

## What the explorer does

- Up to four series on one chart, from any topics; filter the catalogue by topic and by what it
  covers (UK, Great Britain, England…, or series with local-area figures)
- **Over time:** line, step, dots, area, gap between two, columns, stacked
  area, stacked columns, slope, scatter, small multiples. **By area:** map,
  ranking, change, range, heatmap
- **Rebase to 100 · Relative to last series · Year-on-year % · 3-year average · Real terms · Per person · % of GDP**
- Rebasing uses the first year every series on the chart has a value, so all
  the lines start together at 100; the chart starts at that year
- Each prime minister shaded behind the chart in their party's colour
- Line charts name each series at its end and draw breaks on the line itself;
  give a discontinuity a short `label` in `series.yaml` for the on-chart text
- Scatter colours each point by the government of the day
- Click any point for its working; **Check the numbers** tables every year's
  published figure, the plotted value and the sum between them
- Everything about a chart — type, transform, government shading, how its
  sources are credited (short, Harvard or off), range, width — is in its
  settings
- Every view is a permalink — the URL hash carries the whole state
- CSV and PNG export with sources and licence, following the chart's setting

### The warnings are the product

The comparison surface is easy. Making comparison *honest* is the hard part
and the thing nobody else bothers with. The explorer refuses to silently
compare across mismatches:

| Mismatch | What it says |
|---|---|
| Different geographies | England-only against UK-wide is not like for like |
| Different year bases | Academic and financial years plot at their starting calendar year, so a point can sit up to twelve months out |
| Different units | Each series on its own axis can make any two lines look correlated — offers a one-click rebase |
| Inapplicable transform | Deflating a rate or a ratio is meaningless; says which series it skipped and why |
| Series discontinuity | Draws the break and explains it, rather than a smooth line across a definitional change |

---

## Adding an indicator

Add an entry to `ingest/series.yaml`. No code changes. Six adapters cover
almost everything published in the UK:

| `source_type` | Use for |
|---|---|
| `ons_timeseries` | ONS website series JSON — one request, whole history. Pragmatic, but the URL encodes the site taxonomy so paths occasionally move |
| `ons_beta` | ONS Beta API at `api.beta.ons.gov.uk/v1`. Open, no key. More stable, but you must know each dataset's dimension names |
| `dfe_ees` | DfE Explore Education Statistics API. POST queries; note not every EES dataset is exposed through the API |
| `csv` | Anything published as a plain CSV file. Unglamorous, and you'll use it more than you expect |
| `els` | ONS Explore Local Statistics. One indicator slug, whole history, and the same call returns every local area — see below |
| `spreadsheet` | `.xlsx` / `.ods` workbooks — the Home Office, MoJ, HMRC, FCDO and the ONS crime team publish nothing else |

### The Explore Local Statistics adapter

ONS's subnational service, and the one source here that is an ingest job
rather than a build. A series needs one line:

```yaml
source_type: els
fetch: {indicator: gross-median-weekly-pay}
```

`geo` defaults to `K02000001`, the UK. `time=all` is sent for you and is not
optional in spirit — without it the service returns the latest period only,
silently, and you get a one-point series.

Two things come free with an `els` entry:

**Candidate entries.** `python ingest/ingest.py --els-catalogue` reads ONS's
own indicator metadata and prints ready-made `series.yaml` blocks — name,
unit, coverage, publisher, and the release's caveats as `notes`. Review before
pasting: it cannot pick a short permalink `id`, choose this catalogue's topic
tags, or judge which caveats are worth carrying. `--els-geo` and
`--els-min-span` narrow what it offers.

**Local detail.** The same indicator is fetched for every area into
`data/areas/<id>.json`, with `data/areas/index.json` holding the area registry
and which series have local figures. These are deliberately *not* in
`bundle.json`: together they are around 1.8 MB against the bundle's 100 KB,
for a view most visits never open, so the explorer fetches them the first time
someone asks for areas. `--areas-only` rebuilds them without touching the
bundle; `--no-areas` skips them.

Levels come from the area code, not the row: `E07…` is a district, `TLC31` is
ITL3. ONS's own level naming differs between the API and the published files
while the coding scheme is stable.

One trap worth knowing: an indicator's metadata can list a geography level it
does not actually serve. `urban-heat-regulating` claims UK coverage, 400s when
you ask for it, and is published here as England.

### The spreadsheet adapter

Two layouts, because publishers use both.

**`long`** — one row per observation, dimensions in columns. Give it
`year_column`, `value_column`, an optional `period_column`, and `filter`
(a scalar means equality, a list means membership):

```yaml
source_type: spreadsheet
fetch:
  url: https://…/illegal-entry-routes-to-the-uk-dataset-mar-2026.xlsx
  sheet: Data_IER_D01
  year_column: Year
  period_column: Quarter
  value_column: Number of detections
  filter: {Method of entry: Small boat arrivals}
```

Values are summed within each period, then collapsed to a year with
`aggregate` (`sum`, `mean`, `last`). Both stages matter: a quarterly **stock**
like the asylum backlog must be summed across its breakdown rows but taken as
the *last* quarter of the year, never summed across quarters.

Add `rate:` — a second filter, a subset of the first — to publish a
percentage where the source only gives you counts. Numerator and denominator
are each collapsed to the year before dividing, so a quiet quarter doesn't get
the same weight as a busy one.

**`wide`** — years across a header row, one row per measure. Give `row_match`
and `label_column`, plus `row_filter` when the label alone isn't unique.

Other options: `urls` (a list, when a series spans one workbook per year),
`header_row` / `year_header_row`, `column_match` (keep only year columns whose
header contains this — needed when a table carries a rolling quarterly series),
`year_offset` (HMRC's "tax year ending 2008" is the 2007 financial year) and
`scale`.

Downloads and parsed sheets are both cached under `ingest/.cache`. The Home
Office crime-outcomes workbooks are 700,000 rows and take about 90 seconds each
to parse, so the first build of those series is slow and every later one isn't.

---

## Status — read this before trusting anything

**The pipeline is live.** Every identifier in `series.yaml` was verified
against the live catalogues on 2026-08-05, and the spreadsheet sources on
2026-08-06. `data/bundle.json` is built from real releases: the original
9 series (housing, economy, education), borders and migration, money, crime
and justice, transport, environment, local statistics, headline ONS economic
and labour-market series (GDP, inflation, employment, productivity, public
finances, trade), and the three reference series — 198 indicators in one
catalogue, filed under the homepage's nine topics. Of those, 116 come from
ONS Explore Local Statistics with figures for every local area, and 27 of
those are `snapshot` series, published for one or two years only, which the
explorer opens as a map rather than a trend. National series added in
October 2026 (NHS performance, homelessness, housebuilding, prisons and
police, emissions, Bank Rate, births and deaths, teachers, NEET, rail,
electric cars) were verified against their published headline figures on
2026-10-18.
The placeholder data embedded in `explore.html` is still invented — it only
shows if `data/bundle.json` fails to load, and it is labelled as such.

**How the sources shook out**

- `ons_timeseries` carries most of the catalogue. The `api.ons.gov.uk`
  gateway is dead; the website JSON endpoint is the working route.
- `ons_beta` (CMD) works via each version's **bulk CSV download** — the
  per-observation endpoint silently returns zero rows for wildcard time
  queries. Time codes come as `Jul-17` style month-year labels.
- `dfe_ees` works, but the catalogue is thinner than the site: school
  funding is not exposed through the API at all, which is why the education
  set is absence, KS2 disadvantage gap and pupil numbers.
- `els` (Explore Local Statistics) added 33 UK-level series in one go —
  population, business demography, wellbeing, healthy life expectancy,
  natural capital — and local figures for all of them. Its metadata
  endpoint describes each indicator well enough to generate most of a
  `series.yaml` entry, caveats included.
- `spreadsheet` now carries everything the APIs don't: Home Office
  immigration and returns, MoJ prison population, HMRC non-doms, FCDO aid,
  ONS crime, Home Office crime outcomes. Traps worth knowing, all of which
  bit during the build and are handled in `ingest.py`:
  - ONS marks provisional and revised periods with a trailing `P` / `R`
    (`YE Dec 25 P`). Unparsed, the period is dropped and a "last value in
    the year" series silently reports an older quarter.
  - ONS wide tables end with derived `% change` columns whose headers still
    contain a year, so they overwrite the real observation unless excluded.
  - The same Home Office column is `Date (as at…)` on one sheet and
    `Date (as at...)` on the next.
  - Tab names carry the period and change spelling between years
    (`Outcomes_open_data_2022_23`, then `Outcomes open data 2025_26`).

**Known gaps**

- Asylum accommodation **spend**, hotels specifically, is only in the Home
  Office annual report and accounts — a PDF. Not fetchable. What is
  fetchable stands in for it: the hotel *population* (`hotels`) and the aid
  budget charged for housing refugees in the UK (`odarefugee`).
- BBC licence fee revenue is likewise PDF-only, in the BBC annual report.
  There is no ONS series for it and no machine-readable DCMS release.
- Charge rates **by offence type** span only four years — the open data
  tables are one ~40MB workbook per financial year. Extend by adding URLs
  to the `outcomes` anchor in `series.yaml`; the overall charge rate runs
  from 2014-15 because that one comes from a summary table.
- EU contributions are the ONS Pink Book figures, which are *after* the
  rebate. The rebate was deducted at source, so the gross-before-rebate
  number behind the £350m-a-week claim is a different (and more arguable)
  measure.
- The MHCLG housing series and the HMT financial-year deflator are now
  unblocked by the spreadsheet adapter but not yet added.
- Local breakdowns exist only for the 33 `els` series. The other 42 are still
  a single national figure per id, and the schema still has no general
  `geography` dimension — the area files sit beside the bundle rather than
  inside the series objects.
- The map uses ONS ultra-generalised boundaries (`data/geo/`, built by
  `python ingest/geo.py`), fetched only when a map is opened — about 200 KB
  per level. They are current boundaries, so areas abolished in past
  reorganisations have a figure but no shape and are left off the map.
- No sub-annual data. Everything collapses to years at ingest.
- No tests.

---

## Sharing and search

Every published page carries a description, canonical URL, Open Graph and
`twitter:card` tags, and JSON-LD. `robots.txt` allows crawling and points at
`sitemap.xml`; `board.html` is the one exception, excluded from both and
carrying `noindex`.

**Chart state lives in the URL fragment**, and fragments never reach a server,
so an unfurler cannot tell one explorer link from another — every one of them
previews with the same card. The same goes for `#q-<key>` on the homepage. That
is why every question has a real URL under `/q/<slug>/`, each with its own
metadata and its own image.
Making arbitrary explorer links unfurl as themselves would mean moving state
into the query string and rendering images on demand, which needs a server this
site does not have.

**More questions: answered in place, and each a page of its own.** Under
the four featured questions, the homepage has a drawer of eighteen more. They
are written once, in `ingest/questions.py`: each names its indicators, the
explorer chart that answers it (line, dots, small multiples, stacked area,
slope, columns, gap or scatter), why that chart, the caveat that matters, and
a `say()` that writes the answer from the bundle, leaving out any year still in
progress. Some are marked `myth`: questions where the trend people expect isn't
there. `pages.py` works them all out and writes:

- `data/questions-more.json`, which the drawer reads and draws in place;
- `q/<slug>/` for each one, with the answer first, the chart drawn as SVG, the
  caveat, links to its indicators and `FAQPage` markup, so every question can
  be found by search and shared with its own preview;
- `q/`, a page listing every question, featured and not;
- the plain links inside the drawer's list in `index.html`, for crawlers that
  don't run scripts, and a "More questions" list on the four featured pages;
- a "Questions this figure helps answer" list on each indicator page, and the
  questions about each topic on its topic page.

The drawer and the page draw the same computed numbers, so they cannot
disagree. To add a question, add an entry to `QUESTIONS` in `questions.py`,
run `pages.py`, and draw its share image (below). `#q-<key>` on the homepage
opens the drawer on one question.

**A plain page for every indicator.** The explorer is an app and its HTML is
nearly empty until the script runs, so `ingest/pages.py` writes pages a search
engine can read without running anything: `indicator/<slug>/` for every series
(latest figure, a chart drawn as SVG, every published year, the source, notes
and breaks, the highest and lowest local areas where there are any, and a
`data.csv`), `topic/<topic>/` for each of the nine topics, an A–Z at
`indicator/`, and `sitemap.xml` with all of them. Indicator pages carry
schema.org `Dataset` markup, so they can appear in Google Dataset Search. The
weekly refresh runs it after `ingest.py`; run it by hand after a manual
rebuild. Slugs come from the series name and are written to `data/pages.json`.

**The share images are generated in a browser**, not by the build: open
`og/build.html` from the dev server, click *Download all*, and drop the PNGs
into `og/` (four for the main pages, nine for the topics, and one for each
question, featured and not). A question page with no image yet falls back to
the homepage card. Filenames match the `og:image` tags — don't rename them. They
are drawn on a canvas from `bundle.json`, so the comparison cards show the real
current chart, and they need re-running when a chart changes materially.

Source names on the homepage are set in Polyoptic's own type rather than
reproduced as departmental logos: OGL v3.0 licenses the *information* and
specifically excludes crests and logos, so the logos are the one thing on the
site that the licence would not cover.

---

## Licence and attribution

Contains public sector information licensed under the Open Government
Licence v3.0. Ministerial and party data from the Institute for Government
Ministers Database, CC-BY-4.0.

Every series links back to its original release. Polyoptic publishes no data
of its own, and shouldn't ever.
