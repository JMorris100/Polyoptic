# Polyoptic

UK official statistics, plotted against who was in power at the time.

A static site. No server, no database, no runtime cost beyond hosting a
few hundred kilobytes of JSON. Built to run on Cloudflare Pages from a
GitHub repo.

```
polyoptic/
├── index.html                  home — tiles and featured charts
├── explore.html                the explorer — compare, transform, export
├── data.html                   provenance — every raw value, source and API endpoint
├── data/
│   └── bundle.json             written by the ingest, committed to git
├── ingest/
│   ├── ingest.py               pipeline: fetch → normalise → validate → write
│   ├── series.yaml             the whole catalogue, declarative
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

- Up to four series on one chart, from any topics
- **Line · Bars · Area · Scatter · Small multiples**
- **Rebase to 100 · Year-on-year % · 3-year average · Real terms · Per person · % of GDP**
- Era ribbon showing governing party and PM, on every time-series chart
- Scatter colours each point by the government of the day
- Every view is a permalink — the URL hash carries the whole state
- CSV export with sources and licence in the header

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

Add an entry to `ingest/series.yaml`. No code changes. Four adapters cover
almost everything published in the UK:

| `source_type` | Use for |
|---|---|
| `ons_timeseries` | ONS website series JSON — one request, whole history. Pragmatic, but the URL encodes the site taxonomy so paths occasionally move |
| `ons_beta` | ONS Beta API at `api.beta.ons.gov.uk/v1`. Open, no key. More stable, but you must know each dataset's dimension names |
| `dfe_ees` | DfE Explore Education Statistics API. POST queries; note not every EES dataset is exposed through the API |
| `csv` | MHCLG live tables, OBR databank, anything published as a file. Unglamorous, and you'll use it more than you expect |

---

## Status — read this before trusting anything

**The pipeline is live.** Every identifier in `series.yaml` was verified
against the live catalogues on 2026-08-05 and `data/bundle.json` is built
from real releases: 9 series (housing, economy, education) plus the three
reference series. The placeholder data embedded in `explore.html` is still
invented — it only shows if `data/bundle.json` fails to load, and it is
labelled as such.

**How the sources shook out**

- `ons_timeseries` carries most of the catalogue. The `api.ons.gov.uk`
  gateway is dead; the website JSON endpoint is the working route.
- `ons_beta` (CMD) works via each version's **bulk CSV download** — the
  per-observation endpoint silently returns zero rows for wildcard time
  queries. Time codes come as `Jul-17` style month-year labels.
- `dfe_ees` works, but the catalogue is thinner than the site: school
  funding is not exposed through the API at all, which is why the education
  set is absence, KS2 disadvantage gap and pupil numbers.
- The planned MHCLG housing series (net additions, social stock, temporary
  accommodation), the HMT deflator and the OBR databank are all published
  as ODS/XLS spreadsheets, not CSV. They need a spreadsheet adapter —
  that's the next piece of pipeline work.

**Known gaps**

- No spreadsheet (ODS/XLSX) adapter yet — see above; it unlocks most of
  the missing housing catalogue.
- The deflator is the ONS *implied* GDP deflator (L8GG, calendar years),
  not the HMT financial-year deflator, until that adapter exists.
- No local-authority or regional breakdowns — the schema takes a single
  national series per id. Adding a `geography` dimension is the next real
  piece of architecture, and it's the one that unlocks maps.
- No sub-annual data. Everything collapses to years at ingest.
- No tests.

---

## Licence and attribution

Contains public sector information licensed under the Open Government
Licence v3.0. Ministerial and party data from the Institute for Government
Ministers Database, CC-BY-4.0.

Every series links back to its original release. Polyoptic publishes no data
of its own, and shouldn't ever.
