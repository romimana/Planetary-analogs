"""Add measured Irish and US candidates with the same terrain method as the demo."""
import csv
import hashlib
import io
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from zipfile import ZipFile

from openpyxl import load_workbook
from pyproj import Transformer

from build_earth import CACHE, O, OXIDES, fetch
from build_enriched_ml import stage_solar
from build_geology_ml import earth_geology
from build_pilot import FIELDS
from enrich_terrain import NEW, earth_metrics
from package_ml import CHEMISTRY, ROOT, TERRAIN, check

USGS = ("usgs-top5-alt.txt", "https://pubs.usgs.gov/ds/801/downloads/Appendix_2b_Top5_18Sept2013.txt?download=1",
        "e831095cba4549a87144804aa1ccb38e07d44550ab91b27390b84fc1dbdbc894")
TELLUS = ("tellus-sediments.zip", "https://gsi.geodata.gov.ie/downloads/Geochemistry/Data/GSI_Tellus_C_stream_sediment_geochemistry.zip",
          "ac70392f2f9d3cafdc25d36a30cec66b6161bc6708ebe456b2ad7a832f1f6a5a")

def pinned(spec):
    name, url, expected = spec
    data = fetch(name, url)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Source changed: {name}")
    return data

def make_row(identifier, country, survey, material, lat, lon, values, spec, locator):
    if not (-90 < lat < 90 and -180 < lon < 180):
        raise ValueError(f"Invalid coordinates for {identifier}")
    if any(v is not None and (not math.isfinite(v) or not 0 < v <= 100) for v in values):
        return None
    if sum(v for v in values if v is not None) > 100.5 or any(v is None for v in values[1:5]):
        return None
    return (f"{survey}:{identifier}", f"{country}:{lat:.7f}/{lon:.7f}", country, survey, material,
            lat, lon, *values, spec[1], spec[2], locator)

def usgs_rows():
    lines = csv.reader(io.StringIO(pinned(USGS).decode("latin-1")), delimiter="\t")
    for header in lines:
        if header and header[0] == "Top5_LabID":
            break
    columns = {name: i for i, name in enumerate(header)}
    units = next(lines)
    for offset, row in enumerate(lines, 15):
        if not row or not row[0].strip() or not row[columns["Latitude"]].strip():
            continue
        values = [None]
        for oxide in tuple(FIELDS)[1:]:
            element, base, oxygen = OXIDES[oxide]
            col = columns[f"Top5_{element}"]
            unit = units[col].strip()
            if unit not in ("wt. %", "mg/kg"):
                raise ValueError(f"Unrecognized USGS unit for {element}: {unit}")
            try:
                value = float(row[col]) * (base + O * oxygen) / base
            except ValueError:
                values.append(None)
                continue
            values.append(value if unit == "wt. %" else value / 10000)
        if record := make_row(row[0], "USA", "USGS-DS801", "Surface soil 0–5 cm; near-total ICP",
                              float(row[columns["Latitude"]]), float(row[columns["Longitude"]]), values,
                              USGS, f"Appendix 2b record {offset}; SiteID {row[columns['SiteID']]}"):
            yield record

def tellus_rows():
    with ZipFile(io.BytesIO(pinned(TELLUS))) as archive:
        path, = [name for name in archive.namelist() if name.endswith(".xlsx")]
        with archive.open(path) as zipped:
            workbook = load_workbook(io.BytesIO(zipped.read()), read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows = sheet.values
        header = next(rows)
        indices = [header.index(f"{oxide}_%_XRFS") for oxide in FIELDS]
        limit_rows = {row[0]: row for row in workbook["Units_Detection_Limits"].values if row[0]}
        limits = [(limit_rows["LLD"][i], limit_rows["URL"][i]) for i in indices]
        converter = Transformer.from_crs(29903, 4326, always_xy=True)
        for offset, row in enumerate(rows, 2):
            sample, east, north = row[:3]
            if not isinstance(sample, str) or not all(isinstance(v, (int, float)) for v in (east, north)):
                continue
            values = [row[i] if isinstance(row[i], (float, int)) and lo <= row[i] < hi else None
                      for i, (lo, hi) in zip(indices, limits, strict=True)]
            lon, lat = converter.transform(east, north)
            if record := make_row(sample, "IRL", "GSI-Tellus", "Stream sediment <150 µm; XRF",
                                  lat, lon, values, TELLUS, f"{path.rsplit('/',1)[-1]}; row {offset}"):
                yield record
    finally:
        workbook.close()

def build(records, terrain):
    path = ROOT / "data/earth-expansion.sqlite"
    stage = path.with_suffix(".build.sqlite")
    stage.unlink(missing_ok=True)
    with closing(sqlite3.connect(stage)) as db:
        numeric = ",".join(f"{field} REAL" for field in CHEMISTRY)
        dem_columns = ",".join(f"{field} REAL NOT NULL" for field in (*TERRAIN, NEW))
        db.executescript(f"""
            PRAGMA foreign_keys=ON;
            CREATE TABLE earth_samples (
              id TEXT PRIMARY KEY, site_id TEXT NOT NULL, region TEXT NOT NULL, source_id TEXT NOT NULL,
              material TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL, {numeric},
              chemistry_source_url TEXT NOT NULL, chemistry_sha256 TEXT NOT NULL, source_locator TEXT NOT NULL
            );
            CREATE TABLE earth_terrain (site_id TEXT PRIMARY KEY, {dem_columns},
              raster_windows_json TEXT NOT NULL, min_bin_count INTEGER NOT NULL, max_bin_count INTEGER NOT NULL);
            CREATE TABLE earth_geology (site_id TEXT PRIMARY KEY, geology_unit TEXT NOT NULL,
              geology_description TEXT NOT NULL, geology_product TEXT NOT NULL, geology_url TEXT NOT NULL,
              geology_sha256 TEXT NOT NULL, geology_locator TEXT NOT NULL);
            CREATE VIEW earth_model_profiles AS
              SELECT s.*, {','.join('t.' + field for field in (*TERRAIN, NEW))},
                     g.geology_unit, g.geology_description, g.geology_product, g.geology_url, g.geology_locator
              FROM earth_samples s JOIN earth_terrain t USING(site_id) LEFT JOIN earth_geology g USING(site_id);
        """)
        records = [row for row in records if row[1] in terrain]
        if not records:
            raise ValueError("No complete terrain sites")
        db.executemany(f"INSERT INTO earth_samples VALUES ({','.join('?' for _ in records[0])})", records)
        db.executemany("INSERT INTO earth_terrain VALUES (?,?,?,?,?,?,?,?,?,?)", (
            (site, *(metrics[key] for key in TERRAIN), gentle, trace, low, high)
            for site, (metrics, gentle, trace, low, high) in terrain.items()
        ))
        db.executemany("INSERT INTO earth_geology VALUES (?,?,?,?,?,?,?)", earth_geology(
            db.execute("SELECT DISTINCT site_id,latitude,longitude FROM earth_samples").fetchall()
        ))
        stage_solar(db, ("earth",))
        check(db)
        report = db.execute("""SELECT source_id,count(*),count(DISTINCT site_id),count(sio2_wt_pct),
            count(geology_unit),sum(sio2_wt_pct IS NOT NULL AND geology_unit IS NOT NULL)
            FROM earth_model_profiles GROUP BY source_id""").fetchall()
        db.commit()
    stage.replace(path)
    coverage = {"columns": ["survey", "samples", "sites", "silica", "geology", "silica_and_geology"],
                "coverage": report, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".json").write_text(json.dumps(coverage, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(coverage, indent=2), flush=True)

def main():
    records = [*usgs_rows(), *tellus_rows()]
    ids = [row[0] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate survey sample identifier")
    coordinates = {row[1]: (row[5], row[6]) for row in records}
    print("Chemistry passed", Counter(row[3] for row in records), f"{len(coordinates)} sites", flush=True)
    if not coordinates:
        raise ValueError("No approved country data")
    cache = CACHE / "expansion-terrain.json"
    terrain = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    terrain.update(earth_metrics([(id, *ll) for id, ll in sorted(coordinates.items()) if id not in terrain]))
    terrain = {site: record for site, record in terrain.items() if site in coordinates}
    cache.write_text(json.dumps(terrain, separators=(",", ":")), encoding="utf-8")
    build(records, terrain)

if __name__ == "__main__":
    main()
