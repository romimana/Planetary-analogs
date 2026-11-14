"""Assemble partial and complete observations in one SQLite database."""
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from build_earth import CACHE, OUT, digest, envelope, fetch, terrain_batch
from build_final_ml import MAX_GRID_DISTANCE_M, RADIUS, distance, weather_index
from build_pilot import FIELDS
from fetch_final_weather import cell, fetch_cells
from package_ml import TERRAIN, check

ROOT = Path(__file__).resolve().parent
GSJ = "https://gbank.gsj.jp/geochemmap/data/"
INPUTS = {
    "gsj-sites.csv": ("joho/samplejoho.csv", "9fdb58d86ad48eae564291421a0dad2b6f8a4f243d3e89d90016f3c61b0b521c"),
    "gsj-noudo.csv": ("ganyuryo/noudo.csv", "0dbd2beae356adc45b762d50a9aa06ad556fd3ea004d427e369837bedda05671"),
}
METHOD = "https://doi.org/10.2343/geochemj.2.0618"

def gsj_rows(name):
    suffix, sha = INPUTS[name]
    raw = fetch(name, GSJ + suffix)
    if digest(raw) != sha:
        raise ValueError(f"GSJ source changed: {name}")
    return csv.reader(raw.decode("cp932").splitlines())

def japan():
    locations = defaultdict(list)
    reader = gsj_rows("gsj-sites.csv")
    headings = next(reader)
    assert headings[2:4] == ["経度(JGD2000)", "緯度(JGD2000)"]
    for line, row in enumerate(reader, 2):
        if row and row[0].strip():
            locations[int(row[0])].append((line, float(row[3]), float(row[2])))
    reader = gsj_rows("gsj-noudo.csv")
    headings = next(reader)
    fields = [headings.index(k) if k != "SiO2" else None for k in FIELDS]
    values = [(line, row) for line, row in enumerate(reader, 2) if row and row[0].strip()]
    counts = Counter(int(row[0]) for _, row in values)
    rejected = []
    records = []
    for line, row in values:
        number = int(row[0])
        if counts[number] != 1 or len(locations[number]) != 1:
            rejected.append(number)
            continue
        location_line, lat, lon = locations[number][0]
        if not (20 < lat < 47 and 122 < lon < 149):
            raise ValueError(f"Unexpected Japanese coordinate for {number}")
        chemistry = [float(row[i]) if i is not None else None for i in fields]
        if not all(v is None or 0 < v <= 100 for v in chemistry):
            raise ValueError(f"Invalid Japanese concentration at chemistry line {line}")
        sample_id = f"GSJ:{number}"
        site_id = f"JP:{lat:.6f}/{lon:.6f}"
        west, south, east, north = envelope(lat, lon)
        wkt = f"POLYGON (({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
        records.append((sample_id, site_id, "GSJ", "JPN", "stream sediment; magnetic fraction removed",
                        None, *chemistry, f"noudo.csv line {line}; samplejoho.csv line {location_line}",
                        json.dumps({"source_crs": "JGD2000", "method_url": METHOD,
                                    "latitude": lat, "longitude": lon, "sieve_um": 180}),
                        lat, lon, wkt, "EPSG:4612", GSJ + INPUTS["gsj-noudo.csv"][0],
                        INPUTS["gsj-noudo.csv"][1]))
    return records, sorted(set(rejected))

def collect_japan_terrain(records, budget):
    buckets = defaultdict(dict)
    for row in records:
        site, lat, lon = row[1], row[-6], row[-5]
        key = math.floor(lat), math.floor(lon)
        w, s, e, n = envelope(lat, lon)
        if key[0] <= s <= n <= key[0] + 1 and key[1] <= w <= e <= key[1] + 1:
            buckets[key][site] = (site, lat, lon)
    keys = sorted(buckets, key=lambda k: (-len(buckets[k]), k))[:budget]
    with ThreadPoolExecutor(max_workers=5) as pool:
        return [row for batch in pool.map(lambda k: terrain_batch(k, buckets[k].values()), keys) for row in batch]

def copy(db, source, target, names):
    db.execute(f"ATTACH DATABASE ? AS {source}", (target.as_uri() + "?mode=ro",))
    for name, destination in names.items():
        db.execute(f"CREATE TABLE {destination} AS SELECT * FROM {source}.{name}")

def add_era5(db, hourly):
    db.executescript("""
        CREATE TABLE earth_era5 (
            id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL, utc TEXT NOT NULL,
            air_temperature_k REAL NOT NULL, pressure_pa REAL NOT NULL,
            source_url TEXT NOT NULL, sha256 TEXT NOT NULL
        );
        CREATE TABLE earth_site_era5 (
            site_id TEXT NOT NULL, weather_id TEXT NOT NULL REFERENCES earth_era5,
            distance_m REAL NOT NULL, PRIMARY KEY(site_id, weather_id)
        );
    """)
    by_cell = defaultdict(list)
    for (lat, lon, stamp), values in hourly.items():
        by_cell[lat, lon].append((stamp, values))
    for site, lat, lon in db.execute("""
        SELECT DISTINCT s.site_id,s.latitude,s.longitude FROM earth_samples s
        JOIN earth_terrain t USING(site_id)
    """):
        for stamp, (grid_lat, grid_lon, air, pressure, url, sha) in by_cell[cell(lat, lon)]:
            separation = distance((lat, lon), (grid_lat, grid_lon), RADIUS)
            if separation > MAX_GRID_DISTANCE_M:
                continue
            key = f"{grid_lat}/{grid_lon}/{stamp}"
            db.execute("INSERT OR IGNORE INTO earth_era5 VALUES (?,?,?,?,?,?,?,?)",
                       (key, grid_lat, grid_lon, stamp + "Z", air, pressure, url, sha))
            db.execute("INSERT INTO earth_site_era5 VALUES (?,?,?)", (site, key, separation))

def build(earth, target, records, terrain, hourly):
    stage = target.with_suffix(".build.sqlite")
    stage.unlink(missing_ok=True)
    with closing(sqlite3.connect(stage, uri=True)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        copy(db, "terrestrial", earth, {
            "chemistry_inputs": "earth_samples", "terrain": "earth_terrain",
            "modis_temperature": "earth_modis", "weather": "earth_power",
            "site_weather": "earth_site_power", "radar": "earth_radar",
        })
        copy(db, "planetary", ROOT / "data/planetary.sqlite", {
            "samples": "planet_samples", "scenarios": "planet_scenarios",
            "sample_scenarios": "planet_sample_scenarios",
        })
        copy(db, "strict", ROOT / "data/ml-final.sqlite" if earth.parent.name == "data"
             else OUT / "ml-final-local.sqlite", {body: f"complete_{body}" for body in ("earth", "mars", "moon")})
        db.executemany(f"INSERT INTO earth_samples VALUES ({','.join('?' for _ in records[0])})", records)
        db.executemany("INSERT INTO earth_terrain VALUES (?,?,?,?,?,?,?,?,?,?,?)", terrain)
        db.execute("CREATE TABLE additional_sources (id TEXT PRIMARY KEY, url TEXT NOT NULL, sha256 TEXT NOT NULL)")
        db.executemany("INSERT INTO additional_sources VALUES (?,?,?)",
                       ((name, GSJ + suffix, sha) for name, (suffix, sha) in INPUTS.items()))
        keys = {
            "earth_samples": "id", "earth_terrain": "site_id",
            "earth_modis": "site_id,granule_id,pass", "earth_power": "id",
            "earth_site_power": "site_id,weather_id", "earth_radar": "site_id,scene",
            "planet_samples": "id", "planet_scenarios": "id",
            "planet_sample_scenarios": "sample_id,scenario_id",
        }
        for name, fields in keys.items():
            db.execute(f"CREATE UNIQUE INDEX key_{name} ON {name} ({fields})")
        db.execute("CREATE INDEX earth_samples_site ON earth_samples(site_id)")
        add_era5(db, hourly)
        db.execute(f"""
            CREATE VIEW earth_profiles AS
            SELECT s.*, {", ".join(f"t.{k}" for k in TERRAIN)},
                   t.source_url AS terrain_source_url, t.sha256 AS terrain_sha256,
                   t.locator AS terrain_locator
            FROM earth_samples s LEFT JOIN earth_terrain t USING(site_id)
        """)
        db.execute("""
            CREATE VIEW planetary_profiles AS
            SELECT p.*, l.scenario_id, l.distance_m, l.chemistry_sol_delta, w.window_label,
                   w.local_solar_hour, w.source_url AS environment_source_url, w.air_temperature_k,
                   w.pressure_pa, w.ground_brightness_k, w.lunar_surface_bolometric_k,
                   w.provenance_json AS environment_provenance_json
            FROM planet_samples p LEFT JOIN planet_sample_scenarios l ON l.sample_id=p.id
            LEFT JOIN planet_scenarios w ON w.id=l.scenario_id
        """)
        for child, key, parent, parent_key in (
            ("earth_modis","site_id","earth_samples","site_id"),
            ("earth_terrain","site_id","earth_samples","site_id"),
            ("earth_site_power","site_id","earth_samples","site_id"),
            ("earth_site_power","weather_id","earth_power","id"),
            ("earth_radar","site_id","earth_samples","site_id"),
            ("earth_site_era5","site_id","earth_samples","site_id"),
            ("planet_sample_scenarios","sample_id","planet_samples","id"),
            ("planet_sample_scenarios","scenario_id","planet_scenarios","id"),
        ):
            if db.execute(f"SELECT 1 FROM {child} c WHERE NOT EXISTS (SELECT 1 FROM {parent} p "
                          f"WHERE p.{parent_key}=c.{key}) LIMIT 1").fetchone():
                raise ValueError(f"Orphan row in {child}")
        check(db)
        coverage = {
            "earth_by_source": [list(row) for row in db.execute(f"""
                SELECT source_id,count(*),count(DISTINCT site_id),
                       count(DISTINCT CASE WHEN {TERRAIN[0]} IS NOT NULL THEN site_id END)
                FROM earth_profiles GROUP BY source_id
            """)],
            "planetary_by_body_status": [list(row) for row in db.execute("""
                SELECT body,comparison_status,count(*) FROM planet_samples GROUP BY 1,2
            """)],
            "era5_sites": db.execute("SELECT count(DISTINCT site_id) FROM earth_site_era5").fetchone()[0],
        }
        db.commit()
    stage.replace(target)
    coverage["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return coverage

def main():
    records, rejected = japan()
    terrain = collect_japan_terrain(records, budget=8)
    terrain_sites = {row[0] for row in terrain}
    coords = sorted({cell(row[-6], row[-5]) for row in records if row[1] in terrain_sites})
    if coords:
        fetch_cells(coords)
    hourly = weather_index()
    release = ROOT / "data"
    coverage = {
        "gsj_ambiguous_ids": rejected,
        "github": build(release / "earth.sqlite", release / "ml-full.sqlite", records, terrain, hourly),
        "local": build(OUT / "earth-ml-local.sqlite", OUT / "ml-full-local.sqlite", records, terrain, hourly),
    }
    (release / "ml-full-coverage.json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(coverage, indent=2))

if __name__ == "__main__":
    main()
