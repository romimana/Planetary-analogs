"""Fetch and retain ERA5 grid-hour values for terrain sites."""
import json
import math
import sqlite3
from datetime import date
from urllib.parse import urlencode

from build_earth import CACHE, DAYS, OUT, digest, fetch

API = "https://archive-api.open-meteo.com/v1/archive"
SITE_QUERY = "SELECT s.id,s.latitude,s.longitude FROM sites s JOIN terrain t ON t.site_id=s.id"

def cell(lat, lon):
    return round(lat * 4) / 4, round(lon * 4) / 4

def batches(points, size):
    for i in range(0, len(points), size):
        yield points[i:i + size]

def main():
    with sqlite3.connect(OUT / "earth-ml-local.sqlite") as db:
        coords = sorted({cell(lat, lon) for _, lat, lon in db.execute(SITE_QUERY)})
    for day in DAYS:
        date_iso = date(int(day[:4]), int(day[4:6]), int(day[6:])).isoformat()
        for batch in batches(coords, 12):
            query = urlencode({
                "latitude": ",".join(str(lat) for lat, _ in batch),
                "longitude": ",".join(str(lon) for _, lon in batch),
                "start_date": date_iso, "end_date": date_iso,
                "hourly": "temperature_2m,surface_pressure", "models": "era5",
                "elevation": ",".join(["nan"] * len(batch)),
                "cell_selection": "nearest", "timezone": "GMT",
            })
            url = f"{API}?{query}"
            tag = digest(url.encode())
            try:
                raw = fetch(f"era5-final-{tag}.json", url)
            except OSError as exc:
                print(f"ERA5 request failed for {date_iso}: {exc}", flush=True)
                continue
            responses = json.loads(raw)
            if isinstance(responses, dict):
                responses = [responses]
            if len(responses) != len(batch):
                raise ValueError(f"Expected {len(batch)} responses for {date_iso}")
            records = []
            for (lat, lon), response in zip(batch, responses, strict=True):
                grid = (response["latitude"], response["longitude"])
                if max(abs(lat - grid[0]), abs(lon - grid[1])) > .001:
                    continue
                units = response["hourly_units"]
                if response["utc_offset_seconds"] or units["temperature_2m"] != "\u00b0C" or units["surface_pressure"] != "hPa":
                    raise ValueError("Unexpected time or weather units")
                hourly = response["hourly"]
                for stamp, temperature, pressure in zip(
                    hourly["time"], hourly["temperature_2m"], hourly["surface_pressure"], strict=True
                ):
                    if not stamp.startswith(date_iso) or temperature is None or pressure is None:
                        continue
                    if not (math.isfinite(temperature) and math.isfinite(pressure) and pressure > 0):
                        continue
                    records.append((lat, lon, *grid, stamp, temperature + 273.15, pressure * 100, url, digest(raw)))
            (CACHE / f"validated-era5-final-{tag}.json").write_text(json.dumps(records), encoding="utf-8")
        print(f"Processed {date_iso}", flush=True)

if __name__ == "__main__":
    main()
