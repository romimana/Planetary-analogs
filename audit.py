"""Checks published builds against pinned inputs and physical/relational invariants."""
import csv
import hashlib
import io
import json
import math
import sqlite3
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"

def verify_hashes(manifest, directory):
    inputs = json.loads((ROOT / manifest).read_text())
    for name, spec in inputs.items():
        expected = spec[-1] if isinstance(spec, list) else spec
        with (directory / name).open("rb") as data:
            assert hashlib.file_digest(data, "sha256").hexdigest() == expected, name
    return len(inputs)

def connect(planet):
    path = ROOT / "outputs" / f"{planet}.sqlite"
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    for table in ("samples", "time_windows"):
        assert not db.execute(f"""
            SELECT o.id FROM observations o JOIN {table} t
            ON t.id=o.{'sample_id' if table == 'samples' else 'window_id'}
            WHERE o.area_id<>t.area_id""").fetchall()
    assert not db.execute("SELECT id FROM areas EXCEPT SELECT area_id FROM assets").fetchall()
    assert not db.execute("""SELECT area_id FROM footprints
        WHERE slope_pixels > valid_pixels OR valid_pixels > raster_pixels OR slope_pixels < 1""").fetchall()
    assert not db.execute("""SELECT id FROM observations WHERE NOT length(trim(record_locator))
        OR NOT length(trim(spatial_support)) OR uncertainty<0""").fetchall()
    return db

def magnitude(cell):
    return None if cell.strip() in ("", "--", "N/A", "null", "NA") else float(cell)

def check_mars_chemistry(db):
    fields = ("Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O",
              "CaO", "TiO2", "Cr2O3", "MnO", "FeO", "Ni", "Zn", "Br")
    trace = {"Ni", "Zn", "Br"}
    expected = {}
    def add_rows(reader, site, gale=False):
        for index, row in enumerate(reader, 2):
            for field in fields:
                unit = "ppm" if field in trace else "wt%"
                suffix = ("_ppm" if field in trace else "_pct") if gale else ""
                value = magnitude(row[field + suffix])
                if value is not None:
                    error = magnitude(row[field + ("_err" if gale else ".err")])
                    expected[f"{site}:{index}", field] = (value, unit, error)
    with (WORK / "gale.csv").open(encoding="cp1252", newline="") as source:
        add_rows(csv.DictReader(source), "gale", gale=True)
    with zipfile.ZipFile(WORK / "mer.zip") as archive:
        for rover, site in [("mer1", "meridiani"), ("mer2", "gusev")]:
            with io.TextIOWrapper(archive.open(f"merap_2xxx/data/apxs_oxides_{rover}.csv"), encoding="latin1") as source:
                add_rows(csv.DictReader(source), site)
    actual = {(key, field): (val, unit, error) for key, field, val, unit, error in db.execute(
        "SELECT sample_id,parameter,value,unit,uncertainty FROM observations WHERE source_id IN ('mer','gale_apxs')")}
    assert actual == expected
    return len(actual)

def check_craters(db):
    with zipfile.ZipFile(WORK / "craters.zip") as archive:
        with io.TextIOWrapper(archive.open(archive.namelist()[0]), encoding="utf-8-sig") as data:
            expected = {
                row["CRATER_ID"]: (float(row["LAT_CIRC_IMG"]), float(row["LON_CIRC_IMG"]) % 360,
                                   float(row["DIAM_CIRC_IMG"]))
                for row in csv.DictReader(data)
            }
    actual = {id: (lat, lon, diameter) for id, lat, lon, diameter in db.execute(
        "SELECT crater_id,latitude_deg,longitude_e_deg,diameter_km FROM craters")}
    assert len(expected) == len(actual) == 385049
    assert actual == expected

def check_lunar_temperature(db):
    # Independently parse one full slice as CSV and assign projected centroids to a parent footprint.
    area_id = "lola01"
    wkt = db.execute("SELECT footprint_wkt FROM footprints WHERE area_id=?", (area_id,)).fetchone()[0]
    coords = [tuple(map(float, point.split())) for point in wkt.split("((")[1].rstrip(")").split(",")]
    west, south = coords[0]
    east, north = coords[2]
    averages, peaks = [], []
    with (WORK / "lunar/prp01.tab").open(newline="") as source:
        for row in csv.reader(source):
            lon, lat = map(math.radians, map(float, row[9:11]))
            radius = 2 * 1737400 * math.tan((lat + math.pi/2)/2)
            x, y = radius * math.sin(lon), radius * math.cos(lon)
            mean, peak = map(float, row[12:14])
            if west <= x < east and south <= y < north and 0 < mean <= peak:
                averages.append(mean)
                peaks.append(peak)
    from statistics import median

    assert db.execute("SELECT sample_count FROM time_windows WHERE area_id=?", (area_id,)).fetchone() == (len(peaks),)
    for parameter, expected in {
        "subsurface_temperature_annual_mean_spatial_median": median(averages),
        "surface_temperature_annual_max_spatial_median": median(peaks),
        "surface_temperature_annual_max_coldest_triangle": min(peaks),
    }.items():
        assert db.execute("SELECT value FROM observations WHERE area_id=? AND parameter=?",
                          (area_id, parameter)).fetchone() == (expected,)

def check_atlas(planet, db):
    atlas = ROOT / "outputs" / f"{planet.title()} Atlas.html"
    body = atlas.read_text(encoding="utf-8").split('id="data" type="application/json">', 1)[1].split("</script>", 1)[0]
    payload = json.loads(body)
    expected = set(db.execute("SELECT id FROM sources"))
    assert {(row["id"],) for row in payload["sources"]} == expected
    assert {(row["id"],) for row in payload["coverage"]} == set(db.execute("SELECT id FROM areas"))
    assert len(payload["chemistry"]) == db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert len(payload["assets"]) == db.execute("SELECT COUNT(*) FROM assets").fetchone()[0]

mars_hashes = verify_hashes("inputs.json", WORK)
moon_hashes = verify_hashes("moon-inputs.json", WORK / "lunar")
with connect("mars") as mars, connect("moon") as moon:
    apxs = check_mars_chemistry(mars)
    check_craters(mars)
    check_atlas("mars", mars)
    check_atlas("moon", moon)
    check_lunar_temperature(moon)
    assert mars.execute("SELECT latitude_deg FROM areas WHERE id='nili'").fetchone() == (8.7,)
    assert not mars.execute("SELECT id FROM science_observations WHERE source_id='gale_weather'").fetchall()
    assert moon.execute("""SELECT value FROM observations WHERE parameter='Total'
        AND sample_id='luna24:soil15:column L24'""").fetchone() == (100.4,)
    fields = {field.findtext("{*}name"): field.findtext("{*}description") for field in
              ElementTree.parse(WORK / "lunar/prp.xml").findall(".//{*}Field_Character")}
    assert "2 cm below the surface" in fields["temp_avg"]
    assert "at\n                        the surface" in fields["temp_max"]
    assert moon.execute("""SELECT COUNT(*) FROM observations
        WHERE parameter='subsurface_temperature_annual_mean_spatial_median'
        AND depth_top_m=.02 AND depth_bottom_m=.02""").fetchone() == (1727,)
    assert not moon.execute("""SELECT id FROM observations WHERE parameter=
        'surface_temperature_annual_mean_spatial_median'""").fetchall()
    query = "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"
    assert mars.execute(query).fetchall() == moon.execute(query).fetchall()
    for db, expected in ((mars, 340), (moon, 1727)):
        slopes = db.execute("SELECT value,unit,baseline_m FROM observations WHERE parameter='slope_p90'").fetchall()
        assert len(slopes) == expected and all(
            math.isfinite(v) and 0 <= v <= 90 and unit == "degree" and baseline == 40
            for v, unit, baseline in slopes)
print(f"Verified {mars_hashes+moon_hashes} input hashes and {apxs:,} APXS values, units and uncertainties, and 385,049 crater IDs, coordinates and diameters.")
