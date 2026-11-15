"""Publish traceable solar, atmospheric and grain-size scenario tables."""
import csv
import hashlib
import io
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from zipfile import ZipFile

import numpy as np
import spiceypy as spice

from build_context import download
from build_earth import CACHE, DAYS, OUT, digest, fetch
from build_full_ml import GSJ, INPUTS, gsj_rows
from package_ml import ROOT, check, copy_snapshot

NAIF = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/"
KERNELS = {
    "naif0012.tls": "lsk/naif0012.tls",
    "pck00011.tpc": "pck/pck00011.tpc",
    "de440s.bsp": "spk/planets/de440s.bsp",
    "moon_pa_de440_200625.bpc": "pck/moon_pa_de440_200625.bpc",
    "moon_de440_250416.tf": "fk/satellites/moon_de440_250416.tf",
}
GRAIN = "https://ntrs.nasa.gov/api/citations/20250001791/downloads/LunarSoilsGrainSizeCatalogDigitization.zip"
MARS_TEXTURE = {
    ("PortageRP", 89): ("APXS target in the Rocknest sand shadow", "https://doi.org/10.1002/2013JE004519"),
    ("King_rp", 523): ("MAHLI soil texture target", "https://gsa.confex.com/gsa/2015AM/webprogram/Paper265086.html"),
    ("Johnny_Cake_rp", 558): ("MAHLI soil texture target", "https://gsa.confex.com/gsa/2015AM/webprogram/Paper265086.html"),
    ("Lagrange", 605): ("MAHLI soil texture target", "https://gsa.confex.com/gsa/2015AM/webprogram/Paper265086.html"),
}

def utc_dates(body):
    if body == "moon":
        start = datetime(2024, 1, 15, 12, tzinfo=timezone.utc)
        return [(start + timedelta(days=i * 4)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(8)]
    return [datetime.strptime(day, "%Y%m%d").replace(hour=h).strftime("%Y-%m-%dT%H:%M:%SZ")
            for day in DAYS for h in range(0, 24, 4)]

def stage_solar(db):
    db.executescript("""
        CREATE TABLE solar_sources (kernel TEXT PRIMARY KEY,url TEXT NOT NULL,sha256 TEXT NOT NULL);
        CREATE TABLE solar_scenarios (
            body TEXT NOT NULL,location_id TEXT NOT NULL,utc TEXT NOT NULL,solar_zenith_deg REAL NOT NULL
                CHECK(solar_zenith_deg BETWEEN 0 AND 180),
            horizontal_projection REAL NOT NULL CHECK(horizontal_projection BETWEEN 0 AND 1),
            PRIMARY KEY(body, location_id, utc)
        );
    """)
    for name, suffix in KERNELS.items():
        url = NAIF + suffix
        raw = fetch(name, url)
        db.execute("INSERT INTO solar_sources VALUES(?,?,?)", (name, url, digest(raw)))
        spice.furnsh(str(CACHE / name))
    frames = {"earth": ("IAU_EARTH", "EARTH", 6371.0088),
              "mars": ("IAU_MARS", "MARS BARYCENTER", 3396.19),
              "moon": ("MOON_ME_DE440_ME421", "MOON", 1737.4)}
    for body, (frame, origin, radius) in frames.items():
        if body == "earth":
            rows = db.execute("SELECT DISTINCT site_id,latitude,longitude FROM earth_samples ORDER BY 1").fetchall()
        else:
            rows = db.execute(f"SELECT id,latitude,longitude_e FROM {body}_model_profiles ORDER BY 1").fetchall()
        lat, lon = np.radians(np.array([(r[1], r[2]) for r in rows])).T
        normals = np.column_stack((np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)))
        observer = normals * radius
        if body == "earth":
            observer = np.array([spice.georec(lng, phi, 0, 6378.137, 1/298.257223563)
                                 for phi, lng in zip(lat, lon)])
        for utc in utc_dates(body):
            ray = spice.spkpos("SUN", spice.str2et(utc), frame, "NONE", origin)[0] - observer
            cosine = np.clip(np.sum(normals * ray, axis=1) / np.linalg.norm(ray, axis=1), -1, 1)
            zenith = np.degrees(np.arccos(cosine))
            db.executemany("INSERT INTO solar_scenarios VALUES (?,?,?,?,?)",
                           ((body, r[0], utc, float(angle), float(max(0, cos)))
                            for r, angle, cos in zip(rows, zenith, cosine, strict=True)))
    spice.kclear()

def stage_earth_weather(db, extra):
    db.execute("""CREATE TABLE earth_environment_extra (
        weather_id TEXT PRIMARY KEY,wind_speed_10m_m_s REAL,wind_direction_10m_deg REAL,
        soil_water_0_to_7cm_m3_m3 REAL,source_url TEXT NOT NULL,sha256 TEXT NOT NULL
    )""")
    matched = {}
    for weather_id, lat, lon, utc in db.execute("SELECT id,latitude,longitude,utc FROM earth_era5"):
        key = round(lat * 4) / 4, round(lon * 4) / 4, utc
        if key in extra:
            matched[weather_id] = extra[key]
    db.executemany("INSERT INTO earth_environment_extra VALUES(?,?,?,?,?,?)",
                   ((key, *vals) for key, vals in matched.items()))
    db.execute("""CREATE VIEW earth_environment AS
        SELECT l.site_id,w.*,l.distance_m,e.wind_speed_10m_m_s,e.wind_direction_10m_deg,
               e.soil_water_0_to_7cm_m3_m3,e.source_url AS extra_source_url,e.sha256 AS extra_sha256
        FROM earth_site_era5 l JOIN earth_era5 w ON w.id=l.weather_id
        LEFT JOIN earth_environment_extra e ON e.weather_id=w.id
    """)

def mars_wind(db):
    db.execute("""CREATE TABLE mars_wind_windows (
        scenario_id TEXT PRIMARY KEY,wind_speed_m_s REAL NOT NULL,wind_speed_p90_m_s REAL NOT NULL,
        n INTEGER NOT NULL,confidence_flag TEXT NOT NULL,status TEXT NOT NULL,
        source_url TEXT NOT NULL,sha256 TEXT NOT NULL
    )""")
    files = {}
    for sid, url in db.execute("""SELECT DISTINCT s.id,s.source_url FROM planet_scenarios s
        JOIN planet_sample_scenarios l ON l.scenario_id=s.id
        JOIN mars_model_profiles p ON p.id=l.sample_id
        WHERE p.comparison_status='rover_or_station'"""):
        _, _, sol, hour = json.loads(sid)
        if url not in files:
            raw = download(url, f"rems{sol}.tab")
            hourly = defaultdict(lambda: defaultdict(list))
            for row in csv.reader(io.StringIO(raw.decode("ascii"))):
                assert len(row) == 40 and int(row[1][:5]) == sol
                flag = row[6].strip()
                wind = float(row[3])
                if flag in ("111111", "111110") and 0 <= wind <= 100:
                    h = int(row[2].strip().split()[-1][:2])
                    hourly[h][flag].append(wind)
            files[url] = (hourly, digest(raw))
        hourly, sha = files[url]
        flags = hourly[hour]
        for flag, status in (("111111", "reliable"), ("111110", "preliminary")):
            speeds = flags[flag]
            if speeds:
                db.execute("INSERT INTO mars_wind_windows VALUES(?,?,?,?,?,?,?,?)",
                           (sid, median(speeds), float(np.percentile(speeds, 90)), len(speeds),
                            flag, status, url, sha))
                break
    db.execute("""CREATE VIEW mars_environment AS
        SELECT p.*,w.wind_speed_m_s,w.wind_speed_p90_m_s,w.n AS wind_n,
               w.status AS wind_status,w.confidence_flag AS wind_confidence_flag,
               w.source_url AS wind_source_url,w.sha256 AS wind_sha256
        FROM planetary_profiles p LEFT JOIN mars_wind_windows w USING(scenario_id)
        WHERE p.body='mars'
    """)

def grain(db):
    db.executescript("""
        CREATE TABLE earth_grain_notes (
            sample_id TEXT PRIMARY KEY,source_grain_description_ja TEXT NOT NULL,
            source_column TEXT NOT NULL,source_url TEXT NOT NULL,source_line INTEGER NOT NULL,sha256 TEXT NOT NULL
        );
        CREATE TABLE moon_grain_bins (
            sample_id TEXT NOT NULL,grain_aliquot TEXT NOT NULL,join_level TEXT NOT NULL,
            sieve_um REAL NOT NULL,weight_pct REAL NOT NULL,source_url TEXT NOT NULL,source_file TEXT NOT NULL,
            sha256 TEXT NOT NULL, PRIMARY KEY(sample_id,grain_aliquot,sieve_um)
        );
        CREATE TABLE mars_texture_context (
            sample_id TEXT PRIMARY KEY,target_name TEXT NOT NULL,sol INTEGER NOT NULL,
            texture_context TEXT NOT NULL,source_url TEXT NOT NULL
        );
    """)
    for sid, name, provenance in db.execute("SELECT id,name,provenance_json FROM planet_samples WHERE body='mars'"):
        sol = json.loads(provenance).get("sol")
        if (name, sol) in MARS_TEXTURE:
            db.execute("INSERT INTO mars_texture_context VALUES(?,?,?,?,?)",
                       (sid, name, sol, *MARS_TEXTURE[name, sol]))
    ids = {id for (id,) in db.execute("SELECT id FROM earth_samples WHERE source_id='GSJ'")}
    reader = gsj_rows("gsj-sites.csv")
    column = next(reader)[10]
    suffix, sha = INPUTS["gsj-sites.csv"]
    for line, row in enumerate(reader, 2):
        if row and row[0].strip().isdigit() and row[10].strip():
            sid = f"GSJ:{int(row[0])}"
            if sid in ids:
                db.execute("INSERT INTO earth_grain_notes VALUES (?,?,?,?,?,?)",
                           (sid, row[10].strip(), column, GSJ + suffix, line, sha))
    raw = fetch("lunar-grain.zip", GRAIN)
    with ZipFile(io.BytesIO(raw)) as archive:
        files = defaultdict(list)
        for member in archive.namelist():
            name = Path(member).stem
            if name.startswith("soil_") and name.endswith(tuple("0123456789")):
                segments = name.split("_")
                if len(segments) == 3 and all(v.isdigit() for v in segments[1:]):
                    files[segments[1]].append((segments[2], member))
        for sid, name in db.execute("SELECT id,name FROM planet_samples WHERE body='moon'"):
            parent, _, split = name.partition(",")
            for aliquot, member in files[parent]:
                content = archive.read(member)
                values = [tuple(map(float, line.split())) for line in content.decode("ascii").splitlines()[1:]
                          if line.strip()]
                if not values or not all(size > 0 and 0 <= wt <= 100 for size, wt in values):
                    continue
                db.executemany("INSERT INTO moon_grain_bins VALUES (?,?,?,?,?,?,?,?)",
                               ((sid, f"{parent},{aliquot}", "same_aliquot" if split == aliquot else "same_parent",
                                 size, wt, GRAIN, member, digest(content)) for size, wt in values))

def build(tag, extra):
    directory = ROOT / "data" if tag == "" else OUT
    source = directory / f"ml-geology{tag}.sqlite"
    target = directory / f"ml-enriched{tag}.sqlite"
    stage = target.with_suffix(".build.sqlite")
    stage.unlink(missing_ok=True)
    copy_snapshot(source, stage)
    with closing(sqlite3.connect(stage)) as db:
        with db:
            stage_solar(db)
            stage_earth_weather(db, extra)
            mars_wind(db)
            grain(db)
            check(db)
            sql = {
                "solar_sites_by_body": "SELECT body,count(DISTINCT location_id),count(*) FROM solar_scenarios GROUP BY 1",
                "earth_wind_sites": "SELECT count(DISTINCT site_id) FROM earth_environment WHERE wind_speed_10m_m_s IS NOT NULL",
                "earth_moisture_sites": "SELECT count(DISTINCT site_id) FROM earth_environment WHERE soil_water_0_to_7cm_m3_m3 IS NOT NULL",
                "mars_wind_windows": "SELECT status,count(*) FROM mars_wind_windows GROUP BY 1",
                "mars_wind_samples": "SELECT status,count(DISTINCT sample_id) FROM mars_wind_windows w JOIN planet_sample_scenarios s USING(scenario_id) GROUP BY 1",
                "earth_grain_samples": "SELECT count(*) FROM earth_grain_notes",
                "mars_texture_samples": "SELECT count(*) FROM mars_texture_context",
                "moon_grain_samples": "SELECT join_level,count(DISTINCT sample_id) FROM moon_grain_bins GROUP BY 1",
            }
            report = {key: db.execute(query).fetchall() for key, query in sql.items()}
    stage.replace(target)
    report["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)

def main():
    raw = json.loads((OUT / "era5-extra.json").read_text())
    extra = {(lat, lon, stamp): values for lat, lon, stamp, *values in raw}
    if len(extra) != len(raw):
        raise ValueError("Duplicate ERA5 grid hours")
    build("", extra)
    if (OUT / "ml-geology-local.sqlite").exists():
        build("-local", extra)

if __name__ == "__main__":
    main()
