"""Build the model-facing geology and terrain tables without dropping archive records."""
import csv
import hashlib
import io
import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from zipfile import ZipFile

import numpy as np
import shapefile
from pyproj import CRS, Transformer
from shapely import Point, STRtree, make_valid
from shapely.geometry import shape

from build_earth import CACHE, OUT, fetch
from enrich_terrain import NEW, add_terrain
from package_ml import CHEMISTRY, ROOT, TERRAIN, check, copy_snapshot

MOON = "https://asc-astropedia.s3.us-west-2.amazonaws.com/Moon/Geology/Unified_Geologic_Map_of_the_Moon_GIS_v2.zip"
MARS = ("https://raw.githubusercontent.com/eleanorlutz/mars_geology_atlas_of_space/"
        "8686501f3a7737d72e3185566dcbedb1c9fd1683/data/SIM3292_MarsGlobalGeologicGIS_20M/SIM3292_Shapefiles/")
MARS_UNIT = "SIM3292_Global_Geology"
GLIM = "https://epic.awi.de/31092/1/hartmann-moosdorf_2012.zip"
CLASSES = {
    "su": "Unconsolidated sediment", "vb": "Basic volcanic rock", "ss": "Siliciclastic sedimentary rock",
    "pb": "Basic plutonic rock", "sm": "Mixed sedimentary rock", "sc": "Carbonate sedimentary rock",
    "va": "Acid volcanic rock", "mt": "Metamorphic rock", "pa": "Acid plutonic rock",
    "vi": "Intermediate volcanic rock", "py": "Pyroclastics", "pi": "Intermediate plutonic rock",
    "ev": "Evaporites",
}

def earth_geology(rows):
    raw = fetch("glim.zip", GLIM)
    sha = hashlib.sha256(raw).hexdigest()
    with ZipFile(io.BytesIO(raw)) as archive:
        gridfile = archive.read("glim_wgs84_0point5deg.txt.asc")
        grid = np.loadtxt(io.BytesIO(gridfile), skiprows=6, dtype=int)
        lookup = {int(r["Value_"]): r["xx"] for r in csv.DictReader(
            archive.read("Classnames.txt").decode().splitlines(), delimiter=";")}
    assert grid.shape == (360, 720)
    for key, lat, lon in rows:
        r, c = math.floor((90 - lat) * 2), math.floor((lon + 180) * 2)
        code = lookup.get(grid[r, c])
        if code in CLASSES:
            yield key, code, CLASSES[code], "GLiM 0.5 degree", GLIM, sha, f"row {r}, col {c}"

def vector_input(body):
    if body == "moon":
        names = ("shp", "shx", "dbf", "prj")
        raw = fetch("geomoon.zip", MOON)
        with ZipFile(io.BytesIO(raw)) as archive:
            base = next(name[:-4] for name in archive.namelist() if name.endswith("/GeoUnits.shp"))
            files = {ext: archive.read(f"{base}.{ext}") for ext in names}
        return files, MOON
    return {ext: fetch(f"{MARS_UNIT}.{ext}", f"{MARS}{MARS_UNIT}.{ext}")
            for ext in ("shp", "shx", "dbf", "prj")}, MARS + MARS_UNIT + ".shp"

def planetary_geology(body, rows):
    files, url = vector_input(body)
    sha = hashlib.sha256(b"".join(files.values())).hexdigest()
    crs = CRS.from_wkt(files["prj"].decode("ascii"))
    transform = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    points_by_coordinate = defaultdict(list)
    for sample, lat, lon in rows:
        x, y = transform.transform((lon + 180) % 360 - 180, lat)
        points_by_coordinate[x, y].append(sample)
    coordinates = list(points_by_coordinate)
    points = STRtree([Point(pair) for pair in coordinates])
    marker, description = ("Unit", "UnitDesc") if body == "mars" else ("FIRST_Unit", "FIRST_Un_2")
    matches = defaultdict(list)
    with shapefile.Reader(**{ext: io.BytesIO(files[ext]) for ext in ("shp", "shx", "dbf")},
                          encoding="latin1") as records:
        for record in records.iterShapeRecords():
            x0, y0, x1, y1 = record.shape.bbox
            possible = [i for i, (x, y) in enumerate(coordinates) if x0 <= x <= x1 and y0 <= y <= y1]
            if not possible:
                continue
            polygon = shape(record.shape.__geo_interface__)
            if not polygon.is_valid:
                polygon = make_valid(polygon)
            for i in points.query(polygon, predicate="contains"):
                for sample in points_by_coordinate[coordinates[i]]:
                    props = record.record.as_dict()
                    detail = props[description]
                    if body == "moon":
                        detail = f"{props['FIRST_Un_1']} {detail}"
                    matches[sample].append((props[marker], detail, record.record.oid))
    product = "USGS SIM3292 1:20M" if body == "mars" else "USGS Unified Moon 1:5M"
    for sample, entries in matches.items():
        units = {(code, detail) for code, detail, _ in entries}
        if len(units) == 1:
            code, detail = next(iter(units))
            yield sample, code, detail, product, url, sha, "polygon " + ",".join(str(oid) for _, _, oid in entries)

def add_geology(db):
    for body in ("earth", "mars", "moon"):
        table = f"{body}_geology"
        db.execute(f"""CREATE TABLE {table} (
            id TEXT PRIMARY KEY, geology_unit TEXT NOT NULL, geology_description TEXT NOT NULL,
            geology_product TEXT NOT NULL, geology_url TEXT NOT NULL, geology_sha256 TEXT NOT NULL,
            geology_locator TEXT NOT NULL
        )""")
        if body == "earth":
            rows = db.execute("SELECT DISTINCT site_id,latitude,longitude FROM earth_samples")
            values = earth_geology(rows)
        else:
            rows = db.execute("SELECT id,latitude,longitude_e FROM planet_samples WHERE body=?", (body,))
            values = planetary_geology(body, rows)
        db.executemany(f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)", values)

def modeling_views(db):
    features = ", ".join((*CHEMISTRY, *TERRAIN, NEW))
    geology = "g.geology_unit, g.geology_description, g.geology_product, g.geology_url, g.geology_locator"
    db.execute(f"""CREATE VIEW earth_model_profiles AS
        SELECT p.id,p.site_id,p.source_id,p.region,p.material,p.latitude,p.longitude,
               {features}, {geology}
        FROM earth_profiles p LEFT JOIN earth_geology g ON g.id=p.site_id""")
    for body in ("mars", "moon"):
        db.execute(f"""CREATE VIEW {body}_model_profiles AS
            SELECT p.id,p.area,p.material,p.latitude,p.longitude_e,p.location_role,p.comparison_status,
                   {features}, {geology}
            FROM planet_samples p LEFT JOIN {body}_geology g ON g.id=p.id
            WHERE p.body='{body}' AND p.comparison_status <> 'chemistry_hold'""")

def publish(source, target, terrain):
    stage = target.with_suffix(".stage.sqlite")
    stage.unlink(missing_ok=True)
    copy_snapshot(source, stage)
    with closing(sqlite3.connect(stage)) as db:
        with db:
            add_terrain(db, terrain)
            add_geology(db)
            modeling_views(db)
            check(db)
            coverage = {}
            for body in ("earth", "mars", "moon"):
                coverage[body] = dict(zip(("samples", "terrain", "geology", "terrain_and_geology"),
                    db.execute(f"""SELECT count(*),count({NEW}),count(geology_unit),
                          sum({NEW} IS NOT NULL AND geology_unit IS NOT NULL)
                          FROM {body}_model_profiles""").fetchone()))
    stage.replace(target)
    coverage["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    return coverage

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    records = json.loads((OUT / "terrain-public.json").read_text())
    data = ROOT / "data"
    source, target = data / "ml-full.sqlite", data / "ml-geology.sqlite"
    if args.local:
        records.update(json.loads((OUT / "terrain-local.json").read_text()))
        source, target = OUT / "ml-full-local.sqlite", OUT / "ml-geology-local.sqlite"
    coverage = publish(source, target, records)
    target.with_suffix(".json").write_text(json.dumps(coverage, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(coverage, indent=2))

if __name__ == "__main__":
    main()
