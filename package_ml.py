"""Package audited comparison snapshots for local use and redistribution."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from build_comparison import TERRAIN
from build_pilot import FIELDS

ROOT = Path(__file__).resolve().parent
CHEMISTRY = tuple(f"{field.lower()}_wt_pct" for field in FIELDS)

def check(db):
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    if db.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Dangling provenance or site link")

def copy_snapshot(source, target):
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        check(original)
        with closing(sqlite3.connect(target)) as copy:
            original.backup(copy)

def earth_views(db):
    metrics = ", ".join(f"t.{name}" for name in TERRAIN)
    db.executescript(f"""
        CREATE VIEW IF NOT EXISTS chemistry_inputs AS
        SELECT s.*, g.latitude, g.longitude, g.footprint_wkt, g.crs,
               x.url AS chemistry_source_url, x.sha256 AS chemistry_sha256
        FROM samples s JOIN sites g ON g.id=s.site_id JOIN sources x ON x.id=s.source_id;
        CREATE VIEW IF NOT EXISTS terrain_inputs AS
        SELECT c.*, {metrics}, t.source_url AS terrain_source_url, t.sha256 AS terrain_sha256,
               t.locator AS terrain_locator, t.min_bin_count, t.max_bin_count
        FROM chemistry_inputs c JOIN terrain t USING(site_id);
        CREATE VIEW IF NOT EXISTS surface_temperature_inputs AS
        SELECT c.*, m.granule_id, m.date, m.pass, m.row, m.col, m.temperature_k,
               m.local_observation_hour, m.quality_code, m.sha256 AS modis_sha256
        FROM chemistry_inputs c JOIN modis_temperature m USING(site_id);
        CREATE VIEW IF NOT EXISTS surface_terrain_inputs AS
        SELECT m.*, {metrics}, t.source_url AS terrain_source_url, t.sha256 AS terrain_sha256,
               t.locator AS terrain_locator, t.min_bin_count, t.max_bin_count
        FROM surface_temperature_inputs m JOIN terrain t USING(site_id);
    """)

def restrict_earth(db):
    with db:
        db.execute("DELETE FROM samples WHERE source_id != 'NGSA'")
        for table in ("terrain", "site_weather", "radar", "modis_temperature"):
            db.execute(f"DELETE FROM {table} WHERE site_id NOT IN (SELECT site_id FROM samples)")
        db.execute("DELETE FROM sites WHERE id NOT IN (SELECT site_id FROM samples)")
        db.execute("DELETE FROM weather WHERE id NOT IN (SELECT weather_id FROM site_weather)")
        db.execute("DELETE FROM sources WHERE id NOT IN (SELECT source_id FROM samples)")
    db.execute("VACUUM")

def summarize(db, groups):
    results = {}
    for table, site, population in groups:
        columns = ("*", site, population) if population else ("*", site)
        checks = ", ".join("count(*)" if c == "*" else f"count(DISTINCT {c})" for c in columns)
        breakdown = (
            db.execute(f"SELECT {population}, {checks} FROM {table} GROUP BY {population}").fetchall()
            if population else []
        )
        rows, unique_sites, *_ = db.execute(f"SELECT {checks} FROM {table}").fetchone()
        results[table] = {"rows": rows, "distinct_locations": unique_sites}
        if breakdown:
            results[table]["by_body"] = {body: [count, sites] for body, count, sites, _ in breakdown}
    return results

def validate_features(db, table, fields):
    for field in fields:
        invalid = f"{field} IS NULL OR {field} <= 0 OR {field} > 100"
        if db.execute(f"SELECT 1 FROM {table} WHERE {invalid} LIMIT 1").fetchone():
            raise ValueError(f"{table}.{field} has an invalid concentration")

def main():
    out = ROOT / "outputs"
    release = ROOT / "data"
    release.mkdir(exist_ok=True)
    local = out / "earth-ml-local.sqlite"
    earth = release / "earth.sqlite"
    planets = release / "planetary.sqlite"
    copy_snapshot(out / "earth-comparison.sqlite", local)
    with closing(sqlite3.connect(local)) as db:
        earth_views(db)
        check(db)
        validate_features(db, "chemistry_inputs", CHEMISTRY)
        local_coverage = summarize(db, earth_groups)
    copy_snapshot(local, earth)
    with closing(sqlite3.connect(earth)) as db:
        restrict_earth(db)
        check(db)
        public_coverage = summarize(db, earth_groups)
    copy_snapshot(out / "planetary-comparison.sqlite", planets)
    with closing(sqlite3.connect(planets)) as db:
        check(db)
        validate_features(db, "chemistry_inputs", CHEMISTRY)
        planetary_coverage = summarize(db, planetary_groups)
    manifest = {
        "earth": public_coverage,
        "planetary": planetary_coverage,
        "earth_local": local_coverage,
        "sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (earth, planets)
        },
    }
    (release / "coverage.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))

earth_groups = [(name, key, None) for name, key in (
    ("chemistry_inputs", "site_id"), ("terrain_inputs", "site_id"),
    ("modis_temperature", "site_id"), ("surface_temperature_inputs", "site_id"),
    ("surface_terrain_inputs", "site_id"), ("joined_inputs", "site_id"), ("radar", "site_id"),
)]
planetary_groups = [(name, "area || ':' || latitude || ':' || longitude_e", "body") for name in (
    "samples", "chemistry_inputs", "mars_atmosphere_inputs", "mars_surface_inputs", "moon_thermal_inputs",
)]

if __name__ == "__main__":
    main()
