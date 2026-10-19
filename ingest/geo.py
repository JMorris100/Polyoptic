"""Build the boundary files the explorer's map view draws.

Fetches ONS Open Geography Portal "ultra generalised" boundaries (BUC) in
British National Grid metres, and writes one small JSON per boundary set to
data/geo/: {"w","h","areas":{code: svg path}}. Coordinates are rounded to a
250 m grid and written as relative moves, so a whole UK set is a few hundred
KB. Shetland is moved into an inset box east of Orkney, as on most UK maps.

    python ingest/geo.py

Source: Office for National Statistics licensed under the Open Government
Licence v3.0. Contains OS data © Crown copyright and database right.
"""
import json, os, urllib.request, urllib.parse

BASE = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/{}/FeatureServer/{}/query"
SETS = {
    "lad":   ("LAD_MAY_2025_UK_BUC",   "LAD25CD"),
    "cty":   ("CTY_DEC_2023_UK_BUC_V2", "CTY23CD"),
    "itl1":  ("ITL1_JAN_2025_UK_BUC",  "ITL125CD"),
    "itl2":  ("ITL2_JAN_2025_UK_BUC",  "ITL225CD"),
    "itl3":  ("ITL3_JAN_2025_UK_BUC_V2", "ITL325CD", 2),
    "cauth": ("CAUTH_MAY_2025_EN_BUC", "CAUTH25CD"),
}
GRID = 250                      # metres per unit
X0, Y1 = -10000, 1060000        # west edge, north edge of the drawing
W, H = 2720, 4280               # drawing size in units (680 km x 1070 km)
SHETLAND_Y = 1100000            # rings north of this go into the inset
SHETLAND_SHIFT = (150000, -165000)
# the area data still files these two under their pre-2021 codes
ALIASES = {"E08000038": "E08000016", "E08000039": "E08000019"}
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "geo")


def fetch(service, field, layer=0):
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": field, "outSR": 27700, "f": "geojson",
            "geometryPrecision": 0, "resultOffset": offset, "resultRecordCount": 1000})
        with urllib.request.urlopen(BASE.format(service, layer) + "?" + q, timeout=120) as r:
            d = json.load(r)
        feats += d["features"]
        if not d.get("properties", {}).get("exceededTransferLimit") and len(d["features"]) < 1000:
            return feats
        offset += 1000


def ring_path(ring):
    ys = [p[1] for p in ring]
    dx, dy = SHETLAND_SHIFT if min(ys) > SHETLAND_Y else (0, 0)
    pts = []
    for x, y in ring:
        p = (round((x + dx - X0) / GRID), round((Y1 - (y + dy)) / GRID))
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) < 4:
        return ""
    out = [f"M{pts[0][0]} {pts[0][1]}"]
    rel = []
    for a, b in zip(pts, pts[1:]):
        rel.append(f"{b[0]-a[0]} {b[1]-a[1]}")
    out.append("l" + " ".join(rel).replace(" -", "-") + "z")
    return "".join(out)


def build(name, service, field, layer=0):
    areas = {}
    for f in fetch(service, field, layer):
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = "".join(ring_path(r) for poly in polys for r in poly)
        if d:
            code = f["properties"][field]
            areas[code] = d
            if code in ALIASES:
                areas[ALIASES[code]] = d
    path = os.path.join(OUT, name + ".json")
    with open(path, "w") as fh:
        json.dump({"w": W, "h": H, "source": service,
                   "inset": {"shetland": SHETLAND_SHIFT}, "areas": areas}, fh, separators=(",", ":"))
    print(f"{name}: {len(areas)} areas, {os.path.getsize(path)//1024} KB")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, spec in SETS.items():
        build(name, *spec)
