"""Publish complete, provenance-bearing sample/scenario rows for all three bodies."""
import json
import math
import sqlite3
import hashlib
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from build_earth import CACHE, OUT, RADIUS, distance
from fetch_final_weather import cell
from package_ml import CHEMISTRY, TERRAIN, check

ROOT = Path(__file__).resolve().parent
MAX_GRID_DISTANCE_M = 10000
MAX_TIME_OFFSET_MIN = 30

def weather_index():
    hourly = {}
    for path in sorted(CACHE.glob("validated-era5-final-*.json")):
        for lat, lon, grid_lat, grid_lon, stamp, air, pressure, url, sha in json.loads(path.read_text()):
            key = (lat, lon, stamp)
            value = (grid_lat, grid_lon, air, pressure, url, sha)
            if key in hourly and hourly[key][:4] != value[:4]:
                raise ValueError(f"Conflicting weather values at {key}")
            hourly[key] = value
    if not hourly:
        raise ValueError("No validated ERA5 grid-hour values")
    return hourly

def earth_rows(db, weather):
    seen = set()
    for row in db.execute("SELECT * FROM surface_terrain_inputs ORDER BY id,date,pass,granule_id"):
        item = dict(row)
        key = (item["id"], item["date"], item["pass"])
        if key in seen:
            raise ValueError(f"Multiple granules for {key}")
        seen.add(key)
        lat, lon = item["latitude"], item["longitude"]
        # The granule identifies the UTC date. The pixel time is modulo 24 local solar hours.
        midnight = datetime.fromisoformat(item["date"])
        stamp = midnight + timedelta(hours=(item["local_observation_hour"] - lon / 15) % 24)
        hour = (stamp + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        key = (*cell(lat, lon), hour.isoformat(timespec="minutes"))
        entry = weather.get(key)
        if entry is None:
            continue
        grid_lat, grid_lon, air, pressure, url, sha = entry
        distance_m = distance((lat, lon), (grid_lat, grid_lon), RADIUS)
        time_offset = abs((hour - stamp).total_seconds()) / 60
        if distance_m > MAX_GRID_DISTANCE_M or time_offset > MAX_TIME_OFFSET_MIN:
            continue
        item.update(
            modis_approximate_utc=stamp.isoformat(timespec="seconds") + "Z",
            weather_utc=hour.isoformat(timespec="minutes") + "Z",
            weather_offset_minutes=time_offset, weather_distance_m=distance_m,
            weather_grid_latitude=grid_lat, weather_grid_longitude=grid_lon,
            air_temperature_k=air, pressure_pa=pressure,
            weather_source_url=url, weather_sha256=sha,
            modis_source_url="https://cmr.earthdata.nasa.gov/search/granules.umm_json?" + urlencode(
                {"concept_id": item["granule_id"]}
            ),
        )
        yield item

def planet_rows(db, view):
    query = f"""
        SELECT v.*, w.provenance_json AS environment_provenance_json
        FROM {view} v JOIN scenarios w ON w.id=v.scenario_id
        ORDER BY v.id,v.scenario_id
    """
    return (dict(row) for row in db.execute(query))

def write_table(db, name, records, keys, environmental, count_location):
    rows = list(records)
    if not rows:
        raise ValueError(f"No complete records for {name}")
    columns = tuple(rows[0])
    definitions = []
    for column, value in rows[0].items():
        dtype = {str: "TEXT", float: "REAL", int: "INTEGER"}[type(value)]
        definitions.append(f'"{column}" {dtype} NOT NULL')
    pk = ", ".join(f'"{key}"' for key in keys)
    db.execute(f"CREATE TABLE {name} ({', '.join(definitions)}, PRIMARY KEY ({pk}))")
    for row in rows:
        if tuple(row) != columns:
            raise ValueError(f"Schema mismatch in {name}")
        if any(value is None or value == "" or (isinstance(value, float) and not math.isfinite(value))
               for value in row.values()):
            raise ValueError(f"Missing or invalid data in {name}: {row['id']}")
        if not all(0 < row[k] <= 100 for k in CHEMISTRY) or sum(row[k] for k in CHEMISTRY) > 100.5:
            raise ValueError(f"Invalid chemistry in {name}: {row['id']}")
        limits = (90, 90, 1, math.inf, math.inf)
        if not all(0 <= row[k] <= limit for k, limit in zip(TERRAIN, limits, strict=True)):
            raise ValueError(f"Invalid terrain in {name}: {row['id']}")
        if not all(row[k] > 0 for k in environmental):
            raise ValueError(f"Invalid environment in {name}: {row['id']}")
    db.executemany(f"INSERT INTO {name} VALUES ({','.join('?' for _ in columns)})",
                   (tuple(row.values()) for row in rows))
    return {
        "rows": len(rows), "samples": len({row["id"] for row in rows}),
        "locations": len({count_location(row) for row in rows}),
    }

def export(earth_path, planet_path, target, weather):
    temporary = target.with_suffix(".build.sqlite")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(earth_path.as_uri() + "?mode=ro", uri=True)) as earth, \
         closing(sqlite3.connect(planet_path.as_uri() + "?mode=ro", uri=True)) as planet, \
         closing(sqlite3.connect(temporary)) as db:
        earth.row_factory = planet.row_factory = sqlite3.Row
        location = lambda r: (r["latitude"], r["longitude_e"])
        counts = {
            "earth": write_table(db, "earth", earth_rows(earth, weather), ("id", "date", "pass"),
                                 ("temperature_k", "air_temperature_k", "pressure_pa"), lambda r: r["site_id"]),
            "mars": write_table(db, "mars", planet_rows(planet, "mars_surface_inputs"), ("id", "scenario_id"),
                                ("ground_brightness_k", "air_temperature_k", "pressure_pa"), location),
            "moon": write_table(db, "moon", planet_rows(planet, "moon_thermal_inputs"), ("id", "scenario_id"),
                                ("lunar_surface_bolometric_k",), location),
        }
        check(db)
        db.commit()
    temporary.replace(target)
    counts["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return counts

def main():
    weather = weather_index()
    release = ROOT / "data"
    planet = release / "planetary.sqlite"
    coverage = {
        "github": export(release / "earth.sqlite", planet, release / "ml-final.sqlite", weather),
        "local": export(OUT / "earth-ml-local.sqlite", planet, OUT / "ml-final-local.sqlite", weather),
    }
    (release / "ml-final-coverage.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(coverage, indent=2))

if __name__ == "__main__":
    main()
