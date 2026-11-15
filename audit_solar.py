"""Spot-check published solar geometry against JPL Horizons."""
import csv
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
API = "https://ssd.jpl.nasa.gov/api/horizons.api"
MAX_DIFFERENCE_DEG = 0.5

def horizons(body, lat, lon, timestamps):
    center = {"earth": 399, "mars": 499, "moon": 301}[body]
    if body == "mars":
        lat = math.degrees(math.atan2(math.sin(math.radians(lat)) * 3396.19**2,
                                     math.cos(math.radians(lat)) * 3376.2**2))
        # Horizons uses west-positive longitude for Mars.
        lon = -(lon % 360)
    times = " ".join("'" + utc.replace("T", " ").removesuffix("Z") + "'" for utc in timestamps)
    values = {
        "COMMAND": "'10'", "EPHEM_TYPE": "'OBSERVER'", "CENTER": f"'coord@{center}'",
        "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{lon},{lat},0'", "TLIST": times,
        "QUANTITIES": "'4'", "CSV_FORMAT": "'YES'", "ELEV_CUT": "'-90'", "APPARENT": "'AIRLESS'",
    }
    url = f"{API}?{urlencode({'format': 'json', **values})}"
    with urlopen(url, timeout=30) as response:
        result = json.load(response)["result"]
    if "$$SOE" not in result:
        raise ValueError(f"Horizons failed for {body}: {result[-400:]}")
    table = result.split("$$SOE")[1].split("$$EOE")[0].strip()
    rows = list(csv.reader(table.splitlines()))
    if len(rows) != len(timestamps):
        raise ValueError(f"Unexpected Horizons count for {body}")
    return [90 - float(row[4]) for row in rows], url

def audit(path):
    report = []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("SQLite integrity check failed")
        solar = db.execute("SELECT solar_zenith_deg,horizontal_projection FROM solar_scenarios").fetchall()
        if not all(0 <= z <= 180 and abs(r - max(0, math.cos(math.radians(z)))) < 1e-12 for z,r in solar):
            raise ValueError("Invalid solar geometry or projection")
        for body in ("earth", "mars", "moon"):
            key, loncol = ("site_id", "longitude") if body == "earth" else ("id", "longitude_e")
            points = db.execute(f"""SELECT DISTINCT {key},latitude,{loncol}
                               FROM {body}_model_profiles ORDER BY latitude, {key}""").fetchall()
            index = len(points) - 1
            for sid, lat, lon in (points[0], points[index // 2], points[index]):
                records = db.execute("""SELECT utc, solar_zenith_deg FROM solar_scenarios
                    WHERE body=? AND location_id=? ORDER BY utc""", (body, sid)).fetchall()
                selected = [records[i] for i in (0, len(records)//2, len(records)-1)]
                stamps, angles = zip(*selected)
                reference, query = horizons(body, lat, lon, stamps)
                for utc, actual, expected in zip(stamps, angles, reference, strict=True):
                    error = abs(actual - expected)
                    report.append({"body": body, "location": sid, "utc": utc, "sqlite_deg": actual,
                                   "horizons_deg": expected, "abs_delta_deg": error, "query": query})
                if max(abs(x-y) for x,y in zip(angles, reference)) > MAX_DIFFERENCE_DEG:
                    raise ValueError(f"Solar spot-check failed for {body}, {sid}: {reference} vs {angles}")
    return {"projection_rows_checked": len(solar), "tolerance_deg": MAX_DIFFERENCE_DEG, "checks": report}

if __name__ == "__main__":
    data = ROOT / "data"
    result = audit(data / "ml-enriched.sqlite")
    (data / "solar-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for body in ("earth", "mars", "moon"):
        errors = [r["abs_delta_deg"] for r in result["checks"] if r["body"] == body]
        print(body, len(errors), round(max(errors), 5))
