"""Build Earth comparison sites independently of laboratory sampling."""
import hashlib
import io
import json
import math
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from zipfile import ZipFile

import numpy as np
import rasterio
import shapefile
from rasterio.windows import Window, from_bounds
from shapely import Point, STRtree
from shapely.geometry import shape

from build_context import terrain_metrics
from build_earth import envelope
from build_earth_expansion import pinned
from build_enriched_ml import stage_solar
from build_geology_ml import earth_geology
from enrich_terrain import NEW, gentle_patch
from package_ml import ROOT, TERRAIN

WORLDCOVER = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
COPERNICUS = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/"
NASA_ANALOGS = "https://science.nasa.gov/solar-system/analog-explorer/"
NASA_BASALT = "https://www.nasa.gov/missions/analog-field-testing/what-is-basalt/"
COUNTRIES = ("ne_50m_admin_0_countries.zip",
             "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip",
             "5fed433373581fa648920435f937d95f2d3c0200e067409c6478dcdf1b853139")
REGIONS = [
    ("Atacama", "CHL", -24.15, -69.55, NASA_ANALOGS),
    ("Askja", "ISL", 65.05, -16.65, NASA_ANALOGS),
    ("Kilauea", "USA", 19.43, -155.30, NASA_BASALT),
    ("Aden Crater", "USA", 32.11, -107.00, NASA_ANALOGS),
    ("Mojave", "USA", 35.32, -115.75, None),
    ("Canyonlands", "USA", 38.36, -109.88, None),
    ("Svalbard", "NOR", 78.25, 15.70, None),
    ("Ramon Crater", "ISR", 30.60, 34.88, None),
    ("Tibetan Plateau", "CHN", 33.10, 88.20, None),
    ("Gobi", "MNG", 43.33, 104.05, None),
    ("Namib", "NAM", -24.63, 15.40, None),
    ("Puna", "ARG", -25.70, -67.52, None),
    ("Sahara", "DZA", 23.20, 5.60, None),
    ("Tibesti", "TCD", 20.00, 18.51, None),
    ("Danakil", "ETH", 14.15, 40.30, None),
    ("Harrat Khaybar", "SAU", 25.65, 39.94, None),
    ("Patagonian steppe", "ARG", -46.20, -68.60, None),
    ("Western Australian interior", "AUS", -25.57, 124.53, None),
]


def tile_label(lat, lon, step):
    y, x = (step * math.floor(n / step) for n in (lat, lon))
    return f"{'N' if y >= 0 else 'S'}{abs(y):02d}", f"{'E' if x >= 0 else 'W'}{abs(x):03d}"


def single_tile(bounds, step):
    w, s, e, n = bounds
    return tile_label(s, w, step) == tile_label(n, e, step)


def worldcover_url(lat, lon):
    name = "".join(tile_label(lat, lon, 3))
    return f"{WORLDCOVER}ESA_WorldCover_10m_2021_v200_{name}_Map.tif"


def dem_url(lat, lon):
    y, x = tile_label(lat, lon, 1)
    name = f"Copernicus_DSM_COG_10_{y}_00_{x}_00_DEM"
    return f"{COPERNICUS}{name}/{name}.tif"


def candidates():
    land = json.loads((ROOT / "app/assets/land.geojson").read_text(encoding="utf-8"))
    tree = STRtree([shape(f["geometry"]) for f in land["features"]])
    for lat in range(-55, 82, 3):
        for lon in range(-179, 180, 3):
            y, x = lat + .5, lon + .5
            if len(tree.query(Point(x, y), predicate="within")):
                yield y, x, "Global grid", "GRID", None
    for area, region, lat, lon, reference in REGIONS:
        for i in range(-2, 3):
            for j in range(-2, 3):
                yield round(lat + i * .16, 4), round(lon + j * .16, 4), area, region, reference


def cover_tiles(task):
    url, rows = task
    output = []
    with rasterio.open(url) as raster:
        if raster.crs.to_epsg() != 4326:
            raise ValueError("Unexpected WorldCover CRS")
        for row in rows:
            lat, lon, *_ = row
            window = from_bounds(*envelope(lat, lon), raster.transform)
            classes = raster.read(1, window=window, out_shape=(25, 25), masked=True)
            if np.any(np.ma.getmaskarray(classes)):
                continue
            bare, ice = (float(np.mean(classes.data == value)) for value in (60, 70))
            if max(bare, ice) >= .60 and not np.any(classes.data == 0):
                output.append((row, bare, ice, url, hashlib.sha256(classes.data.tobytes()).hexdigest()))
    return output


def elevation_tiles(task):
    url, samples = task
    output = []
    with rasterio.open(url) as raster:
        if raster.crs.to_epsg() != 4326 or raster.transform.b or raster.transform.d:
            raise ValueError("Unexpected Copernicus grid")
        t = raster.transform
        for row, bare, ice, cover_url, cover_hash in samples:
            lat, lon, area, region, reference = row
            w, s, e, n = envelope(lat, lon)
            bounds = from_bounds(w, s, e, n, t)
            c0, c1 = (math.ceil(v - .5) for v in (bounds.col_off, bounds.col_off + bounds.width))
            r0, r1 = (math.ceil(v - .5) for v in (bounds.row_off, bounds.row_off + bounds.height))
            if not (0 <= c0 < c1 <= raster.width and 0 <= r0 < r1 <= raster.height):
                continue
            pixels = raster.read(1, window=Window(c0, r0, c1-c0, r1-r0), masked=True)
            cols = np.floor(((np.arange(c0, c1) + .5) * t.a + t.c - w) * 10 / (e-w)).astype(int)
            rows = np.floor(((np.arange(r0, r1) + .5) * t.e + t.f - s) * 10 / (n-s)).astype(int)
            bins = (rows[:, None] * 10 + cols[None, :]).ravel()
            valid = (~np.ma.getmaskarray(pixels) & np.isfinite(pixels.data) & (pixels.data >= -500)).ravel()
            expected = np.bincount(bins, minlength=100)
            count = np.bincount(bins[valid], minlength=100)
            if np.any(count < 1) or np.any(count < expected * .95):
                continue
            sums = np.bincount(bins[valid], weights=pixels.data.ravel()[valid], minlength=100)
            grid = (sums / count).reshape(10, 10)
            metrics = terrain_metrics(grid, 500, 500)
            output.append({
                "site_id": f"terrain:{lat:.4f}/{lon:.4f}", "latitude": lat, "longitude": lon, "area": area,
                "region": region, "reference_url": reference, "terrain_url": url,
                "terrain_window": [r0, r1, c0, c1],
                "terrain_window_sha256": hashlib.sha256(pixels.data.astype("<f4").tobytes()+valid.tobytes()).hexdigest(),
                "cover_url": cover_url, "cover_sample_sha256": cover_hash,
                "bare_fraction": bare, "ice_fraction": ice,
                **{key: metrics[key] for key in TERRAIN}, NEW: gentle_patch(grid),
            })
    return output


def collect(reader, buckets):
    def run(task):
        try:
            return reader(task)
        except rasterio.errors.RasterioIOError as error:
            if not any(marker in str(error) for marker in ("404", "403", "does not exist")):
                raise
            unavailable.append(task[0])
            return []

    unavailable = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        rows = []
        for i, batch in enumerate(pool.map(run, sorted(buckets.items())), 1):
            rows.extend(batch)
            if i % 40 == 0:
                print(reader.__name__, i, "/", len(buckets), flush=True)
    return rows, sorted(unavailable)


def locate_regions(rows):
    with ZipFile(io.BytesIO(pinned(COUNTRIES))) as archive:
        files = {ext: io.BytesIO(archive.read(f"ne_50m_admin_0_countries.{ext}")) for ext in ("shp", "shx", "dbf")}
    with shapefile.Reader(**files, encoding="utf-8") as data:
        records = list(data.iterShapeRecords())
    tree = STRtree([shape(record.shape.__geo_interface__) for record in records])
    for row in rows:
        matches = tree.query(Point(row["longitude"], row["latitude"]), predicate="within")
        if len(matches) == 1:
            record = records[matches[0]].record
            row.update(region=record["ADM0_A3"], region_name=record["NAME"])
        else:
            row.update(region="GRID", region_name="Unresolved region")


def publish(rows, report, solar_sources):
    locate_regions(rows)
    report["by_region"] = dict(sorted(Counter(row["region"] for row in rows).items()))
    path = ROOT / "data/earth-terrain-sites.json"
    path.write_text(json.dumps({"report": report, "solar_sources": solar_sources, "region_source": COUNTRIES[1:],
                                "rows": rows}, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    print({k: v for k, v in report.items() if not k.startswith("unavailable")}, flush=True)


def main():
    coverage = defaultdict(list)
    proposed = list(candidates())
    for row in proposed:
        lat, lon, *_ = row
        if all(single_tile(envelope(lat, lon), step) for step in (1, 3)):
            coverage[worldcover_url(lat, lon)].append(row)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="20", GDAL_HTTP_MAX_RETRY="2"):
        exposed, missing_cover = collect(cover_tiles, coverage)
        dem = defaultdict(list)
        for record in exposed:
            lat, lon, *_ = record[0]
            dem[dem_url(lat, lon)].append(record)
        rows, missing_dem = collect(elevation_tiles, dem)
    rows.sort(key=lambda row: row["site_id"])
    assert rows and len({r["site_id"] for r in rows}) == len(rows)
    geology = {row[0]: list(row[1:]) for row in earth_geology(
        [(r["site_id"], r["latitude"], r["longitude"]) for r in rows])}
    for row in rows:
        row["geology"] = geology.get(row["site_id"])
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE terrain_sites (site_id TEXT PRIMARY KEY, latitude REAL, longitude REAL)")
        db.execute("CREATE VIEW earth_samples AS SELECT * FROM terrain_sites")
        db.executemany("INSERT INTO terrain_sites VALUES (?,?,?)",
                       ((row["site_id"], row["latitude"], row["longitude"]) for row in rows))
        stage_solar(db, ("earth",))
        solar = defaultdict(dict)
        for key, stamp, projection in db.execute("SELECT location_id,utc,horizontal_projection FROM solar_scenarios"):
            solar[key][stamp] = round(projection, 7)
        solar_sources = db.execute("SELECT kernel,url,sha256 FROM solar_sources ORDER BY kernel").fetchall()
    for row in rows:
        row["solar"] = solar[row["site_id"]]
    report = {"proposed": len(proposed), "within_source_tiles": sum(map(len, coverage.values())),
              "worldcover_passed": len(exposed), "terrain_passed": len(rows), "geology_joined": len(geology),
              "by_area": dict(Counter(row["area"] for row in rows)), "unavailable_worldcover_tiles": missing_cover,
              "unavailable_dem_tiles": missing_dem}
    publish(rows, report, solar_sources)


if __name__ == "__main__":
    main()
