#!/usr/bin/env python3
"""
Generates the placeholder catalogue embedded in explore.html.

EVERY NUMBER THIS PRODUCES IS INVENTED. It exists to exercise the layout,
the geography selector, the transform legality rules and the map. It is
replaced wholesale by data/bundle.json once ingest.py runs successfully.

The *metadata* is real and worth keeping: names, sources, units, kinds,
year bases, geographic coverage and known discontinuities are all as
published. Only the values are fake.
"""
import json, math, random

# ── geography ────────────────────────────────────────────────────────────
# level: 0 = UK only, 1 = nations, 2 = ITL1 regions
AREAS = [
    # code, name, short, level-at-which-it-appears, hex col, hex row, parent
    ("UK",  "United Kingdom",            "UK",      0, None, None, None),
    ("ENG", "England",                   "Eng",     1, 1, 1, "UK"),
    ("SCT", "Scotland",                  "Sco",     1, 1, 0, "UK"),
    ("WLS", "Wales",                     "Wal",     1, 0, 1, "UK"),
    ("NIR", "Northern Ireland",          "NI",      1, 0, 0, "UK"),
    ("UKC", "North East",                "NE",      2, 2, 1, "ENG"),
    ("UKD", "North West",                "NW",      2, 1, 2, "ENG"),
    ("UKE", "Yorkshire and The Humber",  "Y&H",     2, 2, 2, "ENG"),
    ("UKF", "East Midlands",             "E Mid",   2, 3, 3, "ENG"),
    ("UKG", "West Midlands",             "W Mid",   2, 2, 3, "ENG"),
    ("UKH", "East of England",           "East",    2, 4, 3, "ENG"),
    ("UKI", "London",                    "Ldn",     2, 3, 4, "ENG"),
    ("UKJ", "South East",                "SE",      2, 2, 4, "ENG"),
    ("UKK", "South West",                "SW",      2, 1, 4, "ENG"),
    ("SCT2","Scotland",                  "Sco",     2, 2, 0, "UK"),
    ("WLS2","Wales",                     "Wal",     2, 1, 3, "UK"),
    ("NIR2","Northern Ireland",          "NI",      2, 0, 2, "UK"),
]

LEVELS = {
    "uk":     ["UK"],
    "nation": ["UK", "ENG", "SCT", "WLS", "NIR"],
    "region": ["UKC","UKD","UKE","UKF","UKG","UKH","UKI","UKJ","UKK","SCT2","WLS2","NIR2"],
}

# rough relative level multipliers so the map isn't uniform noise
AREA_TILT = {
    "UK":1.00,"ENG":1.02,"SCT":0.94,"WLS":0.88,"NIR":0.85,
    "UKC":0.82,"UKD":0.90,"UKE":0.88,"UKF":0.93,"UKG":0.92,
    "UKH":1.08,"UKI":1.45,"UKJ":1.22,"UKK":1.05,
    "SCT2":0.94,"WLS2":0.88,"NIR2":0.85,
}

# ── the catalogue ────────────────────────────────────────────────────────
# id | name | topic | unit | kind | source | geo | basis | start | shape | disc
#
# kind drives transform legality:
#   cash  – money at current prices    → real terms, per person, % of GDP all legal
#   count – a number of things         → per person legal, real terms not
#   index – already an index number    → rebase legal, real terms not
#   rate  – per-100k / per-1000        → rebase and per person both meaningless
#   pct   – a percentage               → same
#   ratio – a ratio                    → same
#   level – a physical/volume quantity → per person legal
#
# shape: rough trajectory for the invented series
#   'rise','fall','flat','hump','dip','vol','break2020','crisis2008'

S = [
# ── ECONOMY ──────────────────────────────────────────────────────────────
("gdp",        "Gross domestic product, chained volume", "Economy","£bn 2022 prices","cash","ONS","region","calendar",1980,"crisis2008",None),
("gdppc",      "GDP per head",                          "Economy","£ 2022 prices","cash","ONS","region","calendar",1980,"crisis2008",None),
("gva",        "Gross value added (balanced)",          "Economy","£bn","cash","ONS","region","calendar",1998,"rise",None),
("gdpdef",     "GDP deflator",                          "Economy","Index 2022=100","index","ONS / HM Treasury","uk","financial",1980,"rise",None),
("cpi",        "Consumer Prices Index",                 "Economy","Index 2015=100","index","ONS","uk","calendar",1988,"rise",None),
("cpih",       "CPIH (incl. owner occupiers' housing)", "Economy","Index 2015=100","index","ONS","uk","calendar",2005,"rise",None),
("rpi",        "Retail Prices Index",                   "Economy","Index Jan 1987=100","index","ONS","uk","calendar",1987,"rise",[(2013,"Lost National Statistic status")]),
("cpirate",    "CPI inflation rate",                    "Economy","% per year","pct","ONS","uk","calendar",1989,"vol",None),
("cpifood",    "CPI: food and non-alcoholic drinks",    "Economy","Index 2015=100","index","ONS","uk","calendar",1996,"rise",None),
("cpienergy",  "CPI: housing, water and fuels",         "Economy","Index 2015=100","index","ONS","uk","calendar",1996,"rise",None),
("cpitrans",   "CPI: transport",                        "Economy","Index 2015=100","index","ONS","uk","calendar",1996,"rise",None),
("ppiin",      "Producer Price Index, input",           "Economy","Index 2015=100","index","ONS","uk","calendar",1996,"vol",None),
("ppiout",     "Producer Price Index, output",          "Economy","Index 2015=100","index","ONS","uk","calendar",1996,"rise",None),
("sppi",       "Services Producer Price Index",         "Economy","Index 2015=100","index","ONS","uk","calendar",1998,"rise",None),
("unemp",      "Unemployment rate, 16+",                "Economy","%","pct","ONS Labour Force Survey","region","calendar",1992,"dip",[(2024,"LFS to Transformed LFS")]),
("emprate",    "Employment rate, 16–64",                "Economy","%","pct","ONS Labour Force Survey","region","calendar",1992,"rise",[(2024,"LFS to Transformed LFS")]),
("inact",      "Economic inactivity rate, 16–64",       "Economy","%","pct","ONS Labour Force Survey","region","calendar",1992,"dip",[(2024,"LFS to Transformed LFS")]),
("claimant",   "Claimant count",                        "Economy","Thousands","count","ONS / DWP","region","calendar",1992,"dip",[(2013,"Universal Credit rollout changes basis")]),
("vacancies",  "Job vacancies",                         "Economy","Thousands","count","ONS","uk","calendar",2001,"hump",None),
("redund",     "Redundancy rate",                       "Economy","Per 1,000 employees","rate","ONS","uk","calendar",1995,"vol",None),
("awe",        "Average weekly earnings, total pay",    "Economy","£ per week","cash","ONS","uk","calendar",2000,"rise",None),
("awereal",    "Average weekly earnings, real terms",   "Economy","£ per week 2022 prices","cash","ONS","uk","calendar",2000,"flat",None),
("prod",       "Output per hour worked",                "Economy","Index 2019=100","index","ONS","region","calendar",1997,"crisis2008",None),
("bankrate",   "Bank Rate",                             "Economy","%","pct","Bank of England","uk","calendar",1980,"dip",None),
("gilt10",     "10-year gilt yield",                    "Economy","%","pct","Bank of England","uk","calendar",1985,"dip",None),
("eri",        "Sterling effective exchange rate",      "Economy","Index 2005=100","index","Bank of England","uk","calendar",1990,"fall",None),
("businv",     "Business investment",                   "Economy","£bn 2022 prices","cash","ONS","uk","calendar",1997,"rise",None),
("caccount",   "Current account balance",               "Economy","% of GDP","pct","ONS","uk","calendar",1980,"fall",None),
("insolv",     "Company insolvencies",                  "Economy","Count","count","Insolvency Service","nation","calendar",1990,"vol",None),
("retail",     "Retail sales volume",                   "Economy","Index 2019=100","index","ONS","uk","calendar",1996,"rise",[(2020,"Pandemic trading restrictions")]),
("iop",        "Index of Production",                   "Economy","Index 2019=100","index","ONS","uk","calendar",1990,"fall",None),
("ios",        "Index of Services",                     "Economy","Index 2019=100","index","ONS","uk","calendar",1990,"rise",None),

# ── HOUSING ──────────────────────────────────────────────────────────────
("hpi",        "House Price Index",                     "Housing","Index 2015=100","index","ONS / HM Land Registry","region","calendar",1995,"rise",None),
("hpavg",      "Average house price",                   "Housing","£","cash","ONS / HM Land Registry","region","calendar",1995,"rise",None),
("hpe",        "House price to earnings ratio",         "Housing","Ratio","ratio","ONS","region","calendar",1997,"rise",None),
("pipr",       "Private rent index",                    "Housing","Index 2015=100","index","ONS","region","calendar",2005,"rise",[(2024,"IPHRP replaced by PIPR")]),
("rentavg",    "Average monthly private rent",          "Housing","£ per month","cash","ONS","region","calendar",2005,"rise",None),
("completions","Net additional dwellings",              "Housing","Count","count","MHCLG","region","financial",1997,"hump",None),
("starts",     "Housing starts",                        "Housing","Count","count","MHCLG","region","financial",1997,"vol",None),
("affordable", "Affordable housing supply",             "Housing","Count","count","MHCLG","region","financial",1997,"dip",None),
("socialstock","Social housing stock",                  "Housing","Thousands of dwellings","count","MHCLG","region","financial",1997,"fall",None),
("rtb",        "Right to Buy sales",                    "Housing","Count","count","MHCLG","region","financial",1997,"dip",None),
("tempacc",    "Households in temporary accommodation", "Housing","Count","count","MHCLG","region","financial",1998,"rise",None),
("homeless",   "Statutory homelessness assessments",    "Housing","Count","count","MHCLG","region","financial",2000,"rise",[(2018,"Homelessness Reduction Act changes basis")]),
("roughsleep", "Rough sleeping snapshot",               "Housing","Count","count","MHCLG","region","calendar",2010,"hump",None),
("mortapp",    "Mortgage approvals for house purchase", "Housing","Thousands per month","count","Bank of England","uk","calendar",1993,"crisis2008",None),
("ftbdep",     "First-time buyer average deposit",      "Housing","£","cash","UK Finance","region","calendar",2000,"rise",None),
("ownocc",     "Owner occupation rate",                 "Housing","%","pct","English Housing Survey","region","financial",1997,"dip",None),
("prsshare",   "Private rented sector share",           "Housing","%","pct","English Housing Survey","region","financial",1997,"rise",None),
("nondecent",  "Non-decent homes",                      "Housing","%","pct","English Housing Survey","nation","financial",2006,"fall",None),
("planning",   "Planning permissions granted",          "Housing","Count","count","MHCLG","region","financial",2005,"flat",None),
("epcabc",     "Dwellings rated EPC C or better",       "Housing","%","pct","MHCLG","region","calendar",2010,"rise",None),
("vacant",     "Long-term vacant dwellings",            "Housing","Count","count","MHCLG","region","calendar",2004,"flat",None),

# ── EDUCATION ────────────────────────────────────────────────────────────
("att8",       "Attainment 8 score",                    "Education","Points","level","DfE","region","academic",2016,"flat",[(2020,"Centre-assessed grades")]),
("gcse95",     "Grade 5+ in English and maths",         "Education","%","pct","DfE","region","academic",2016,"flat",[(2020,"Centre-assessed grades")]),
("prog8",      "Progress 8 score",                      "Education","Points","level","DfE","region","academic",2016,"flat",None),
("gap",        "Disadvantage attainment gap index",     "Education","Index","index","DfE","region","academic",2011,"dip",[(2020,"Centre-assessed grades")]),
("ks2",        "KS2 expected standard, reading writing maths","Education","%","pct","DfE","region","academic",2016,"rise",[(2020,"No assessments held")]),
("ptr",        "Pupil–teacher ratio, secondary",        "Education","Ratio","ratio","DfE","region","academic",2010,"rise",None),
("tvac",       "Teacher vacancy rate",                  "Education","Per 1,000 teachers","rate","DfE","region","academic",2010,"rise",None),
("twast",      "Teacher wastage rate",                  "Education","%","pct","DfE","nation","academic",2010,"rise",None),
("funding",    "School funding per pupil, real terms",  "Education","£ per pupil 2022 prices","cash","IFS / DfE","region","financial",2010,"dip",None),
("ehcp",       "Pupils with an EHC plan",               "Education","Count","count","DfE","region","academic",2015,"rise",None),
("sen",        "Pupils with SEN support",               "Education","%","pct","DfE","region","academic",2015,"rise",None),
("absence",    "Persistent absence rate",               "Education","%","pct","DfE","region","academic",2011,"break2020",[(2020,"Attendance recording changed")]),
("exclusion",  "Permanent exclusion rate",              "Education","Per 100 pupils","rate","DfE","region","academic",2011,"rise",None),
("suspension", "Suspension rate",                       "Education","Per 100 pupils","rate","DfE","region","academic",2011,"rise",None),
("fsm",        "Free school meal eligibility",          "Education","%","pct","DfE","region","academic",2011,"rise",None),
("heentry",    "Higher education entry rate, 18-year-olds","Education","%","pct","UCAS","nation","academic",2010,"rise",None),
("polar",      "HE entry rate, most deprived quintile", "Education","%","pct","UCAS","nation","academic",2010,"rise",None),
("apprent",    "Apprenticeship starts",                 "Education","Count","count","DfE","region","academic",2011,"fall",[(2017,"Apprenticeship levy introduced")]),
("neet",       "Young people not in education or work", "Education","%","pct","DfE / ONS","region","calendar",2001,"dip",None),
("classsize",  "Average infant class size",             "Education","Pupils","level","DfE","region","academic",2010,"flat",None),

# ── HEALTH ───────────────────────────────────────────────────────────────
("rtt",        "Referral to treatment waiting list",    "Health","Count of pathways","count","NHS England","region","financial",2008,"rise",[(2020,"Pandemic suspension of routine care")]),
("rtt18",      "Treated within 18 weeks",               "Health","%","pct","NHS England","region","financial",2008,"fall",None),
("ae4",        "A&E four-hour performance",             "Health","%","pct","NHS England","region","financial",2011,"fall",None),
("amb2",       "Category 2 ambulance response time",    "Health","Minutes","level","NHS England","region","financial",2018,"rise",None),
("cancer62",   "Cancer 62-day standard met",            "Health","%","pct","NHS England","region","financial",2010,"fall",None),
("gpfte",      "GPs, full-time equivalent",             "Health","Count","count","NHS Digital","region","calendar",2015,"fall",None),
("gpappt",     "GP appointments",                       "Health","Millions per year","count","NHS Digital","region","calendar",2018,"rise",None),
("lifeexp",    "Life expectancy at birth",              "Health","Years","level","ONS","region","calendar",1991,"flat",None),
("hle",        "Healthy life expectancy at birth",      "Health","Years","level","ONS","region","calendar",2009,"fall",None),
("infmort",    "Infant mortality rate",                 "Health","Per 1,000 live births","rate","ONS","region","calendar",1990,"fall",None),
("asmr",       "Age-standardised mortality rate",       "Health","Per 100,000","rate","ONS","region","calendar",1990,"fall",[(2020,"Pandemic")]),
("bedocc",     "Overnight bed occupancy",               "Health","%","pct","NHS England","region","financial",2011,"rise",None),
("delayed",    "Patients not discharged when ready",    "Health","Count per day","count","NHS England","nation","financial",2015,"rise",None),
("obesity",    "Adult obesity prevalence",              "Health","%","pct","NHS Digital","region","calendar",2000,"rise",None),
("smoking",    "Adult smoking prevalence",              "Health","%","pct","ONS","region","calendar",2011,"fall",None),
("drugdeath",  "Drug poisoning deaths",                 "Health","Per million","rate","ONS","region","calendar",1993,"rise",None),
("alcdeath",   "Alcohol-specific deaths",               "Health","Per 100,000","rate","ONS","region","calendar",2001,"rise",None),

# ── CRIME & JUSTICE ──────────────────────────────────────────────────────
("csew",       "Crime Survey incidence",                "Crime & Justice","Per 1,000 adults","rate","ONS","nation","financial",1997,"fall",[(2020,"Telephone survey during pandemic")]),
("recorded",   "Police recorded crime",                 "Crime & Justice","Per 1,000 population","rate","ONS / Home Office","region","financial",2003,"rise",[(2014,"Recording standards tightened")]),
("homicide",   "Homicide rate",                         "Crime & Justice","Per million","rate","ONS","region","financial",1997,"fall",None),
("knife",      "Knife-enabled offences",                "Crime & Justice","Count","count","Home Office","region","financial",2011,"rise",None),
("charge",     "Charge or summons rate",                "Crime & Justice","%","pct","Home Office","region","financial",2015,"fall",None),
("backlog",    "Crown Court open caseload",             "Crime & Justice","Count","count","Ministry of Justice","nation","financial",2014,"rise",None),
("prison",     "Prison population",                     "Crime & Justice","Count","count","Ministry of Justice","nation","calendar",1990,"rise",None),
("reoffend",   "Proven reoffending rate",               "Crime & Justice","%","pct","Ministry of Justice","region","financial",2010,"flat",None),
("police",     "Police officer headcount",              "Crime & Justice","FTE","count","Home Office","region","financial",2003,"dip",[(2019,"Police uplift programme")]),
("stopsearch", "Stop and search",                       "Crime & Justice","Per 1,000 population","rate","Home Office","region","financial",2007,"vol",None),

# ── TRANSPORT ────────────────────────────────────────────────────────────
("railjourneys","Rail passenger journeys",              "Transport","Millions","count","Office of Rail and Road","region","financial",1997,"break2020",[(2020,"Pandemic")]),
("railpunct",  "Trains on time",                        "Transport","%","pct","Office of Rail and Road","nation","financial",2015,"fall",None),
("busjourneys","Local bus passenger journeys",          "Transport","Millions","count","Department for Transport","region","financial",2004,"fall",None),
("busmiles",   "Local bus vehicle miles",               "Transport","Millions","level","Department for Transport","region","financial",2004,"fall",None),
("traffic",    "Road traffic volume",                   "Transport","Billion vehicle miles","level","Department for Transport","region","calendar",1993,"break2020",None),
("ksi",        "Killed or seriously injured",           "Transport","Count","count","Department for Transport","region","calendar",1990,"fall",[(2016,"CRASH injury reporting change")]),
("evshare",    "Electric share of new car registrations","Transport","%","pct","DVLA / SMMT","region","calendar",2015,"rise",None),
("airpax",     "Air passengers",                        "Transport","Millions","count","Civil Aviation Authority","nation","calendar",1997,"break2020",None),
("fuelprice",  "Average petrol pump price",             "Transport","Pence per litre","cash","Department for Energy","uk","calendar",1990,"rise",None),

# ── ENVIRONMENT & ENERGY ─────────────────────────────────────────────────
("ghg",        "Territorial greenhouse gas emissions",  "Environment & Energy","MtCO2e","level","DESNZ","nation","calendar",1990,"fall",None),
("ghgcons",    "Consumption-based emissions",           "Environment & Energy","MtCO2e","level","Defra","uk","calendar",1997,"fall",None),
("renewshare", "Renewable share of electricity",        "Environment & Energy","%","pct","DESNZ","nation","calendar",2000,"rise",None),
("gasprice",   "Domestic gas price",                    "Environment & Energy","Pence per kWh","cash","DESNZ","region","calendar",2004,"rise",None),
("elecprice",  "Domestic electricity price",            "Environment & Energy","Pence per kWh","cash","DESNZ","region","calendar",2004,"rise",None),
("no2",        "Roadside nitrogen dioxide",             "Environment & Energy","µg/m³","level","Defra","region","calendar",2000,"fall",None),
("pm25",       "Fine particulate matter",               "Environment & Energy","µg/m³","level","Defra","region","calendar",2010,"fall",None),
("spills",     "Storm overflow spill hours",            "Environment & Energy","Hours","level","Environment Agency","region","calendar",2020,"rise",None),
("recycling",  "Household waste recycled",              "Environment & Energy","%","pct","Defra","region","financial",2000,"rise",None),
("birds",      "Farmland bird index",                   "Environment & Energy","Index 1970=100","index","Defra / BTO","nation","calendar",1990,"fall",None),
("woodland",   "Woodland cover",                        "Environment & Energy","% of land area","pct","Forest Research","nation","calendar",1998,"rise",None),

# ── POPULATION & MIGRATION ───────────────────────────────────────────────
("population", "Population estimate",                   "Population & Migration","Thousands","count","ONS","region","calendar",1980,"rise",None),
("netmig",     "Net migration",                         "Population & Migration","Thousands","count","ONS","uk","calendar",1991,"rise",[(2021,"LTIM replaced by admin-based estimates")]),
("births",     "Live births",                           "Population & Migration","Count","count","ONS","region","calendar",1990,"fall",None),
("deaths",     "Deaths registered",                     "Population & Migration","Count","count","ONS","region","calendar",1990,"flat",None),
("tfr",        "Total fertility rate",                  "Population & Migration","Children per woman","ratio","ONS","region","calendar",1990,"fall",None),
("asylum",     "Asylum applications",                   "Population & Migration","Count","count","Home Office","uk","calendar",1997,"vol",None),
("asylumback", "Asylum cases awaiting decision",        "Population & Migration","Count","count","Home Office","uk","calendar",2010,"rise",None),
("workvisa",   "Work visas granted",                    "Population & Migration","Count","count","Home Office","uk","calendar",2005,"rise",[(2021,"Post-EU-exit immigration system")]),
("studyvisa",  "Study visas granted",                   "Population & Migration","Count","count","Home Office","uk","calendar",2005,"rise",None),
("foreignborn","Population born outside the UK",        "Population & Migration","%","pct","ONS","region","calendar",2004,"rise",None),

# ── PUBLIC SPENDING ──────────────────────────────────────────────────────
("tme",        "Total managed expenditure",             "Public Spending","% of GDP","pct","HM Treasury / OBR","uk","financial",1980,"vol",None),
("tmecash",    "Total managed expenditure, cash",       "Public Spending","£bn","cash","HM Treasury / OBR","uk","financial",1980,"rise",None),
("receipts",   "Public sector current receipts",        "Public Spending","% of GDP","pct","OBR","uk","financial",1980,"rise",None),
("psnb",       "Public sector net borrowing",           "Public Spending","% of GDP","pct","ONS / OBR","uk","financial",1980,"vol",None),
("psnd",       "Public sector net debt",                "Public Spending","% of GDP","pct","ONS / OBR","uk","financial",1980,"rise",None),
("healthspend","Health spending",                       "Public Spending","£bn 2022 prices","cash","HM Treasury","nation","financial",1997,"rise",None),
("edspend",    "Education spending",                    "Public Spending","£bn 2022 prices","cash","HM Treasury","nation","financial",1997,"flat",None),
("defspend",   "Defence spending",                      "Public Spending","% of GDP","pct","HM Treasury / NATO","uk","financial",1980,"fall",None),
("laspend",    "Local authority core spending power",   "Public Spending","£ per person 2022 prices","cash","MHCLG","region","financial",2010,"dip",None),
("counciltax", "Band D council tax",                    "Public Spending","£ per year","cash","MHCLG","region","financial",1997,"rise",None),
("ucclaim",    "Universal Credit claimants",            "Public Spending","Thousands","count","DWP","region","calendar",2015,"rise",None),
("pension",    "State Pension caseload",                "Public Spending","Thousands","count","DWP","region","financial",2000,"rise",None),
]

END = 2025

SHAPES = {
    "rise":       lambda t: 40 + 60 * t,
    "fall":       lambda t: 100 - 55 * t,
    "flat":       lambda t: 70 + 6 * math.sin(t * 5),
    "hump":       lambda t: 45 + 70 * math.sin(math.pi * t),
    "dip":        lambda t: 95 - 60 * math.sin(math.pi * t),
    "vol":        lambda t: 60 + 25 * math.sin(t * 9) + 12 * math.sin(t * 21),
    "crisis2008": lambda t: 35 + 75 * t - 22 * math.exp(-((t - 0.55) ** 2) / 0.004),
    "break2020":  lambda t: 60 + 35 * t - 45 * math.exp(-((t - 0.86) ** 2) / 0.0015),
}

# plausible magnitude by unit so the axis labels aren't nonsense
def scale_for(unit, kind):
    u = unit.lower()
    if "index" in u:                      return (60, 150)
    if u.startswith("%") or kind == "pct": return (2, 45)
    if "ratio" in u:                      return (2, 12)
    if "years" in u:                      return (58, 84)
    if "per 1,000" in u or "per 100" in u or "per million" in u: return (5, 90)
    if u == "£":                          return (60000, 340000)
    if "£ per week" in u:                 return (320, 700)
    if "£ per month" in u:                return (450, 1600)
    if "£ per pupil" in u:                return (5200, 7600)
    if "£ per person" in u:               return (900, 1900)
    if "£ per year" in u:                 return (700, 2200)
    if "£bn" in u:                        return (30, 1100)
    if "pence" in u:                      return (8, 180)
    if "thousand" in u:                   return (400, 6500)
    if "million" in u:                    return (20, 1900)
    if "count" in u or kind == "count":   return (2000, 250000)
    if "minutes" in u:                    return (18, 48)
    if "points" in u:                     return (2, 55)
    if "hours" in u:                      return (1000, 90000)
    return (20, 200)

def build(sid, unit, kind, shape, start, disc, area, seed):
    rng = random.Random(seed)
    lo, hi = scale_for(unit, kind)
    fn = SHAPES[shape]
    n = END - start + 1
    tilt = AREA_TILT.get(area, 1.0)
    # each area gets its own gentle divergence as well as a level offset
    drift = (rng.random() - 0.5) * 0.35
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        base = fn(t)
        base *= (1 + drift * t)
        v = lo + (hi - lo) * (base / 130.0)
        v *= tilt if kind != "pct" else (1 + (tilt - 1) * 0.4)
        v *= 1 + rng.gauss(0, 0.016)
        if disc:
            for dy, _ in disc:
                if start + i >= dy:
                    v *= 1.045
        out.append(v)
    # sensible rounding by magnitude
    mx = max(out)
    dp = 0 if mx > 1000 else (1 if mx > 20 else 2)
    return [round(v, dp) for v in out]

series = []
for (sid, name, topic, unit, kind, source, geo, basis, start, shape, disc) in S:
    codes = LEVELS[geo] if geo != "region" else LEVELS["nation"] + LEVELS["region"]
    if geo == "nation":
        codes = LEVELS["nation"]
    data = {}
    for j, code in enumerate(codes):
        data[code] = build(sid, unit, kind, shape, start, disc, code, hash((sid, code)) & 0xffff)
    series.append({
        "id": sid, "name": name, "topic": topic, "unit": unit, "kind": kind,
        "source": source, "geo": geo, "basis": basis, "start": start,
        "disc": [{"y": y, "note": n} for y, n in (disc or [])],
        "d": data,
    })

bundle = {
    "generated": "placeholder",
    "end": END,
    "areas": [{"code": c, "name": n, "short": s, "lvl": l, "col": col, "row": row, "parent": p}
              for (c, n, s, l, col, row, p) in AREAS],
    "series": series,
}

with open("catalogue.json", "w") as f:
    json.dump(bundle, f, separators=(",", ":"))

import os
print(f"{len(series)} series, {os.path.getsize('catalogue.json')/1024:.0f} KB")
print("topics:", sorted({s['topic'] for s in series}))
