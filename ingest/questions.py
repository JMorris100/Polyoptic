"""
The questions answered in the homepage's drawer, each of which also has a page
of its own at q/<slug>/.

One list, two outputs. pages.py works out every answer here from the bundle
and writes it to data/questions-more.json, which the homepage reads to show
the question in place, and into a plain page per question, which search
engines and link previews read. The chart on the homepage and the chart on
the page are drawn from the same computed numbers, so the two cannot differ.

Each question names:
    ids      the indicators, in the order the chart uses them
    chart    the explorer chart that answers it best: line, dots, small,
             stack, slope, bar, gap or scatter
    trans    none, index (rebased to the first year all series share) or
             pctgdp (a share of nominal GDP)
    why      what that kind of chart does for this question
    care     the caveat that matters most
    say      the answer, written from the numbers

A year still in progress is left out throughout, so whole years are only
ever set against whole years. Groups: "many" (several trends at once), "long"
(the long view) and "myth" (the trend people expect is not there, or is not
what it seems).
"""
from __future__ import annotations

import html
import math

esc = lambda s: html.escape(str(s), quote=True)

TYPE_NAME = {"line": "Line", "dots": "Dots", "small": "Small multiples", "stack": "Stacked area",
             "slope": "Slope", "bar": "Columns", "gap": "Gap", "scatter": "Scatter"}
GROUP_NAME = {"many": "Several trends at once", "myth": "Looks like a trend — isn’t", "long": "The long view"}
WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


# ── reading the bundle for an answer ────────────────────────────────

class Data:
    """The bundle, read the way an answer needs it: by series and year, with
    any year still in progress left out."""

    def __init__(self, db: dict):
        self.by_id = {s["id"]: s for s in db["series"]}
        self.refs = db.get("refs", {})

    def val(self, i: str, y: int) -> float | None:
        s = self.by_id.get(i)
        if not s or (s.get("partial") or {}).get("year") == y:
            return None
        k = y - s["start"]
        return s["values"][k] if 0 <= k < len(s["values"]) else None

    def ref(self, k: str, y: int) -> float | None:
        r = self.refs.get(k)
        if not r:
            return None
        i = y - r["start"]
        return r["values"][i] if 0 <= i < len(r["values"]) else None

    def yrs(self, i: str, a: int, b: int) -> list[int]:
        return [y for y in range(a, b + 1) if self.val(i, y) is not None]

    def first(self, i, a, b):
        return self.yrs(i, a, b)[0]

    def last(self, i, a, b):
        return self.yrs(i, a, b)[-1]

    def argmax(self, i, a, b, f=lambda v: v):
        return max(self.yrs(i, a, b), key=lambda y: f(self.val(i, y)))

    def argmin(self, i, a, b):
        return min(self.yrs(i, a, b), key=lambda y: self.val(i, y))

    def yl(self, i: str, y: int) -> str:
        """2019/20 for a school year, 2019-20 for a financial one."""
        b = (self.by_id.get(i) or {}).get("year_basis")
        if b == "academic":
            return f"{y}/{(y + 1) % 100:02d}"
        if b == "financial":
            return f"{y}-{(y + 1) % 100:02d}"
        return str(y)


def rnd(v: float) -> int:
    """Half up, as a reader rounds — not Python's half to even."""
    return int(math.floor(v + 0.5))


def big(v: float) -> str:
    return f"{v / 1e6:.1f} million" if abs(v) >= 1e6 else f"{rnd(v):,}"


def thou(v: float) -> str:
    return f"{rnd(v / 1000) * 1000:,}"


d1 = lambda v: f"{v:.1f}"
d2 = lambda v: f"{v:.2f}"
nw = lambda n: WORDS[n] if 0 <= n < 10 else str(n)


def pc(a: float, b: float) -> str:
    c = (b / a - 1) * 100
    return f'{"+" if c >= 0 else "−"}{abs(c):.0f}%'


def pcw(a: float, b: float) -> str:
    c = (b / a - 1) * 100
    return f'{"up" if c >= 0 else "down"} {abs(c):.0f}%'


def lc(t: str) -> str:
    return t[0].lower() + t[1:]


def at(sets, i, y):
    s = next(s for s in sets if s["id"] == i)
    return next((v for yy, v in s["pts"] if yy == y), None)


# ── the answers ─────────────────────────────────────────────────────
# Each takes the data, the question and its computed sets, and returns the
# paragraph shown under "The answer" — on the homepage and on the page.

def say_nhs(D, Q, sets):
    w, wp = D.last("rttwaitlist", 2010, 2026), D.argmax("rttwaitlist", 2019, 2026)
    a, m, mw = D.last("ae4hour", 2010, 2026), D.last("ambcat2", 2010, 2026), D.argmax("ambcat2", 2017, 2026)
    g0, g = D.first("gpfte", 2010, 2026), D.last("gpfte", 2010, 2026)
    v = D.val
    return (f'The waiting list was {big(v("rttwaitlist", 2019))} in 2019 and {big(v("rttwaitlist", w))} in {w}'
            + (f', having peaked at {big(v("rttwaitlist", wp))} in {wp}' if wp != w else "") + ". "
            f'The share of A&E patients seen within four hours went from {d1(v("ae4hour", 2018))}% in {D.yl("ae4hour", 2018)} '
            f'to {d1(v("ae4hour", a))}% in {D.yl("ae4hour", a)}. '
            f'Category 2 ambulances — strokes, heart attacks — averaged {rnd(v("ambcat2", 2018))} minutes in {D.yl("ambcat2", 2018)}, '
            f'{rnd(v("ambcat2", mw))} at the worst in {D.yl("ambcat2", mw)}, and {rnd(v("ambcat2", m))} in {D.yl("ambcat2", m)}. '
            f'Fully qualified GPs have barely changed in number: {big(v("gpfte", g))} full-time equivalents in {g}, '
            f'against {big(v("gpfte", g0))} in {g0}.')


def say_life(D, Q, sets):
    v = D.val
    e, h0, h = D.last("lemale", 2001, 2022), D.first("hlemale", 2001, 2022), D.last("hlemale", 2001, 2022)
    gap0, gap = v("lefemale", h0) - v("hlefemale", h0), v("lefemale", h) - v("hlefemale", h)
    return (f'Life expectancy at birth rose by {d1(v("lemale", 2011) - v("lemale", 2001))} years for men and '
            f'{d1(v("lefemale", 2011) - v("lefemale", 2001))} for women between 2001 and 2011, then all but stopped: '
            f'by {e} it was {d1(v("lemale", e))} for men and {d1(v("lefemale", e))} for women. '
            f'Healthy life expectancy — the years expected in good health — fell, from {d1(v("hlemale", h0))} to '
            f'{d1(v("hlemale", h))} for men and {d1(v("hlefemale", h0))} to {d1(v("hlefemale", h))} for women. '
            f'So the years a woman can expect to spend in poor health grew from {d1(gap0)} to {d1(gap)}.')


def say_power(D, Q, sets):
    v = D.val
    f, l = D.first("fossilshare", 1998, 2025), D.last("renewshare", 1998, 2025)
    cross = lambda a, b: next((y for y in D.yrs(a, 1998, 2025) if v(a, y) > v(b, y)), None)
    c1, c2 = cross("lowcarbon", "fossilshare"), cross("renewshare", "fossilshare")
    return (f'In {f} fossil fuels made {d1(v("fossilshare", f))}% of the UK’s electricity and renewables {d1(v("renewshare", f))}%. '
            + (f"Low-carbon sources — renewables plus nuclear — overtook fossil fuels in {c1}" if c1 else "")
            + (f", and renewables alone did so in {c2}. " if c2 else ". ")
            + f'By {l} renewables made {d1(v("renewshare", l))}% against fossil fuels’ {d1(v("fossilshare", l))}%.')


def say_ageing(D, Q, sets):
    v = D.val
    f, l = D.first("pop65", 1991, 2024), D.last("pop65", 1991, 2024)
    c = next((y for y in D.yrs("pop65", 1991, 2024) if v("pop65", y) > v("pop015", y)), None)
    pk = D.argmax("pop1664", 1991, 2024)
    return (f'In {f} under-16s were {d1(v("pop015", f))}% of the UK population and over-65s {d1(v("pop65", f))}%. '
            + (f'The over-65s overtook the under-16s in {c}, and by {l} were {d1(v("pop65", l))}% against {d1(v("pop015", l))}%. ' if c else "")
            + f'The working-age share peaked at {d1(v("pop1664", pk))}% in {pk} and is {d1(v("pop1664", l))}% now.')


def say_travel(D, Q, sets):
    n = lambda x: rnd(x)
    lo = lambda i: D.argmin(i, 2019, 2025)
    l = D.last("railjourneys", 2010, 2025)
    return (f'Set each to {Q["start"]} = 100. Before the pandemic, in {D.yl("railjourneys", 2018)}, rail journeys stood at '
            f'{n(at(sets, "railjourneys", 2018))} and road traffic at {n(at(sets, "traffic", 2018))}, while bus journeys had fallen to '
            f'{n(at(sets, "busjourneys", 2018))}. Lockdown took rail down to {n(at(sets, "railjourneys", lo("railjourneys")))} and buses to '
            f'{n(at(sets, "busjourneys", lo("busjourneys")))}. By {D.yl("railjourneys", l)} rail was back to {n(at(sets, "railjourneys", l))} '
            f'and traffic {n(at(sets, "traffic", D.last("traffic", 2010, 2025)))}, but buses only '
            f'{n(at(sets, "busjourneys", D.last("busjourneys", 2010, 2025)))}.')


def say_rise(D, Q, sets):
    end = sorted(((s, [p for p in s["pts"] if p[1] is not None][-1]) for s in sets), key=lambda e: -e[1][1])
    lst = [f"{lc(s['name'])} {pc(100, p[1])}" for s, p in end]
    return (f'Rebased to {Q["start"]} = 100, by {Q["end"]}: {", ".join(lst[:-1])} and {lst[-1]}. '
            f'{end[0][0]["name"]} rose most and {lc(end[-1][0]["name"])} least.')


def say_migration(D, Q, sets):
    v = D.val
    n, nl = D.argmax("netmig", 2012, 2025), D.last("netmig", 2012, 2025)
    w, s, h = D.argmax("visawork", 2012, 2025), D.argmax("visastudy", 2012, 2025), D.argmax("visahcw", 2012, 2025)
    return (f'Net migration was {thou(v("netmig", 2019))} in 2019, peaked at {thou(v("netmig", n))} in {n} and was '
            f'{thou(v("netmig", nl))} in {nl}. Study visas peaked first, at {thou(v("visastudy", s))} in {s}; work visas at '
            f'{thou(v("visawork", w))} in {w}, when {thou(v("visahcw", h))} health and care visas were granted. '
            f'Both routes have fallen since, in step with the headline number.')


def say_obesity(D, Q, sets):
    v = D.val
    f, l = D.first("obesey6", 2006, 2024), D.last("obesey6", 2006, 2024)
    return (f'Obesity among reception children was {d1(v("obeserec", f))}% in {D.yl("obeserec", f)} and '
            f'{d1(v("obeserec", l))}% in {D.yl("obeserec", l)} — little changed. Among Year 6 children it went from '
            f'{d1(v("obesey6", f))}% to {d1(v("obesey6", l))}%. Children now leave primary school about '
            f'{d1(v("obesey6", l) / v("obeserec", l))} times as likely to be obese as when they start it.')


def say_homes(D, Q, sets):
    v = D.val
    pk, l = D.argmax("homecompletions", 1946, 2025), D.last("homecompletions", 1946, 2025)
    p30 = D.argmax("homecompletions", l - 29, l)
    return (f'England completed {thou(v("homecompletions", pk))} new homes in {pk}, the most in any year since the war. '
            f'In the last thirty years the most in a single year was {thou(v("homecompletions", p30))}, in {p30}, and in {l} '
            f'it was {thou(v("homecompletions", l))} — {rnd(v("homecompletions", l) / v("homecompletions", pk) * 100)}% of the {pk} peak.')


def say_borrow(D, Q, sets):
    p = [q for q in sets[0]["pts"] if q[1] is not None]
    surp = [q for q in p if q[1] < 0]
    pk, l = max(p, key=lambda q: q[1]), p[-1]
    return (f'The government borrowed in {len(p) - len(surp)} of the {len(p)} years from {p[0][0]} to {l[0]}. '
            + (f"The last surplus was in {surp[-1][0]}. " if surp else "")
            + f"Borrowing peaked at {d1(pk[1])}% of GDP in {pk[0]}; in {l[0]} it was {d1(l[1])}%.")


def say_births(D, Q, sets):
    v = D.val
    ys = [y for y in D.yrs("births", 1938, 2025) if v("deaths", y) is not None]
    gap = lambda y: v("births", y) - v("deaths", y)
    pk, l = max(ys, key=gap), ys[-1]
    neg = [y for y in ys if gap(y) < 0]
    tail = (f"Deaths last outnumbered births in {neg[-1]}"
            + (f", one of only {nw(len(neg))} years since {ys[0]} when they did" if len(neg) > 1 else "") + "."
            if neg else f"Deaths have not outnumbered births in any year since {ys[0]}.")
    return (f"In {pk} births outnumbered deaths in England and Wales by {thou(gap(pk))}. In {l} the gap was {thou(gap(l))}: "
            f'{thou(v("births", l))} births against {thou(v("deaths", l))} deaths. ' + tail)


def say_prod(D, Q, sets):
    v = D.val
    f, l = D.first("productivity", 1971, 2025), D.last("productivity", 1971, 2025)
    r = lambda a, b: ((v("productivity", b) / v("productivity", a)) ** (1 / (b - a)) - 1) * 100
    proj = v("productivity", 2007) * (1 + r(f, 2007) / 100) ** (l - 2007)
    return (f"Output per hour grew by {d1(r(f, 2007))}% a year on average from {f} to 2007, and {d1(r(2007, l))}% a year "
            f"from 2007 to {l}. Had the old rate carried on, the index would be about {rnd(proj)} today rather than "
            f'{rnd(v("productivity", l))} — roughly {rnd((proj / v("productivity", l) - 1) * 100)}% higher.')


def say_crime(D, Q, sets):
    v = D.val
    lo, l = D.argmin("prc", 2002, 2025), D.last("prc", 2002, 2025)
    cl, cp = D.last("csew", 2002, 2025), D.argmax("csew", 1981, 2025)
    return (f'Police-recorded crime has risen {pc(v("prc", lo), v("prc", l)).lstrip("+")} since its low in {D.yl("prc", lo)} — '
            f"the rise most headlines report. The Crime Survey, which asks people what happened to them and does not depend on "
            f'what the police record, shows crime {pcw(v("csew", 2002), v("csew", cl))} since {D.yl("csew", 2002)}, and '
            f'{pcw(v("csew", cp), v("csew", cl)).replace("down ", "")} lower than its peak in {D.yl("csew", cp)}.')


def say_happy(D, Q, sets):
    v = D.val
    h = [v("wbhappy", y) for y in D.yrs("wbhappy", 2011, 2022)]
    l = D.last("wbanxiety", 2011, 2022)
    return (f"On a scale of 0 to 10, average happiness moved between {d2(min(h))} and {d2(max(h))} over {len(h)} years — "
            f"{d2(max(h) - min(h))} of a point. The biggest move came in the pandemic: anxiety rose from "
            f'{d2(v("wbanxiety", 2018))} in {D.yl("wbanxiety", 2018)} to {d2(v("wbanxiety", 2020))} in {D.yl("wbanxiety", 2020)}, '
            f'and was {d2(v("wbanxiety", l))} in {D.yl("wbanxiety", l)}. Drawn from zero, as here, the lines are close to flat. '
            f"Cut the axis to fit the data and the same numbers look like a collapse.")


def say_deaths(D, Q, sets):
    v = D.val
    lo, hi, l = D.argmin("deaths", 1900, 2025), D.argmax("deaths", 1900, 2025), D.last("deaths", 1900, 2025)
    pr = D.refs.get("population") or {}
    pl = pr.get("start", 0) + len(pr.get("values", [])) - 1
    p0, p1 = D.ref("population", 1971), D.ref("population", min(l, pl))
    out = (f'Deaths in England and Wales have stayed between {thou(v("deaths", lo))} ({lo}) and {thou(v("deaths", hi))} ({hi}) '
           f'every year since 1900. In {l} there were {thou(v("deaths", l))}.')
    if p0 and p1:
        within = max(1, math.ceil(abs(v("deaths", l) / v("deaths", 1971) - 1) * 100))
        out += (f" Since 1971 the UK population has grown by {rnd((p1 / p0 - 1) * 100)}%, yet deaths in {l} were within "
                f'{within}% of the {thou(v("deaths", 1971))} in 1971.')
    return out


def say_saving(D, Q, sets):
    v = D.val
    ys = D.yrs("saving", 1963, 2025)
    vals = [v("saving", y) for y in ys]
    m = sum(vals) / len(vals)
    lo, hi, l = D.argmin("saving", 1963, 2025), D.argmax("saving", 1963, 2025), ys[-1]
    lv = v("saving", l)
    rel = "close to" if abs(lv - m) < 1 else "above" if lv > m else "below"
    return (f'Households have saved between {d1(v("saving", lo))}% ({lo}) and {d1(v("saving", hi))}% ({hi}) of their disposable '
            f"income since {ys[0]}, {d1(m)}% on average. In {l} it was {d1(lv)}%, {rel} that average. "
            f"The highs line up with recessions and the 2020 lockdown, when spending fell — there is no long slide.")


def say_trade(D, Q, sets):
    p = [q for q in sets[0]["pts"] if q[1] is not None]
    pre = [q for q in p if 1998 <= q[0] <= 2015]
    post = [q for q in p if q[0] >= 2016]
    dfc = lambda a: sum(1 for q in a if q[1] < 0)
    avg = lambda a: sum(q[1] for q in a) / len(a)
    of = lambda n, a: f"every one of the {len(a)} years" if n == len(a) else f"{nw(n)} of the {len(a)} years"
    return (f"The UK ran a trade deficit in {of(dfc(pre), pre)} from 1998 to 2015, before the referendum, and in "
            f"{of(dfc(post), post)} since. It averaged {d1(abs(avg(pre)))}% of GDP a year before the vote and "
            f"{d1(abs(avg(post)))}% after. The deficit is decades old.")


def say_police(D, Q, sets):
    X, Y = sets
    pr = [(y, x, Y["pts"][i][1]) for i, (y, x) in enumerate(X["pts"]) if x is not None and Y["pts"][i][1] is not None]
    mx, my = sum(q[1] for q in pr) / len(pr), sum(q[2] for q in pr) / len(pr)
    r = (sum((q[1] - mx) * (q[2] - my) for q in pr)
         / math.sqrt(sum((q[1] - mx) ** 2 for q in pr) * sum((q[2] - my) ** 2 for q in pr)))
    lo, hi = min(pr, key=lambda q: q[1]), max(pr, key=lambda q: q[1])
    cl, l = min(pr, key=lambda q: q[2]), pr[-1]
    return (f"Across these {len(pr)} years, if anything the years with more officers had lower charge rates "
            f'(a correlation of {"−" if r < 0 else ""}{abs(r):.2f}). Officer numbers fell to {thou(lo[1])} in {lo[0]} and rose '
            f"to {thou(hi[1])} by {hi[0]}; the charge rate fell from {d1(pr[0][2])}% to {d1(cl[2])}% in "
            f'{D.yl("chargerate", cl[0])}, and is back to {d1(l[2])}%. Both moved with time, for their own reasons — '
            f"the dots trace a loop, not a line.")


# ── the questions ───────────────────────────────────────────────────
# `q` is the short form used on the homepage; `title` is the page heading,
# phrased the way someone would search for it.

QUESTIONS: list[dict] = [
    dict(key="nhs", slug="is-the-nhs-under-more-strain-than-before-the-pandemic", group="many",
         q="Is the NHS under more strain than before the pandemic?",
         title="Is the NHS under more strain than before the pandemic?",
         ids=["rttwaitlist", "ae4hour", "ambcat2", "gpfte"], chart="small", trans="none", start=2010, end=2026, era="bands",
         short={"rttwaitlist": "Waiting list (pathways)", "ae4hour": "A&E seen within 4 hours (%)",
                "ambcat2": "Ambulance, Category 2 (minutes)", "gpfte": "Fully qualified GPs (FTE)"},
         say=say_nhs,
         why="Four measures in four units — patients, a percentage, minutes, doctors. Small multiples give each its own scale on the same timeline, so you compare the shape and timing of each without pretending they share an axis.",
         care="Every one of these has breaks in it: pathways dropped from the waiting list in 2013 and 2024, A&E trial sites left out from 2019 to 2023, new ambulance standards in 2017. They are marked on the lines in the explorer."),
    dict(key="life", slug="are-people-in-the-uk-living-longer-and-healthier", group="many",
         q="Are we living longer — and healthier?",
         title="Are people in the UK living longer — and healthier?",
         ids=["lefemale", "lemale", "hlefemale", "hlemale"], chart="line", trans="none", start=2001, end=2022, era="off",
         short={"lefemale": "Women", "lemale": "Men", "hlefemale": "Women, in good health", "hlemale": "Men, in good health"},
         say=say_life,
         why="All four are in years, so they can honestly share one axis — and the space between each pair of lines is the story: the years lived in poor health.",
         care="Period life expectancy assumes this year’s death rates hold for a whole lifetime: it summarises mortality now rather than forecasting it. Healthy life expectancy rests on people rating their own health in a survey."),
    dict(key="power", slug="where-does-uk-electricity-come-from-now", group="many",
         q="Where does our electricity come from now?",
         title="Where does UK electricity come from now?",
         ids=["renewshare", "lowcarbon", "fossilshare"], chart="line", trans="none", start=1998, end=2025, era="off",
         short={"renewshare": "Renewables", "lowcarbon": "Low-carbon, incl. nuclear", "fossilshare": "Fossil fuels"},
         say=say_power,
         why="Shares of the same total over a quarter of a century. A line shows exactly when one source overtook another, which a stacked chart would bury in its middle bands.",
         care="Low-carbon includes renewables, so those two lines overlap by design — they are not slices that add up to 100%. The space between them is nuclear."),
    dict(key="ageing", slug="is-the-uk-population-getting-older", group="many",
         q="Is the population getting older?",
         title="Is the UK population getting older?",
         ids=["pop015", "pop1664", "pop65"], chart="stack", trans="none", start=1991, end=2024, era="off",
         short={"pop015": "Under 16", "pop1664": "16 to 64", "pop65": "65 and over"},
         say=say_ageing,
         why="The three age groups add up to the whole population, and a stacked area shows that: each band is a share of 100%. Its weakness is that only the bottom band sits on a flat baseline — the moment the over-65s overtake the under-16s is easier to see as a line, one click away in the explorer.",
         care="These are shares, not numbers. The population grew throughout, so a smaller share of under-16s does not have to mean fewer children."),
    dict(key="travel", slug="have-trains-buses-and-road-traffic-recovered-from-lockdown", group="many",
         q="Have trains, buses and cars recovered from lockdown?",
         title="Have UK trains, buses and road traffic recovered from lockdown?",
         ids=["railjourneys", "busjourneys", "traffic"], chart="line", trans="index", start=2010, end=2025, era="off",
         short={"railjourneys": "Rail journeys", "busjourneys": "Bus journeys", "traffic": "Road traffic"},
         say=say_travel,
         why="Journeys, journeys and vehicle miles: three units at three very different sizes. Rebasing each to 100 in the same year puts them on one axis as growth, so ‘back to normal’ means the same thing for all three.",
         care="Rail and bus figures are April-to-March years and road traffic is calendar years, so the pandemic dip lands a few months apart. Rail has several changes of method, marked in the explorer."),
    dict(key="rise", slug="pay-prices-rents-or-house-prices-what-has-risen-fastest-since-2015", group="many",
         q="Since 2015, what has risen fastest: pay, prices, rents or house prices?",
         title="Pay, prices, rents or house prices: what has risen fastest in the UK since 2015?",
         ids=["pay", "cpih", "rents", "houseprice"], chart="slope", trans="index", start=2015, end=2025, era="off",
         short={"pay": "Pay", "cpih": "Prices (CPIH)", "rents": "Private rents", "houseprice": "House prices"},
         say=say_rise,
         why="When the question is ‘where did each one end up?’, the years in between are noise. A slope chart keeps just the start and the end, so the ranking and the size of each rise read at a glance.",
         care="A slope chart hides the route: two series can take very different paths and finish level. Switch to a line in the explorer to see each year. The rents index starts in 2015, which is why this does too."),
    dict(key="migration", slug="is-uk-net-migration-driven-by-students-or-workers", group="many",
         q="Is net migration driven by students or workers?",
         title="Is UK net migration driven by students or workers?",
         ids=["netmig", "visastudy", "visawork", "visahcw"], chart="line", trans="none", start=2012, end=2025, era="off",
         short={"netmig": "Net migration", "visastudy": "Study visas", "visawork": "Work visas", "visahcw": "Health and care visas"},
         say=say_migration,
         why="All four count people, so one axis is fair — and putting the routes beside the headline number shows which of them moved with it, and when.",
         care="A visa granted is not a person settling: visas include short stays, study visas here exclude dependants, and net migration subtracts everyone who left. ONS changed how it estimates net migration in 2020."),
    dict(key="obesity", slug="are-children-in-england-getting-heavier", group="many",
         q="Are children getting heavier?",
         title="Are children in England getting heavier?",
         ids=["obeserec", "obesey6"], chart="dots", trans="none", start=2006, end=2024, era="off", zero=True,
         short={"obeserec": "Reception, age 4–5", "obesey6": "Year 6, age 10–11"},
         say=say_obesity,
         why="Each dot is one school year’s measurement. Dots rather than a line make plain that this is a yearly check, and stop one odd year from dragging a line up and down with it.",
         care="England only. The 2020/21 figures come from a much smaller sample of schools measured during the pandemic, so that year’s jump should be read with care."),
    dict(key="homes", slug="is-england-building-as-many-homes-as-it-used-to", group="long",
         q="Are we building as many homes as we used to?",
         title="Is England building as many homes as it used to?",
         ids=["homecompletions"], chart="bar", trans="none", start=1946, end=2025, era="off", note=True,
         say=say_homes,
         why="Homes completed is a count for each year, so each column is one year’s output and its height the total. Columns make the size of the post-war peak against today plain in a way a thin line does not.",
         care="These are completions counted by councils and building control in England. They miss conversions and changes of use, which the ‘net additions’ measure includes, so they understate how many homes the stock gains."),
    dict(key="borrow", slug="when-did-the-uk-government-last-balance-the-books", group="long",
         q="When did the government last balance the books?",
         title="When did the UK government last balance the books?",
         ids=["psnb"], chart="bar", trans="pctgdp", start=1946, end=2025, era="bands", signs=["Borrowing", "Surplus"], note=True,
         say=say_borrow,
         why="Borrowing is one total per year and can go below zero when there is a surplus. Columns above and below the line show each year’s sign at a glance — and as a share of GDP, 1950 and 2020 compare fairly.",
         care="In cash terms every recent year would dwarf the past, which is why this is a share of the economy. A surplus here is the whole public sector’s, before any one-off transfers are taken out."),
    dict(key="births", slug="are-deaths-about-to-overtake-births-in-england-and-wales", group="long",
         q="Are deaths about to overtake births?",
         title="Are deaths about to overtake births in England and Wales?",
         ids=["births", "deaths"], chart="gap", trans="none", start=1938, end=2025, era="off",
         short={"births": "Births", "deaths": "Deaths"},
         say=say_births,
         why="The question is about the difference between two lines. A gap chart shades it, so you read births minus deaths — the natural change in the population — directly, and see how close the lines have come.",
         care="England and Wales only. With the gap this narrow, population growth now comes almost entirely from migration."),
    dict(key="prod", slug="did-uk-productivity-stop-growing-after-2008", group="long",
         q="Did productivity stop growing after 2008?",
         title="Did UK productivity stop growing after 2008?",
         ids=["productivity"], chart="line", trans="none", start=1971, end=2025, era="bands",
         short={"productivity": "Output per hour"},
         say=say_prod,
         why="One series over half a century. A line shows the change of slope — the bend at 2008 — and the bend is the whole story.",
         care="Productivity is output per hour worked across the whole economy. It is hard to measure and is revised often, so the last year or two may move."),
    dict(key="crime", slug="has-crime-gone-up-in-england-and-wales", group="myth",
         q="Has crime gone up?",
         title="Has crime gone up in England and Wales?",
         ids=["csew", "prc"], chart="line", trans="index", start=2002, end=2025, era="bands",
         short={"csew": "Crime Survey", "prc": "Police recorded"},
         say=say_crime,
         why="Two measures of the same thing at very different sizes. Rebasing both to 100 shows the direction of each, and the year they part ways.",
         care="Police figures rose from 2014 largely because recording was tightened after inspectors found crimes going unrecorded. The survey misses crimes against businesses, only counts fraud from 2016, and paused in 2020."),
    dict(key="happy", slug="is-britain-getting-unhappier", group="myth",
         q="Is Britain getting unhappier?",
         title="Is Britain getting unhappier?",
         ids=["wbhappy", "wbsatisfied", "wbworthwhile", "wbanxiety"], chart="dots", trans="none", start=2011, end=2022, era="off",
         domain=[0, 10],
         short={"wbhappy": "Happiness", "wbsatisfied": "Life satisfaction", "wbworthwhile": "Feeling worthwhile", "wbanxiety": "Anxiety"},
         say=say_happy,
         why="The scale runs from 0 to 10, so the axis does too. Zoom in to fit the data — as most charts, and the explorer by default, do — and a quarter-point wobble fills the frame.",
         care="These are averages of a very large survey, so a tenth of a point is a real change across the population, even if no one person would notice it. Lower is better for anxiety."),
    dict(key="deaths", slug="are-more-people-dying-than-ever-in-england-and-wales", group="myth",
         q="Are more people dying than ever?",
         title="Are more people dying than ever in England and Wales?",
         ids=["deaths"], chart="line", trans="none", start=1900, end=2025, era="off", zero=True,
         short={"deaths": "Deaths registered"},
         say=say_deaths,
         why="The axis starts at zero, which shows a flat line for what it is. Why it is flat is the surprise: far more people, each living far longer.",
         care="These are deaths registered in the year, which can lag the death itself — most of all when a coroner is involved."),
    dict(key="saving", slug="has-britain-stopped-saving", group="myth",
         q="Has Britain stopped saving?",
         title="Has Britain stopped saving?",
         ids=["saving"], chart="line", trans="none", start=1963, end=2025, era="bands", mean=True, zero=True,
         short={"saving": "Saving ratio"},
         say=say_saving,
         why="A dashed line at the long-run average turns ‘is it low?’ into something you can see: the ratio crosses it again and again, which is what no trend looks like.",
         care="The saving ratio is what is left of disposable income after spending, so it falls when spending rises as well as when income falls. It is revised heavily, often years later."),
    dict(key="trade", slug="did-brexit-tip-britain-into-a-trade-deficit", group="myth",
         q="Did Brexit tip Britain into a trade deficit?",
         title="Did Brexit tip Britain into a trade deficit?",
         ids=["tradebal"], chart="bar", trans="pctgdp", start=1948, end=2025, era="bands", signs=["Surplus", "Deficit"], note=True,
         say=say_trade,
         why="A balance can sit either side of zero. Columns above and below the line show each year’s surplus or deficit, and as a share of GDP 1950 and 2020 compare fairly.",
         care="This is goods and services together: a long-standing deficit in goods is partly offset by a surplus in services. Trade figures are revised often, and trade in precious metals can swing a single year."),
    dict(key="police", slug="do-more-police-officers-mean-more-crimes-charged", group="myth",
         q="Do more police officers mean more crimes charged?",
         title="Do more police officers mean more crimes charged?",
         ids=["policeofficers", "chargerate"], chart="scatter", trans="none", start=2014, end=2025, era="off",
         short={"policeofficers": "Police officers (FTE)", "chargerate": "Charge rate, % of offences"},
         say=say_police,
         why="Each dot is a year, placed by officer numbers across and charge rate up. If more officers meant more charges the dots would climb to the right. Joining them in time order shows what is really going on.",
         care="A scatter of yearly totals cannot show cause either way. Charge rates also depend on how crimes are recorded and what kinds are reported, and both changed over these years. Officers are counted at March, charge rates by financial year."),
]


# ── the numbers behind one question ─────────────────────────────────

def short_unit(u: str) -> str:
    """The explorer's short unit: '£ per week' not '£ per week, cash'."""
    import re
    u = str(u or "")
    u = re.sub(r",\s*cash$", "", u, flags=re.I)
    u = re.sub(r",\s*\d{4} prices$", " real", u, flags=re.I)
    u = re.sub(r"^index.*", "index", u, flags=re.I)
    u = re.sub(r"^% change on a year earlier$", "%", u)
    u = re.sub(r" per year$", "/yr", u)
    return re.sub(r"^% of pupil enrolments$", "% of pupils", u)


def compute_sets(D: Data, Q: dict) -> list[dict]:
    """The plotted numbers: as published, rebased to the first year every
    series has, or as a share of GDP — the explorer's transforms."""
    base = None
    if Q["trans"] == "index":
        base = next((y for y in range(Q["start"], Q["end"] + 1) if all(D.val(i, y) is not None for i in Q["ids"])), None)
    out = []
    for i in Q["ids"]:
        pts = []
        for y in range(Q["start"], Q["end"] + 1):
            v = D.val(i, y)
            if v is not None and Q["trans"] == "index":
                v = v / D.val(i, base) * 100
            if v is not None and Q["trans"] == "pctgdp":
                g = D.ref("gdp", y)
                v = v / g * 100 if g else None
            pts.append([y, None if v is None else round(v, 4)])
        out.append({"id": i, "name": (Q.get("short") or {}).get(i, D.by_id[i]["name"]), "pts": pts})
    return out


def unit_label(D: Data, Q: dict) -> str:
    if Q["trans"] == "index":
        return f'index, {Q["start"]} = 100'
    if Q["trans"] == "pctgdp":
        return "% of GDP"
    return " · ".join(dict.fromkeys(short_unit(D.by_id[i]["unit"]) for i in Q["ids"]))


def span(sets: list[dict]) -> tuple[int, int]:
    ys = [y for s in sets for y, v in s["pts"] if v is not None]
    return min(ys), max(ys)


def description(sentence: str, limit: int = 158) -> str:
    """The search-result snippet: whole sentences up to the limit, or the
    first one cut at a word."""
    import re
    parts = re.split(r"(?<=[.?!])\s+(?=[A-Z])", sentence)
    out = ""
    for p in parts:
        if len(out) + len(p) + 1 > limit:
            break
        out = f"{out} {p}".strip()
    if not out:
        out = sentence[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—– ") + "…"
    return out


def build(db: dict) -> list[dict]:
    """Every question whose indicators are all in the bundle, worked out."""
    D = Data(db)
    out = []
    for Q in QUESTIONS:
        if not all(i in D.by_id for i in Q["ids"]):
            print(f"  question {Q['key']}: an indicator is missing, left out")
            continue
        sets = compute_sets(D, Q)
        try:
            sentence = Q["say"](D, Q, sets)
        except (TypeError, ValueError, ZeroDivisionError, StopIteration, KeyError, IndexError) as e:
            # a missing year makes an answer impossible to write; the chart
            # still stands, and the page says where the numbers are
            print(f"  question {Q['key']}: answer not written ({type(e).__name__}: {e})")
            sentence = "The chart shows the latest published figures; open it in the explorer for the numbers behind each year."
        x0, x1 = span(sets)
        series = [D.by_id[i] for i in Q["ids"]]
        item = {k: v for k, v in Q.items() if k != "say"}
        item.update({
            "from": Q["start"], "to": Q["end"],
            "sentence": sentence, "description": description(sentence),
            "unit": unit_label(D, Q), "x0": x0, "x1": x1,
            "geos": list(dict.fromkeys(s.get("geography", "") for s in series if s.get("geography"))),
            "sources": list(dict.fromkeys(s.get("source", "") for s in series)),
            "topics": list(dict.fromkeys(t for s in series for t in (s.get("topics") or []))),
            "explore": "~".join([",".join(Q["ids"]), Q["chart"], Q["trans"], str(Q["start"]), str(Q["end"]), Q["era"]]),
            "sets": sets,
        })
        del item["start"], item["end"]
        out.append(item)
    return out


# ── the chart, drawn at build time so the page needs no script ──────
# The same marks as the homepage's drawer, in plain SVG: round-number
# ticks, names at the line ends, a stronger line at 100 or 0, government
# shaded where the question asks for it. Colours come from the page's CSS
# variables, so the chart follows light and dark.

COL = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"]


def nice(raw: float) -> float:
    e = 10 ** math.floor(math.log10(raw))
    f = raw / e
    return (1 if f <= 1 else 2 if f <= 2 else 2.5 if f <= 2.5 else 5 if f <= 5 else 10) * e


def y_axis(vals: list[float], plot_h: float, incl: float | None = None) -> dict:
    v = [x for x in vals if x is not None]
    if incl is not None:
        v.append(incl)
    a, b = min(v), max(v)
    if a == b:
        a, b = a - 1, b + 1
    n = max(3, min(6, round(plot_h / 55)))
    st = nice((b - a) / n)
    mn, mx = math.floor(a / st + 1e-9) * st, math.ceil(b / st - 1e-9) * st
    ticks, t = [], mn
    while t <= mx + st / 2:
        ticks.append(round(t, 10))
        t += st
    return {"mn": mn, "mx": mx, "ticks": ticks, "st": st}


def tick_fmt(v: float, st: float) -> str:
    d = 0
    while d < 6 and abs(st * 10 ** d - round(st * 10 ** d)) > 1e-6:
        d += 1
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace("-", "−")
    return f"{v:.{d}f}".replace("-", "−")


def vfmt(v: float) -> str:
    a = abs(v)
    s = f"{v:,.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}"
    return s.replace("-", "−")


def wrap_name(name: str, max_ch: int = 24) -> list[str]:
    out, cur = [], ""
    for w in name.split():
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_ch:
            cur += " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out[:3] or [""]


def gutter(names: list[str], least: int) -> int:
    return min(200, max(least, round(max(len(l) for n in names for l in wrap_name(n)) * 6.1) + 22))


def frame(g: list, ax: dict, Y, x0: int, x1: int, sx, l: float, r: float, H: float,
          label: str | None = None, base: float | None = None, no_x: bool = False) -> None:
    for v in ax["ticks"]:
        cls = "baseline" if base is not None and abs(v - base) < ax["st"] / 1e6 else "gridline"
        g.append(f'<line class="{cls}" x1="{l}" y1="{Y(v):.1f}" x2="{r}" y2="{Y(v):.1f}"/>')
        g.append(f'<text class="axlabel" x="{l - 9}" y="{Y(v) + 4:.1f}" text-anchor="end">{tick_fmt(v, ax["st"])}</text>')
    if base is not None and ax["mn"] < base < ax["mx"] and not any(abs(v - base) < 1e-9 for v in ax["ticks"]):
        g.append(f'<line class="baseline" x1="{l}" y1="{Y(base):.1f}" x2="{r}" y2="{Y(base):.1f}"/>')
    if label:
        g.append(f'<text class="axunit" x="0" y="11">{esc(label)}</text>')
    if no_x:
        return
    sp = x1 - x0
    step = 5 if sp > 24 else 2 if sp > 12 else 1
    per = (r - l) / max(1, sp)
    while step * per < 38 and step < sp:
        step = 2 if step < 2 else 5 if step < 5 else step * 2
    for yr in range(math.ceil(x0 / step) * step, x1 + 1, step):
        g.append(f'<text class="axlabel" x="{sx(yr):.1f}" y="{H - 6}" text-anchor="middle">{yr}</text>')


def bands(g: list, eras: list, pms: list, x0: float, x1: float, sx, top: float, bot: float, names: bool = True) -> None:
    for e in eras or []:
        f, t = max(e["from"], x0), min(e["to"], x1)
        if t > f:
            g.append(f'<rect class="band" x="{sx(f):.1f}" y="{top}" width="{sx(t) - sx(f):.1f}" height="{bot - top}" '
                     f'fill="{e["colour"]}"><title>{esc(e["party"])} {e["from"]}–{e["to"]}</title></rect>')
    if not names:
        return
    for k, (y, n) in enumerate(pms or []):
        end = pms[k + 1][0] if k + 1 < len(pms) else 1e9
        f, t = max(y, x0), min(end, x1)
        if t <= f:
            continue
        a, b = sx(f), sx(t)
        if y > x0:
            g.append(f'<line class="banddiv" x1="{a:.1f}" y1="{top - 14}" x2="{a:.1f}" y2="{bot}"/>')
        if b - a > len(n) * 5.6 + 10:
            g.append(f'<text class="bandlbl" x="{(a + b) / 2:.1f}" y="{top - 4}" text-anchor="middle">{esc(n)}</text>')


def line_path(pts, sx, Y) -> str:
    d, pen = [], False
    for x, v in pts:
        if v is None:
            pen = False
            continue
        d.append(f'{"L" if pen else "M"}{sx(x):.1f} {Y(v):.1f}')
        pen = True
    return " ".join(d)


def end_labels(g: list, labels: list[dict], lx: float, floor_y: float) -> None:
    """Names and values at the line ends, nudged apart, kept above the floor."""
    L = sorted(({**l, "names": wrap_name(l["name"])} for l in labels), key=lambda l: l["cy"])
    floor = -1e9
    for l in L:
        l["h"] = len(l["names"]) * 12 + 12
        l["top"] = max(l["cy"] - 9, floor + 6)
        floor = l["top"] + l["h"]
    ceil = floor_y
    for l in reversed(L):
        if l["top"] + l["h"] > ceil:
            l["top"] = ceil - l["h"]
        ceil = l["top"] - 6
    for l in L:
        y = l["top"] + 9
        if l["cx"] < lx - 14 or abs(l["top"] + 9 - l["cy"]) > 3:
            g.append(f'<path class="leader" d="M{l["cx"] + 6:.1f} {l["cy"]:.1f} L{lx - 6} {l["top"] + 5:.1f}" stroke="{l["colour"]}"/>')
        for n in l["names"]:
            g.append(f'<text class="endlbl" x="{lx}" y="{y:.1f}" fill="{l["colour"]}">{esc(n)}</text>')
            y += 12
        g.append(f'<text class="endval" x="{lx}" y="{y:.1f}">{esc(l["val"])}</text>')


def svg(q: dict, db: dict, W: int = 820) -> str:
    """The question's chart as an SVG string."""
    sets = [{**s, "colour": COL[k % 4]} for k, s in enumerate(q["sets"])]
    by_id = {s["id"]: s for s in db["series"]}
    narrow = W < 600
    H = (4 * 150 if narrow else 2 * 175) if q["chart"] == "small" else (300 if narrow else 360)
    g: list[str] = []
    {"line": _line, "dots": _line, "gap": _line, "small": _small, "stack": _stack,
     "slope": _slope, "bar": _bar, "scatter": _scatter}[q["chart"]](g, q, sets, W, H, db, by_id)
    names = ", ".join(by_id[s["id"]]["name"] for s in sets)
    label = f'{q["title"]} {TYPE_NAME[q["chart"]]} chart of {names}, {q["x0"]} to {q["x1"]}.'
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
            + "".join(g) + "</svg>")


def left_for(ax: dict) -> int:
    """Room for the widest tick label: '1,000,000' needs more than '80'."""
    return max(52, round(max(len(tick_fmt(v, ax["st"])) for v in ax["ticks"]) * 6.8) + 14)


def _axis(q, vals, plot_h, incl=None):
    if q.get("domain"):
        mn, mx = q["domain"]
        st = nice((mx - mn) / 5)
        ticks, t = [], mn
        while t <= mx + st / 2:
            ticks.append(round(t, 10))
            t += st
        return {"mn": mn, "mx": mx, "ticks": ticks, "st": st}
    return y_axis(vals + ([0] if q.get("zero") else []), plot_h, incl)


def _line(g, q, sets, W, H, db, by_id):
    x0, x1 = q["x0"], q["x1"]
    bnd = q["era"] == "bands"
    T, B, R = 26 + (16 if bnd else 0), 26, gutter([s["name"] for s in sets], 60)
    ax = _axis(q, [v for s in sets for _, v in s["pts"]], H - T - B, 100 if q["trans"] == "index" else None)
    L = left_for(ax)
    sx = lambda x: L + (x - x0) / max(1, x1 - x0) * (W - L - R)
    Y = lambda v: T + (1 - (v - ax["mn"]) / (ax["mx"] - ax["mn"])) * (H - T - B)
    if bnd:
        bands(g, db.get("eras"), db.get("pms"), x0, x1, sx, T, H - B)
    frame(g, ax, Y, x0, x1, sx, L, W - R, H, q["unit"],
          100 if q["trans"] == "index" else (0 if ax["mn"] < 0 < ax["mx"] else None))
    if q["chart"] == "gap" and len(sets) == 2:
        A, Bs = sets
        for i in range(len(A["pts"]) - 1):
            (ya, a0), (yb, a1) = A["pts"][i], A["pts"][i + 1]
            b0, b1 = Bs["pts"][i][1], Bs["pts"][i + 1][1]
            if None in (a0, a1, b0, b1):
                continue

            def seg(xa, pa, qa, xb, pb, qb):
                col = A["colour"] if (pa + pb) / 2 >= (qa + qb) / 2 else Bs["colour"]
                g.append(f'<path d="M{sx(xa):.1f} {Y(pa):.1f} L{sx(xb):.1f} {Y(pb):.1f} L{sx(xb):.1f} {Y(qb):.1f} '
                         f'L{sx(xa):.1f} {Y(qa):.1f} Z" fill="{col}" opacity=".2"/>')
            if (a0 - b0) * (a1 - b1) < 0:
                t = (a0 - b0) / ((a0 - b0) - (a1 - b1))
                xm, vm = ya + t, a0 + (a1 - a0) * t
                seg(ya, a0, b0, xm, vm, vm)
                seg(xm, vm, vm, yb, a1, b1)
            else:
                seg(ya, a0, b0, yb, a1, b1)
    if q.get("mean"):
        v = [x for _, x in sets[0]["pts"] if x is not None]
        m = sum(v) / len(v)
        g.append(f'<line class="qmean" x1="{L}" x2="{W - R}" y1="{Y(m):.1f}" y2="{Y(m):.1f}"/>')
        g.append(f'<text class="qnote" x="{L + 6}" y="{Y(m) - 6:.1f}">Average, {m:.1f}</text>')
    labels = []
    for s in sets:
        seg_pts = [(x, v) for x, v in s["pts"] if v is not None]
        if not seg_pts:
            continue
        if q["chart"] == "dots":
            for x, v in seg_pts:
                g.append(f'<circle class="qdot" cx="{sx(x):.1f}" cy="{Y(v):.1f}" r="4" fill="{s["colour"]}"/>')
        else:
            g.append(f'<path class="line" d="{line_path(s["pts"], sx, Y)}" stroke="{s["colour"]}"/>')
            for d in by_id[s["id"]].get("discontinuities") or []:
                yb = d.get("year")
                p = next(((x, v) for x, v in seg_pts if x >= (yb or 0)), None)
                if yb and x0 < yb <= x1 and p:
                    g.append(f'<circle cx="{sx(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="4" class="hollow" stroke="{s["colour"]}" '
                             f'stroke-width="2"><title>Break at {yb}: {esc(d.get("note", ""))}</title></circle>')
        lx_, lv = seg_pts[-1]
        if q["chart"] != "dots":
            g.append(f'<circle class="enddot" cx="{sx(lx_):.1f}" cy="{Y(lv):.1f}" r="3.6" fill="{s["colour"]}"/>')
        labels.append({"colour": s["colour"], "cx": sx(lx_), "cy": Y(lv), "name": s["name"],
                       "val": vfmt(lv) + (f" in {lx_}" if lx_ < x1 else "")})
    end_labels(g, labels, W - R + 12, H - B + 4)


def _small(g, q, sets, W, H, db, by_id):
    cols = 1 if W < 600 else 2
    rows = math.ceil(len(sets) / cols)
    cw, ch = W / cols, H / rows
    x0, x1 = q["from"], q["to"]
    for k, s in enumerate(sets):
        ox, oy = (k % cols) * cw, (k // cols) * ch
        top, bot, l, r = oy + 34, oy + ch - 26, ox + 50, ox + cw - (34 if cols > 1 and k % cols == 0 else 16)
        pts = s["pts"]
        name = s["name"]
        if max((v or 0) for _, v in pts) >= 1e6:
            pts = [[y, None if v is None else v / 1e6] for y, v in pts]
            name = name[:-1] + ", millions)" if name.endswith(")") else name + " (millions)"
        sx = lambda x, l=l, r=r: l + (x - x0) / max(1, x1 - x0) * (r - l)
        ax = y_axis([v for _, v in pts], bot - top)
        Y = lambda v, ax=ax, top=top, bot=bot: top + (1 - (v - ax["mn"]) / (ax["mx"] - ax["mn"])) * (bot - top)
        if q["era"] == "bands":
            bands(g, db.get("eras"), [], x0, x1, sx, top, bot, names=False)
        frame(g, ax, Y, x0, x1, sx, l, r, bot + 20)
        g.append(f'<text class="qsmt" x="{ox + 2}" y="{oy + 14}" fill="{s["colour"]}">{esc(name)}</text>')
        g.append(f'<path class="line" d="{line_path(pts, sx, Y)}" stroke="{s["colour"]}"/>')
        last = next(((x, v) for x, v in reversed(pts) if v is not None), None)
        if last:
            g.append(f'<circle class="enddot" cx="{sx(last[0]):.1f}" cy="{Y(last[1]):.1f}" r="3.6" fill="{s["colour"]}"/>')
            g.append(f'<text class="endval" x="{sx(last[0]) - 6:.1f}" y="{Y(last[1]) - 8:.1f}" text-anchor="end">{vfmt(last[1])}</text>')


def _stack(g, q, sets, W, H, db, by_id):
    x0, x1 = q["x0"], q["x1"]
    T, B, L, R = 26, 26, 52, gutter([s["name"] for s in sets], 60)
    sx = lambda x: L + (x - x0) / max(1, x1 - x0) * (W - L - R)
    years = list(range(x0, x1 + 1))
    val = lambda s, y: next((v for yy, v in s["pts"] if yy == y), None) or 0
    tops = [sum(val(s, y) for s in sets) for y in years]
    ax = ({"mn": 0, "mx": 100, "ticks": [0, 25, 50, 75, 100], "st": 25} if all(abs(t - 100) < 1.5 for t in tops)
          else y_axis([0] + tops, H - T - B, 0))
    Y = lambda v: T + (1 - (v - ax["mn"]) / (ax["mx"] - ax["mn"])) * (H - T - B)
    frame(g, ax, Y, x0, x1, sx, L, W - R, H, q["unit"], 0)
    lower = [0.0] * len(years)
    labels = []
    for s in sets:
        upper = [lower[i] + val(s, y) for i, y in enumerate(years)]
        d = ("M" + " L".join(f"{sx(y):.1f} {Y(upper[i]):.1f}" for i, y in enumerate(years)) + " L"
             + " L".join(f"{sx(y):.1f} {Y(lower[i]):.1f}" for i, y in reversed(list(enumerate(years)))) + " Z")
        g.append(f'<path d="{d}" fill="{s["colour"]}" opacity=".78" stroke="var(--surface)" stroke-width="1"/>')
        labels.append({"colour": s["colour"], "cx": sx(x1), "cy": Y((upper[-1] + lower[-1]) / 2),
                       "name": s["name"], "val": f"{val(s, x1):.1f}%"})
        lower = upper
    end_labels(g, labels, W - R + 12, H - B + 4)


def _slope(g, q, sets, W, H, db, by_id):
    a, b = q["from"], q["to"]
    T, B, L = 40, 24, (150 if W >= 600 else 44)
    R = gutter([s["name"] for s in sets], 70) + (60 if W >= 600 else 0)
    ends = []
    for s in sets:
        v0 = next((v for y, v in s["pts"] if y == a), None)
        v1 = next((v for y, v in s["pts"] if y == b), None)
        if v0 is not None and v1 is not None:
            ends.append((s, v0, v1))
    ax = y_axis([v for _, v0, v1 in ends for v in (v0, v1)], H - T - B, 100 if q["trans"] == "index" else None)
    Y = lambda v: T + (1 - (v - ax["mn"]) / (ax["mx"] - ax["mn"])) * (H - T - B)
    XA, XB = L, W - R
    g.append(f'<text class="axunit" x="0" y="11">{esc(q["unit"])}</text>')
    for x, y in ((XA, a), (XB, b)):
        g.append(f'<line class="gridline" x1="{x}" x2="{x}" y1="{T - 8}" y2="{H - B}"/>')
        g.append(f'<text class="axlabel strong" x="{x}" y="{T - 14}" text-anchor="middle">{y}</text>')
    seen, prev = set(), None
    for s, v0, _ in sorted(ends, key=lambda e: Y(e[1])):
        t = vfmt(v0)
        if t in seen:
            continue
        seen.add(t)
        y = Y(v0) if prev is None else max(Y(v0), prev + 14)
        prev = y
        g.append(f'<text class="axlabel" x="{XA - 10}" y="{y + 4:.1f}" text-anchor="end">{t}</text>')
    labels = []
    for s, v0, v1 in ends:
        g.append(f'<line class="line" x1="{XA}" y1="{Y(v0):.1f}" x2="{XB}" y2="{Y(v1):.1f}" stroke="{s["colour"]}" stroke-width="2.5"/>')
        g.append(f'<circle class="enddot" cx="{XA}" cy="{Y(v0):.1f}" r="4" fill="{s["colour"]}"/>'
                 f'<circle class="enddot" cx="{XB}" cy="{Y(v1):.1f}" r="4.5" fill="{s["colour"]}"/>')
        labels.append({"colour": s["colour"], "cx": XB, "cy": Y(v1), "name": s["name"], "val": f"{vfmt(v1)}  ({pc(v0, v1)})"})
    end_labels(g, labels, XB + 14, H - B + 4)


def _bar(g, q, sets, W, H, db, by_id):
    s = sets[0]
    x0, x1 = q["x0"], q["x1"]
    bnd = q["era"] == "bands"
    T, B, R = 26 + (16 if bnd else 0), 26, 20
    ax = y_axis([v for _, v in s["pts"]], H - T - B, 0)
    L = left_for(ax)
    slot = (W - L - R) / (x1 - x0 + 1)
    sx = lambda x: L + slot * (x - x0 + .5)
    Y = lambda v: T + (1 - (v - ax["mn"]) / (ax["mx"] - ax["mn"])) * (H - T - B)
    if bnd:
        bands(g, db.get("eras"), db.get("pms"), x0 - .5, x1 + .5, sx, T, H - B)
    frame(g, ax, Y, x0, x1, sx, L, W - R, H, f'{by_id[s["id"]]["name"]}, {q["unit"]}', 0)
    neg = COL[1] if q.get("signs") else s["colour"]
    bw = max(1.2, slot * .78)
    for y, v in s["pts"]:
        if v is None:
            continue
        a, b = Y(max(0, v)), Y(min(0, v))
        g.append(f'<rect x="{sx(y) - bw / 2:.1f}" y="{a:.1f}" width="{bw:.1f}" height="{max(.6, b - a):.1f}" '
                 f'rx="{min(1.5, bw / 3):.1f}" fill="{neg if v < 0 else s["colour"]}"><title>{y}: {vfmt(v)}</title></rect>')
    if q.get("note"):
        p = [(y, v) for y, v in s["pts"] if v is not None]
        y, v = max(p, key=lambda t: abs(t[1]))
        x = sx(y)
        anc = "end" if x > W - R - 60 else "start" if x < L + 60 else "middle"
        g.append(f'<text class="qnote strong" x="{x:.1f}" y="{Y(v) - 7 if v >= 0 else Y(v) + 15:.1f}" text-anchor="{anc}">{y}: {vfmt(v)}</text>')


def _scatter(g, q, sets, W, H, db, by_id):
    X, Yv = sets
    pr = [(y, x, Yv["pts"][i][1]) for i, (y, x) in enumerate(X["pts"]) if x is not None and Yv["pts"][i][1] is not None]
    T, R, B, L = 28, 24, 40, 52
    ax, ay = y_axis([q_[1] for q_ in pr], W - L - R), y_axis([q_[2] for q_ in pr], H - T - B)
    PX = lambda v: L + (v - ax["mn"]) / (ax["mx"] - ax["mn"]) * (W - L - R)
    PY = lambda v: T + (1 - (v - ay["mn"]) / (ay["mx"] - ay["mn"])) * (H - T - B)
    for v in ay["ticks"]:
        g.append(f'<line class="gridline" x1="{L}" x2="{W - R}" y1="{PY(v):.1f}" y2="{PY(v):.1f}"/>')
        g.append(f'<text class="axlabel" x="{L - 9}" y="{PY(v) + 4:.1f}" text-anchor="end">{tick_fmt(v, ay["st"])}</text>')
    xt = ax["ticks"][::2] if len(ax["ticks"]) > 7 else ax["ticks"]
    for v in xt:
        g.append(f'<line class="gridline" x1="{PX(v):.1f}" x2="{PX(v):.1f}" y1="{T}" y2="{H - B}" opacity=".5"/>')
        g.append(f'<text class="axlabel" x="{PX(v):.1f}" y="{H - B + 16}" text-anchor="middle">{tick_fmt(v, ax["st"])}</text>')
    g.append(f'<text class="axunit" x="0" y="11">{esc(Yv["name"])} ↑</text>')
    g.append(f'<text class="axunit" x="{W - R}" y="{H - 4}" text-anchor="end">{esc(X["name"])} →</text>')
    g.append('<path d="' + " ".join(f'{"L" if i else "M"}{PX(p[1]):.1f} {PY(p[2]):.1f}' for i, p in enumerate(pr))
             + '" fill="none" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="3 3" opacity=".6"/>')
    for i, (y, vx, vy) in enumerate(pr):
        t = i / (len(pr) - 1) if len(pr) > 1 else 1
        g.append(f'<circle class="qdot" cx="{PX(vx):.1f}" cy="{PY(vy):.1f}" r="5.5" fill="{COL[0]}" opacity="{.3 + .7 * t:.2f}"/>')
        g.append(f'<text class="qyr" x="{PX(vx) + 8:.1f}" y="{PY(vy) - 6:.1f}">{y}</text>')
