import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

from fetch_moon import CHEM, LOLA, PRP, RAW, STRIPES

WORK = Path(__file__).resolve().parent
OUT = WORK.parent / "outputs"
OUT.mkdir(exist_ok=True)
expected_hashes = json.loads((WORK.parent / "moon-inputs.json").read_text(encoding="utf-8"))
temporary = WORK / "moon.build.sqlite"
temporary.unlink(missing_ok=True)
db = sqlite3.connect(temporary)
db.row_factory = sqlite3.Row
db.executescript((WORK / "schema.sql").read_text(encoding="utf-8"))

def add(table, **fields):
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(fields.values()))

def source(id, title, url, note, filename=None, product=None):
    digest = None
    if filename:
        with (RAW / filename).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected_hashes[filename]:
            raise ValueError(f"{filename}: SHA-256 differs from the cataloged input")
    add("sources", id=id, title=title, url=url, product_id=product, file_sha256=digest, use_note=note)

def area(id, name, kind, src, lat, lon, role, note, mission=None, parent=None):
    add("areas", id=id, body="Moon", name=name, kind=kind, source_id=src,
        latitude_deg=lat, longitude_e_deg=lon % 360, geometry_role=role,
        coordinate_note=note, mission=mission, parent_id=parent)

def obs(site, field, value, unit, evidence, support, src, locator, **extra):
    add("observations", area_id=site, parameter=field, value=float(value), unit=unit,
        evidence=evidence, spatial_support=support, source_id=src, record_locator=locator, **extra)

def asset(site, src, title, kind):
    add("assets", area_id=site, title=title, kind=kind, source_id=src)

source("lroc_sites", "LROC coordinates of human features",
       "https://lroc.im-ldi.com/data/support/downloads/2016_LROC_Coordinates_of_Human_Features.pdf",
       "Landing hardware coordinates and GLD100 point elevations. Site coordinate is not a sample pickup position.")
source("apollo_images", "LPI Apollo landing site orbital photographs",
       "https://www.lpi.usra.edu/publications/slidesets/apollolanding/index.shtml", "Image collection indexed by mission.")
source("luna_images", "LPI Luna landing site maps",
       "https://www.lpi.usra.edu/publications/slidesets/apollolanding/ApolloLanding/slide_40.shtml", "Regional mission map.")
source("polar_atlas", "LPI Lunar South Pole Atlas", "https://www.lpi.usra.edu/lunar/lunar-south-pole-atlas/",
       "Regional reference imagery, maps and interpretation.")
source("moon_trek", "NASA Moon Trek", "https://trek.nasa.gov/moon/", "Interactive imagery and planetary layers.")
source("prp_label", "PDS Diviner south polar resource product label", PRP + ".xml",
       "Field locations and definitions; annual mean at 2 cm depth and annual maximum at the surface, fitted to observations.", "prp.xml")

landings = {
    "Apollo 11": (.67416, 23.47314, -1926, .3),
    "Apollo 12": (-3.0128, 336.5781, -1422, 2.2),
    "Apollo 14": (-3.64589, 342.52806, -1062, .4),
    "Apollo 15": (26.13239, 3.63330, -1931, 1),
    "Apollo 16": (-8.9734, 15.5011, 8, 3),
    "Apollo 17": (20.1911, 30.7723, -2626, 3.5),
    "Luna 16": (-.5137, 56.3638, -2452, 3.7),
    "Luna 20": (3.7863, 56.6242, -1780, 4.3),
    "Luna 24": (12.7142, 62.2129, -3670, 3.7),
}
for name, (lat, lon, elevation, accuracy) in landings.items():
    site = name.lower().replace(" ", "")
    area(site, name, "sample return landing site", "lroc_sites", lat, lon, "landing hardware",
         "LROC published feature location. Sample geolocation is at mission level.", mission=name)
    obs(site, "elevation_at_landing_hardware", elevation, "m", "published DEM value",
        "GLD100 elevation at hardware", "lroc_sites", name)
    obs(site, "coordinate_uncertainty", accuracy, "m", "published site coordinate uncertainty",
        "landing hardware", "lroc_sites", name)
    asset(site, "apollo_images" if name.startswith("Apollo") else "luna_images", f"{name} image collection", "orbital imagery")
    asset(site, "moon_trek", "Moon Trek imagery browser", "interactive imagery")

source("lcross_coords", "Marshall et al. — Locating the LCROSS Impact Craters",
       "https://ntrs.nasa.gov/citations/20140005563", "Weighted mean Centaur impact coordinates in the Mean Earth frame.")
source("lcross_water", "Colaprete et al. — Detection of water in the LCROSS ejecta plume",
       "https://pubmed.ncbi.nlm.nih.gov/20966242/", "Published ice concentration estimate for observable excavated regolith.")
source("lcross_map", "NASA SVS LCROSS impact site",
       "https://svs.gsfc.nasa.gov/3654/", "Regional impact site visualization.")
area("cabeus_lcross", "Cabeus — LCROSS impact", "impact measurement site", "lcross_coords",
     -84.6796, -48.7093, "Centaur impact point", "Weighted estimate, Mean Earth coordinates.")
obs("cabeus_lcross", "water_ice_mass_fraction", 5.6, "wt%", "published spectroscopic estimate",
    "observable excavated regolith at the Centaur impact site", "lcross_water", "Abstract",
    uncertainty=2.9, uncertainty_kind="published plus/minus")
asset("cabeus_lcross", "lcross_map", "LCROSS impact site visualization", "regional imagery")

def sample(site, src, target, fraction, line, summary=False):
    key = f"{site}:{src}:{line}"
    add("samples", id=key, area_id=site, source_id=src, target=target,
        method="historical laboratory compilation", material="lunar regolith",
        preparation_code=fraction, record_locator=line,
        quality="see source table and documented exclusions",
        duplicate_status="compilation; may overlap fractions and site summaries" if summary
        else "same parent sample may appear in both tables and multiple size fractions")
    return key

def chem(site, src, key, field, cell, unit, line, summary=False):
    cell = cell.strip()
    if cell:
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", cell):
            raise ValueError(f"{src}, {line}, {field}: {cell!r}")
        obs(site, field, float(cell), unit,
            "published soil compilation" if summary else "published laboratory result",
            "selected soils as defined by source column" if summary else "returned soil sample or size fraction",
            src, line, sample_id=key)

for n in (15, 16, 17):
    source(f"soil{n}", f"Lunar Sourcebook table 7.{n}", f"{CHEM}/tab7_{n}.asc",
           {15: "Selected soil summaries by landing site/subregion. Apollo 11 is sample 10002. Ambiguous P2O3 and anomalous Apollo 11 Na2O omitted.",
            16: "Major elements in reference soils. Size units established by companion PDF (micrometers). Ambiguous AlO2 and CrO3 column labels omitted.",
            17: "Trace elements in reference soils. Ni omitted because the authors flag potential sieve contamination."}[n],
           f"tab{n}.asc", f"Table 7.{n}")
source("soil16_label", "Lunar Sourcebook table 7.16 typeset", f"{CHEM}/tab7_16.pdf",
       "Typeset table supports the micrometer size units.")
rows = (RAW / "tab15.asc").read_text(encoding="latin-1").splitlines()
for column, name in enumerate(rows[3].split()):
    site = ("luna" if name.startswith("L") else "apollo") + re.search(r"\d+", name)[0]
    key = sample(site, "soil15", name, None, f"column {name}", summary=True)
    unit = "wt%"
    for line, row in enumerate(rows[4:23], 5):
        field = row[:8].strip()
        if field == "ppm":
            unit = "ppm"
        if field in ("", "ppm", "P2O3") or (name == "11" and field == "Na2O"):
            continue
        start = 8 + column * 8
        cell = row[8:].split()[column] if field == "Total" else row[start:start + 8]
        chem(site, "soil15", key, field, cell, unit, f"line {line}, column {name}", summary=True)

for n, start, unit in [(16, 32, "wt%"), (17, 24, "ppm")]:
    src = f"soil{n}"
    lines = (RAW / f"tab{n}.asc").read_text(encoding="latin-1").splitlines()
    header = next(row for row in lines if row.startswith("Sample"))
    fields = header[start:].split()
    for i, row in enumerate(lines[5:90], 6):
        fraction = row[16:start].strip()
        if not re.fullmatch(r"Bulk|[<>]?\d+(?:-\d+)?", fraction):
            continue
        label = row[:16].strip()
        if label:
            if label.startswith("Luna"):
                site = label.lower().replace(" ", "")
                parent_sample = lines[i][:16].strip()
            elif label.startswith("Apollo"):
                site, parent_sample = "apollo15", "15601"
            elif label not in {"21000,5", "22001,35", "24999,6"}:
                number = label.lstrip("U")[:2]
                site = "apollo" + {"10": "11", "64": "16", "67": "16", "72": "17", "76": "17", "78": "17"}.get(number, number)
                parent_sample = label.lstrip("U")
        locator = f"line {i}"
        key = sample(site, src, parent_sample, "bulk" if fraction == "Bulk" else f"{fraction} um", locator)
        for j, field in enumerate(fields):
            if field not in {"AlO2", "CrO3", "Ni*"}:
                chem(site, src, key, field, row[start + j*8:start + (j+1)*8], unit, locator)

RADIUS = 1737400
SITES = {"01": "Connecting Ridge", "04": "Shackleton Rim", "07": "Peak near Shackleton",
         "11": "de Gerlache Rim", "20": "Leibnitz Beta Plateau", "23": "Malapert Massif"}

def geographic(x, y):
    lat = math.degrees(2 * math.atan(math.hypot(x, y) / (2 * RADIUS))) - 90
    return lat, math.degrees(math.atan2(x, y)) % 360

def thermal_data(number):
    path = RAW / f"prp{number}.tab"
    first, last = STRIPES[number]
    raw = path.read_bytes()
    assert len(raw) == (last-first+1)*2400*210
    records = np.frombuffer(raw, dtype=np.dtype({
        "names": ["lon", "lat", "avg", "peak"],
        "formats": ["S15", "S15", "S8", "S8"], "offsets": [126,143,177,187], "itemsize": 210}))
    lat, lon, avg, peak = [records[k].astype(float) for k in ("lat","lon","avg","peak")]
    assert np.all((-90 <= lat) & (lat < -75))
    radius = 2 * RADIUS * np.tan(np.radians(lat+90)/2)
    return radius*np.sin(np.radians(lon)), radius*np.cos(np.radians(lon)), avg, peak

for number, name in SITES.items():
    site = f"lola{number}"
    dem = f"{site}.tif"
    source(site, f"NASA LOLA 5 m DEM Site {number}", f"{LOLA}/Site{number}/Site{number}_final_adj_5mpp_surf.tif",
           "Adjusted south polar DEM; the source notes substantial interpolation between LOLA laser tracks.", dem,
           f"Site{number}_final_adj_5mpp_surf")
    with Image.open(RAW/dem) as image:
        assert image.tag_v2[33550][:2] == (5, 5)
        x0, y0 = image.tag_v2[33922][3:5]
        assert image.tag_v2[34736][:2] == (-90, 0)
        height = np.array(image, dtype=np.float64)
    ny, nx = height.shape
    assert (ny, nx) == ((4200, 4200) if number == "23" else (3200, 3200))
    grid = height.reshape(ny//4,4,nx//4,4).mean(axis=(1,3))
    x = x0 + (np.arange(nx//4)+.5)*20
    y = y0 - (np.arange(ny//4)+.5)*20
    scale = 1 + (x[None,1:-1]**2+y[1:-1,None]**2)/(2*RADIUS)**2
    dx = (grid[1:-1,2:] - grid[1:-1,:-2])/40
    dy = (grid[2:,1:-1] - grid[:-2,1:-1])/40
    slopes = np.full(grid.shape, np.nan)
    slopes[1:-1,1:-1] = np.degrees(np.arctan(np.hypot(dx,dy)*scale))
    slopes[~np.isfinite(grid)] = np.nan

    first,last = STRIPES[number]
    temp_id = f"diviner{number}"
    start = 210 * (1 + 2400*first)
    end = 210 * (1 + 2400*(last+1)) - 1
    source(temp_id, f"Diviner PRP south — Site {number} input slice", PRP + ".tab",
           "Annual fitted mean at 2 cm and maximum at the surface. SHA-256 is for the stated 0-based inclusive HTTP byte range only.",
           f"prp{number}.tab", f"bytes={start}-{end}")
    tx, ty, avg, peak = thermal_data(number)

    def tile(tile_id, title, row, col, nr, nc, parent=None):
        west, east = x0+col*20, x0+(col+nc)*20
        north, south = y0-row*20, y0-(row+nr)*20
        lat, lon = geographic((west+east)/2, (south+north)/2)
        g = grid[row:row+nr,col:col+nc]
        s = slopes[row:row+nr,col:col+nc]
        if not np.isfinite(g).any() or not np.isfinite(s).any():
            return
        area(tile_id, title, "terrain grid cell" if parent else "south polar DEM region", site, lat, lon,
             "DEM footprint center", "Moon south polar stereographic footprint; longitude is east-positive.", parent=parent)
        polygon = f"POLYGON (({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"
        add("footprints", area_id=tile_id, source_id=site,
            native_crs="+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +type=crs",
            axis_order="easting northing", vertical_reference="LOLA lunar reference sphere (1737400 m)",
            footprint_wkt=polygon, raster_pixels=nr*nc, valid_pixels=int(np.isfinite(g).sum()),
            slope_pixels=int(np.isfinite(s).sum()))
        locator = f"20 m grid, rows [{row},{row+nr}), cols [{col},{col+nc})"
        support = f"{nc*20} x {nr*20} m footprint"
        for field, value, unit in [
            ("elevation_median", np.nanmedian(g), "m"),
            ("elevation_p10", np.nanpercentile(g,10), "m"),
            ("elevation_p90", np.nanpercentile(g,90), "m"),
            ("elevation_relief_p90_p10", np.nanpercentile(g,90)-np.nanpercentile(g,10), "m"),
            ("slope_median", np.nanmedian(s), "degree"),
            ("slope_p90", np.nanpercentile(s,90), "degree")]:
            obs(tile_id, field, value, unit, "derived from orbital DEM", support, site, locator,
                baseline_m=40 if field.startswith("slope") else None)
        for src,title,kind in [(site,"LOLA terrain GeoTIFF","terrain raster"),
                               ("polar_atlas","South Pole imagery and maps","regional imagery")]:
            asset(tile_id,src,title,kind)
        mask = (west <= tx) & (tx < east) & (south <= ty) & (ty < north) & (avg > 0) & (peak >= avg)
        count = int(mask.sum())
        if not parent:
            expected_count = 2 * (nr*20) * (nc*20) / 500**2
            assert .95*expected_count < count < 1.05*expected_count, f"Unexpected Diviner coverage for {tile_id}: {count}"
        if not count:
            return
        window = f"{tile_id}:annual"
        add("time_windows", id=window, area_id=tile_id, kind="annual thermal model", sample_count=count,
            time_standard="annual fitted product, no assigned UTC dates", source_id=temp_id)
        obs(tile_id, "subsurface_temperature_annual_mean_spatial_median", np.median(avg[mask]),
            "K", "derived from Diviner annual thermal model", f"{count} triangle centroids inside {support}",
            temp_id, polygon, window_id=window, depth_top_m=.02, depth_bottom_m=.02)
        for field, value in [
            ("surface_temperature_annual_max_spatial_median", np.median(peak[mask])),
            ("surface_temperature_annual_max_spatial_p90", np.percentile(peak[mask],90)),
            ("surface_temperature_annual_max_coldest_triangle", np.min(peak[mask]))]:
            obs(tile_id, field, value, "K", "derived from Diviner annual thermal model",
                f"{count} triangle centroids inside {support}", temp_id, polygon, window_id=window)

    tile(site, name, 0, 0, *grid.shape)
    for row in range(0,grid.shape[0],50):
        for col in range(0,grid.shape[1],50):
            tile(f"{site}-{row//50:02d}-{col//50:02d}", f"{name} · {row//50:02d}/{col//50:02d}",
                 row,col,50,50,parent=site)

for key,value in {
    "body":"Moon", "longitude":"east positive, 0–360 degrees",
    "tile_overlap":"Parent DEMs can overlap. Tiles from different DEMs are not independent.",
    "temperature":"Diviner PRP is a thermal model fitted to orbital data. Spatial percentiles are unweighted over triangle centroids. The annual mean is modeled at 2 cm depth and the annual maximum at the surface.",
    "chemistry":"Landing coordinates are mission anchors only. Samples and fractions may overlap and do not characterize a polar tile.",
    "craters":"No lunar crater catalog ingested in this build."
}.items():
    add("metadata",key=key,value=value)
db.executescript((WORK/"views.sql").read_text(encoding="utf-8"))
db.commit()
assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert db.execute("PRAGMA foreign_key_check").fetchall() == []
assert db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 161
assert db.execute("SELECT COUNT(*) FROM footprints").fetchone()[0] == 1727
assert db.execute("SELECT value FROM observations WHERE sample_id='apollo11:soil15:column 11' AND parameter='SiO2'").fetchone()[0] == 42.2
assert db.execute("SELECT value FROM observations WHERE sample_id='apollo11:soil17:line 6' AND parameter='Sc'").fetchone()[0] == 60.2
assert db.execute("SELECT value FROM observations WHERE sample_id='apollo11:soil16:line 6' AND parameter='FeO'").fetchone()[0] == 15.8
assert not db.execute("SELECT id FROM areas WHERE id NOT IN (SELECT area_id FROM assets)").fetchall()

def export_rows(query):
    return [dict(row) for row in db.execute(query)]

data = {
    "coverage": export_rows("""SELECT a.id,a.name,a.kind,a.mission,a.latitude_deg,a.longitude_e_deg,
        c.chemistry_samples,c.science_values,
        (SELECT sample_count FROM time_windows w WHERE w.area_id=a.id) AS diviner_triangles,c.linked_assets
        FROM areas a JOIN area_coverage c ON a.id=c.id ORDER BY a.parent_id IS NOT NULL,a.id"""),
    "details": export_rows("""SELECT area_id,parameter,ROUND(value,4) value,unit,evidence,spatial_support,
        baseline_m,uncertainty,source_id,record_locator FROM observations WHERE sample_id IS NULL AND window_id IS NULL ORDER BY id"""),
    "chemistry": export_rows("""SELECT s.area_id,s.target,s.preparation_code,s.source_id,
        GROUP_CONCAT(o.parameter || '=' || o.value || ' ' || o.unit, ' | ') AS composition,s.record_locator
        FROM samples s JOIN observations o ON s.id=o.sample_id GROUP BY s.id ORDER BY s.area_id,s.target"""),
    "assets": export_rows("SELECT a.*,s.url FROM assets a JOIN sources s ON a.source_id=s.id ORDER BY a.area_id"),
    "weather": export_rows("""SELECT area_id,parameter,ROUND(value,4) value,unit,evidence,spatial_support,
        source_id,window_id,depth_top_m FROM observations WHERE window_id IS NOT NULL ORDER BY id"""),
    "sources": export_rows("SELECT * FROM sources ORDER BY id"),
}
template = (WORK/"atlas.html").read_text(encoding="utf-8")
template = template.replace("מאדים", "הירח")
template = template.replace("ערכי science אינם כוללים את סדרת ההסברה של Curiosity.",
                            "משימות החזרת דגימות, אזורי קוטב ותאי שטח בגודל קילומטר רבוע.")
template = template.replace("מזג אוויר ב־Gale", "טמפרטורת קרקע")
template = template.replace("הזנת NASA/CAB מיועדת להסברה. סדרת הסול מוצגת לעיון. הארכיון המדעי של REMS מופיע בטבלת המקורות.",
                            "נתוני Diviner מסוכמים על פני משולשים בתוך כל תא. הערכים בקלווין. הממוצע השנתי בעומק 2 ס״מ, והמקסימום השנתי בפני השטח.")
template = template.replace("מדגם עמודות מכל רשומות הכימיה, באחוזי משקל. הרשומות עם סימוני איכות וכפילויות נשמרו כפי שהגיעו מהמקור.",
                            "טבלאות מדגימות אפולו ולונה. יחידות מוצגות לצד כל ערך. חלק מהדגימות קיימות בכמה טבלאות.")
template = template.replace("גובה, שיפועים, תכונות דיונות, חום, קרח וחלונות סיכום.",
                            "גובה ושיפועים לפי שטח. את חלונות הטמפרטורה אפשר לראות בלשונית הנפרדת.")
template = template.replace("['assets','details','chemistry','coverage']",
                            "['assets','details','chemistry','coverage','weather']")
payload = json.dumps(data,ensure_ascii=False,separators=(",",":")).replace("</","<\\/")
counts = {table:db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
          for table in ("areas","footprints","samples","observations","time_windows","assets","sources")}
(OUT/"Moon Atlas.html").write_text(template.replace("__DATA_JSON__",payload).replace(
    "__COUNTS__", f"{counts['areas']:,} אזורים ותאים • {counts['samples']:,} רשומות כימיה • {counts['observations']:,} ערכים"),
    encoding="utf-8")
db.close()
temporary.replace(OUT/"moon.sqlite")
print(counts)
