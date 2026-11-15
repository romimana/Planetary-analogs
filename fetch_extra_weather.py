"""Fetch ERA5 scenario winds and upper-layer soil moisture for existing grid hours."""
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from itertools import islice
from urllib.parse import urlencode
from urllib.error import HTTPError

from build_earth import CACHE, OUT, digest, fetch
from fetch_final_weather import API
from package_ml import ROOT

FIELDS = ("wind_speed_10m", "wind_direction_10m", "soil_moisture_0_to_7cm")
UNITS = ("m/s", "°", "m³/m³")

def fetch_batch(job):
    date, points = job
    query = urlencode({
        "latitude": ",".join(str(lat) for lat, _ in points),
        "longitude": ",".join(str(lon) for _, lon in points),
        "elevation": ",".join(["nan"] * len(points)),
        "start_date": date, "end_date": date, "hourly": ",".join(FIELDS), "models": "era5",
        "timezone": "GMT", "cell_selection": "nearest", "wind_speed_unit": "ms",
    })
    url = f"{API}?{query}"
    try:
        raw = fetch("env-era5-" + digest(url.encode()) + ".json", url)
    except HTTPError as exc:
        if exc.code != 429:
            raise
        print(f"Rate limited for {date}, {len(points)} grid cells", flush=True)
        return []
    values = json.loads(raw)
    if isinstance(values, dict):
        values = [values]
    results = []
    for (lat, lon), value in zip(points, values, strict=True):
        if max(abs(lat - value["latitude"]), abs(lon - value["longitude"])) > .001 or value["utc_offset_seconds"]:
            raise ValueError(f"Invalid ERA5 grid or time metadata for {lat},{lon}")
        if tuple(value["hourly_units"][key] for key in FIELDS) != UNITS:
            raise ValueError(f"Unexpected ERA5 units: {value['hourly_units']!r}")
        hourly = value["hourly"]
        for stamp, speed, direction, wet in zip(hourly["time"], *(hourly[key] for key in FIELDS), strict=True):
            if not stamp.startswith(date):
                raise ValueError(f"Unexpected date: {stamp}")
            speed = speed if speed is not None and math.isfinite(speed) and 0 <= speed <= 120 else None
            direction = direction if direction is not None and 0 <= direction <= 360 and speed else None
            wet = wet if wet is not None and 0 <= wet <= 1 else None
            if speed is not None or wet is not None:
                results.append((lat, lon, stamp + "Z", speed, direction, wet, url, digest(raw)))
    return results

def main():
    paths = (ROOT / "data/ml-geology.sqlite", OUT / "ml-geology-local.sqlite")
    grid = {}
    for path in paths:
        if path.exists():
            with closing(sqlite3.connect(path)) as db:
                for day, lat, lon in db.execute("SELECT DISTINCT substr(utc,1,10),latitude,longitude FROM earth_era5"):
                    grid.setdefault(day, set()).add((round(lat * 4) / 4, round(lon * 4) / 4))
    jobs = []
    for date, coordinates in sorted(grid.items()):
        ordered = iter(sorted(coordinates))
        while batch := list(islice(ordered, 24)):
            jobs.append((date, batch))
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [item for batch in pool.map(fetch_batch, jobs) for item in batch]
    (OUT / "era5-extra.json").write_text(json.dumps(rows, ensure_ascii=True), encoding="utf-8")
    print(f"Validated {len(rows)} ERA5 grid hours", flush=True)

if __name__ == "__main__":
    main()
