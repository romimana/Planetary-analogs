"""Enrich existing snapshots with GIS terrain metrics at all available sites."""
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from build_context import terrain as planet_terrain, terrain_metrics
from build_earth import CACHE, DEM, OUT, RADIUS, envelope, tile
from package_ml import ROOT, TERRAIN, check

NEW = "largest_gentle_patch_fraction"

def gentle_patch(grid, spacing=500):
    gx = (grid[1:-1, 2:] - grid[1:-1, :-2]) / (2 * spacing)
    gy = (grid[2:, 1:-1] - grid[:-2, 1:-1]) / (2 * spacing)
    gentle = np.hypot(gx, gy) <= np.tan(np.deg2rad(10))
    unvisited = set(zip(*np.nonzero(gentle)))
    largest = 0
    while unvisited:
        frontier = [unvisited.pop()]
        size = 0
        while frontier:
            i, j = frontier.pop()
            size += 1
            for neighbor in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                    frontier.append(neighbor)
        largest = max(largest, size)
    return largest / gentle.size

def tiles_for(lat, lon):
    west, south, east, north = envelope(lat, lon)
    return [(y, x) for y in range(math.floor(south), math.floor(north) + 1)
            for x in range(math.floor(west), math.floor(east) + 1)
            if posting_bounds(y, x, west, south, east, north)]

def posting_bounds(south, west, w, s, e, n):
    # Assign each shared posting to exactly one tile.
    c0, c1 = max(0, math.ceil((w - west) * 3600)), min(3600, math.ceil((e - west) * 3600))
    r0, r1 = max(0, math.ceil((south + 1 - n) * 3600)), min(3600, math.ceil((south + 1 - s) * 3600))
    return (r0, r1, c0, c1) if c1 > c0 and r1 > r0 else None

def tile_part(key, sites):
    south, west = key
    name = tile(*key)
    url = DEM + f"NASADEM_HGT_{name}.tif"
    local = CACHE / f"{name}.tif"
    output = []
    if not -56 <= south < 60:
        return output
    try:
        with rasterio.open(local if local.exists() else url) as dem:
            if dem.shape != (3601, 3601) or dem.crs.to_epsg() != 4326 or dem.nodata is None:
                raise ValueError("Unexpected DEM layout")
            x, y = dem.xy(0, 0)
            if abs(x - west) > 1e-8 or abs(y - south - 1) > 1e-8:
                raise ValueError("Unexpected DEM origin")
            if abs(dem.res[0] - 1 / 3600) > 1e-10 or abs(dem.res[1] - 1 / 3600) > 1e-10:
                raise ValueError("Unexpected DEM resolution")
            for site, lat, lon in sites:
                r0, r1, c0, c1 = posting_bounds(south, west, *envelope(lat, lon))
                data = dem.read(1, window=Window(c0, r0, c1-c0, r1-r0), masked=True)
                valid = ~np.ma.getmaskarray(data)
                x = (np.arange(c0, c1) / 3600 + west - lon) * np.pi / 180 * RADIUS * np.cos(np.deg2rad(lat))
                y = (south + 1 - np.arange(r0, r1) / 3600 - lat) * np.pi / 180 * RADIUS
                bins = np.floor((y[:, None] + 2500) / 500).astype(int).clip(0, 9) * 10
                bins = bins + np.floor((x[None, :] + 2500) / 500).astype(int).clip(0, 9)
                expected = np.bincount(bins.ravel(), minlength=100)
                count = np.bincount(bins[valid], minlength=100)
                sums = np.bincount(bins[valid], weights=data.data[valid], minlength=100)
                sha = hashlib.sha256(data.data.astype("<i2").tobytes() + valid.tobytes()).hexdigest()
                output.append((site, expected, count, sums, {"url": url, "rows": [r0, r1],
                                                            "columns": [c0, c1], "sha256": sha}))
    except (OSError, rasterio.errors.RasterioError, ValueError) as exc:
        print(f"Skipped {name}: {exc}", flush=True)
        return []
    return output

def earth_metrics(sites):
    buckets = defaultdict(list)
    required = {}
    for site, lat, lon in sites:
        keys = tiles_for(lat, lon)
        required[site] = set(keys)
        for key in keys:
            buckets[key].append((site, lat, lon))
    parts = defaultdict(list)
    keys = sorted(buckets)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="10",
                      GDAL_HTTP_MAX_RETRY="1", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        with ThreadPoolExecutor(max_workers=16) as pool:
            for index, (key, batch) in enumerate(zip(keys, pool.map(lambda k: tile_part(k, buckets[k]), keys)), 1):
                for site, expected, count, sums, trace in batch:
                    parts[site].append((key, expected, count, sums, trace))
                if index % 50 == 0:
                    print(f"Read {index}/{len(keys)} terrain tiles", flush=True)
    records = {}
    for site, pieces in parts.items():
        if required[site] != {piece[0] for piece in pieces}:
            continue
        expected, count, sums = (np.sum([piece[i] for piece in pieces], axis=0) for i in (1, 2, 3))
        if np.any(count == 0) or np.any(count < .95 * expected):
            continue
        grid = (sums / count).reshape(10, 10)
        records[site] = (terrain_metrics(grid, 500, 500), gentle_patch(grid),
                         json.dumps([piece[-1] for piece in pieces]), int(count.min()), int(count.max()))
    return records

def add_terrain(db, records):
    db.execute(f"ALTER TABLE earth_terrain ADD COLUMN {NEW} REAL CHECK ({NEW} BETWEEN 0 AND 1)")
    db.execute("ALTER TABLE earth_terrain ADD COLUMN raster_windows_json TEXT")
    available = {site for (site,) in db.execute("SELECT DISTINCT site_id FROM earth_samples")}
    for site in sorted(available & records.keys()):
        metrics, patch, trace, low, high = records[site]
        db.execute("INSERT OR REPLACE INTO earth_terrain VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (site, *(metrics[key] for key in TERRAIN), DEM, hashlib.sha256(trace.encode()).hexdigest(),
                    "See raster_windows_json", low, high, patch, trace))
    db.execute(f"ALTER TABLE planet_samples ADD COLUMN {NEW} REAL CHECK ({NEW} BETWEEN 0 AND 1)")
    coordinates = {}
    for sample, body, lat, lon in db.execute("SELECT id,body,latitude,longitude_e FROM planet_samples"):
        location = body, lat, lon
        if location not in coordinates:
            coordinates[location] = planet_terrain(*location, patch_metric=gentle_patch)["common_500m"][NEW]
        db.execute(f"UPDATE planet_samples SET {NEW}=? WHERE id=?", (coordinates[location], sample))
    sql, = db.execute("SELECT sql FROM sqlite_schema WHERE name='earth_profiles'").fetchone()
    db.execute("DROP VIEW earth_profiles")
    db.execute(sql.replace("t.locator AS terrain_locator", f"t.locator AS terrain_locator, t.{NEW}"))

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Retry sites absent from the existing cache")
    args = parser.parse_args()
    db_path = OUT / "ml-full-local.sqlite" if args.local else ROOT / "data/ml-full.sqlite"
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as source:
        sites = source.execute(
            "SELECT DISTINCT site_id,latitude,longitude FROM earth_samples "
            "WHERE (? = 0 OR source_id = 'GEMAS') ORDER BY site_id", (args.local,)
        ).fetchall()
    result = OUT / ("terrain-local.json" if args.local else "terrain-public.json")
    records = json.loads(result.read_text()) if args.resume and result.exists() else {}
    records.update(earth_metrics([row for row in sites if row[0] not in records]))
    result.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")
    print(f"Computed terrain for {len(records)} of {len(sites)} sites", flush=True)

if __name__ == "__main__":
    main()
