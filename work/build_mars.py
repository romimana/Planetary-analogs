import csv
import hashlib
import html
import io
import json
import math
import re
import sqlite3
import statistics
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
OUT = ROOT / "outputs"
DB = WORK / "mars.build.sqlite"
DB.unlink(missing_ok=True)
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
db.executescript((WORK / "schema.sql").read_text(encoding="utf-8"))


def add(table, **fields):
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    db.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(fields.values()))


def source(id, title, url, note, product=None, filename=None):
    digest = None
    if filename:
        with (WORK / filename).open("rb") as file:
            digest = hashlib.file_digest(file, "sha256").hexdigest()
    add("sources", id=id, title=title, url=url, product_id=product,
        use_note=note, file_sha256=digest)


def area(id, name, kind, source_id, lat=None, lon=None, mission=None, parent=None,
         note="Coordinates as published; longitude converted to 0–360° E.", role="reference point"):
    add("areas", id=id, name=name, kind=kind, source_id=source_id,
        latitude_deg=lat, longitude_e_deg=None if lon is None else lon % 360,
        mission=mission, parent_id=parent, geometry_role=role, coordinate_note=note)


def obs(site, field, value, unit, evidence, support, src, locator, **extra):
    if value is None:
        return
    values = {"value_text": value} if isinstance(value, str) else {"value": value}
    add("observations", area_id=site, parameter=field, unit=unit, evidence=evidence,
        spatial_support=support, source_id=src, record_locator=locator, **values, **extra)


def asset(area_id, src, title, kind, locator=None):
    add("assets", area_id=area_id, title=title, kind=kind, source_id=src, locator=locator)


def number(value):
    if value is None or str(value).strip() in ("", "--", "N/A", "null", "NA"):
        return None
    result = float(value)
    if not math.isfinite(result) or result in (-999, -9999):
        raise ValueError(f"Unexpected special value: {value!r}")
    return result


source("landing", "Mellon et al. — History of ground ice, Table 2",
       "https://doi.org/10.1016/j.icarus.2021.114667",
       "Landing-area model inputs from published Table 2. Reference coordinates as printed; Jezero is the study reference near the landing site. Elevation is relative to the Mars reference surface.")
source("dunes", "Davis et al. — Quantified Aeolian Dune Changes, Table 1 and Figure 1",
       "https://discovery.ucl.ac.uk/id/eprint/10088261/1/2019EA000874.pdf",
       "Published geometric-mean estimates from repeat CTX imagery and terrain models; uncertainty is reported spread, not instrument accuracy.", "10.1029/2019EA000874")
source("pixl", "Simon et al. — Jezero crater floor samples, Table 4",
       "https://doi.org/10.1029/2022JE007474",
       "Bulk sums on abraded rock spots. Source has separate 1σ error and within-scan standard deviation columns; the database uses the 1σ error.", "10.1029/2022JE007474")
source("mer", "NASA PDS — Spirit and Opportunity APXS oxide abundances",
       "https://pds-geosciences.wustl.edu/missions/mer/mer_apxs_oxide.htm",
       "2021 ZIP; the source .err columns are 2σ statistical precision. Norm is a standoff indicator, and short integration/standoff can affect precision. Coordinates are not in these two tables.", "10.17189/1518973", "mer.zip")
source("gale_apxs", "NASA PDS — Berger Curiosity APXS targets, sols 0–3076",
       "https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/",
       "Original target coordinates in metres and original elevation retained. Do not treat easting/northing as lon/lat. Source duplicate and low-quality flags retained verbatim.", "10.17189/6q8a-kg55 / ds01_2021je007171r.csv", "gale.csv")
source("gale_weather", "NASA / CAB — Curiosity REMS daily public weather feed",
       "https://mars.nasa.gov/rss/api/?category=msl&feed=weather&feedtype=json",
       "OUTREACH ONLY per publisher. Sampling is incomplete and the rover moves. Earth date is the source report date, not start UTC. Do not use these data as calibrated scientific evidence.", "NASA/CAB weather JSON, accessed 2026-11-14", "gale_weather.json")
source("insight_weather", "NASA / JPL — InSight weather API documentation, Appendix A",
       "https://api.nasa.gov/assets/insight/InSight%20Weather%20API%20Documentation.pdf",
       "Published example for sols 259 and 260; pressure and wind fields only. Temperature omitted because this document conflicts on its unit.")
source("hp3", "Grott et al. — InSight thermal conductivity",
       "https://doi.org/10.1029/2021JE006861", "Active heating measurement; value applies to a depth interval.")
source("tecp", "Grott et al. — Seasonal variations in soil conductivity",
       "https://doi.org/10.1029/2023GL102975", "Phoenix conductivity cited from Zent et al.; different depth and method from HP³.")
source("phoenix_ice", "Stoker et al. — Habitability of the Phoenix landing site",
       "https://doi.org/10.1029/2009JE003421", "Phoenix trench samples and context, Table 1.")
source("phoenix_dig", "Arvidson et al. — Phoenix robotic arm experiment",
       "https://doi.org/10.1029/2009JE003408", "Stone Soup excavation did not reach icy soil by approximately 18 cm.")
source("insight_slope", "USGS / Fergason et al. — Slopes at InSight",
       "https://pubs.usgs.gov/publication/70177060", "Published slope at 1 m baseline, representative of most of the studied ellipse.")
source("insight_terrain", "Warner et al. — InSight stratigraphic characterization",
       "https://doi.org/10.1029/2022JE007232", "Figure 8c, slopes calculated using 3 × 3 pixels of a 1 m DEM; variability is within terrain class.")
source("phoenix_slope", "Mellon et al. — Prelanding assessment of the Phoenix ice table",
       "https://doi.org/10.1029/2007JE003067", "Primary landing area (box 1); approximate range of median slopes over a 250 m baseline.")
source("craters", "Robbins–Hynek — Mars Crater Database, 2020 release",
       "https://craters.sjrdesign.net/", "Original author archive. Circle-fit geological inventory; not candidate site profiles. Coverage and morphologic classifications have documented limitations. 2020 CSV lacks depth.", "Catalog_Mars_Release_2020_1kmPlus_FullMorphData.csv", "craters.zip")
source("landing_map", "NASA/JPL — Mars landing sites overview", 
       "https://science.nasa.gov/image-detail/45468-landingsitescontextmap-featperseverance/", "Orbital context map with nine NASA landing sites.")
source("viking_gallery", "NASA — Viking imagery", "https://science.nasa.gov/mars/resources/viking-mission-resources/", "Lander images from both locations.")
source("pathfinder_view", "NASA — Pathfinder landing site", "https://science.nasa.gov/resource/mars-pathfinder-landing-site/", "Orbital and horizon features.")
source("spirit_view", "NASA/JPL — Spirit from orbit", "https://www.jpl.nasa.gov/news/nasa-mars-orbiter-photographs-spirit-and-vikings-on-the-ground/", "HiRISE view of Spirit in Columbia Hills.")
source("opportunity_view", "NASA — Opportunity Eagle Crater traverse area", "https://science.nasa.gov/photojournal/eagle-crater-traverse-area/", "Overhead view of the landing site and planned traverse.")
source("phoenix_view", "NASA/JPL — Phoenix’s Lay of the Land", "https://www.jpl.nasa.gov/images/pia10908-phoenixs-lay-of-the-land/", "Trench imagery and context.")
source("insight_view", "NASA/JPL — InSight press kit, landing site", "https://www.jpl.nasa.gov/news/press_kits/insight/landing/mission/landing-site/", "Topographic and landing-ellipse views.")
source("zhurong_view", "NASA/JPL — The Zhurong Rover Explores Utopia Planitia", "https://www.jpl.nasa.gov/images/pia24914-the-zhurong-rover-explores-utopia-planitia/", "HiRISE orbital context.")
source("oxia_view", "ESA — Oxia Planum close up", "https://www.esa.int/ESA_Multimedia/Images/2018/11/Oxia_Planum_close_up", "HiRISE image and orbital clay interpretation.")
source("jezero_map", "NASA — Perseverance location map", "https://science.nasa.gov/mission/mars-2020-perseverance/location-map/", "Interactive rover traverse.")
source("jezero_dem", "USGS — Mars 2020 Jezero CTX DEM mosaic",
       "https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic",
       "Read the original numeric elevations and GeoTIFF metadata. Slope from central differences at 20 m postings; only cells with all four neighbors plus center valid.",
       "M20_JezeroCrater_CTXDEM_20m.tif", "jezero_dem.tif")
source("jezero_geology", "USGS — Geologic map of Jezero and Nili Planum", "https://pubs.usgs.gov/publication/sim3464", "Regional geological GIS resource.")
source("gale_dem", "USGS — Gale merged DEM", "https://astrogeology.usgs.gov/search/map/mars_msl_gale_merged_dem_1m", "1 m postings; linked.")
source("gale_view", "NASA — Gale surface materials", "https://science.nasa.gov/photojournal/gale-craters-surface-materials/", "THEMIS false-color context.")
source("gale_rems", "NASA PDS — Curiosity REMS science archive", "https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html", "Calibrated archive linked for science use.")
source("gale_chemin", "Gale Crater Mineralogy and Geochemistry Database", "https://galecrater.samples.odr.io/odr/chemin", "Mineral-phase archive linked; chemical oxide rows are stored separately.")
source("meda", "NASA PDS — Perseverance MEDA", "https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html", "Calibrated and derived environmental sensor archives linked.")
source("mawrth", "HiRISE — Layering Along a Tributary to Mawrth Vallis", "https://hirise.lpl.arizona.edu/dtm/PSP_002074_2025", "Stereo terrain model and context for CRISM/OMEGA orbital clay detections.")
source("nili_view", "HiRISE — The Active Dunes of Nili Patera", "https://hirise.lpl.arizona.edu/ESP_035603_1890", "Orbital image of active dunes.")
source("mars_trek", "NASA/JPL — Mars Trek", "https://trek.nasa.gov/mars/", "Planet-wide basemap and context for catalog crater coordinates.")

landing_sites = [
    ("phoenix", "Vastitas Borealis", "Phoenix", 68.219, 234.249, 299, .190, -4126, "phoenix_view"),
    ("meridiani", "Meridiani Planum", "Opportunity", -1.948, 354.474, 190, .144, -1402, "opportunity_view"),
    ("gusev", "Gusev Crater", "Spirit", -14.572, 175.478, 337, .222, -1922, "spirit_view"),
    ("gale", "Gale Crater", "Curiosity", -4.590, 137.442, 321, .248, -3358, "gale_view"),
    ("viking1", "Chryse Planitia", "Viking 1", 22.269, 312.051, 293, .208, -3607, "viking_gallery"),
    ("viking2", "Utopia Planitia — Viking 2", "Viking 2", 47.668, 134.284, 248, .233, -4494, "viking_gallery"),
    ("pathfinder", "Ares Vallis", "Pathfinder / Sojourner", 19.098, 326.742, 394, .184, -3667, "pathfinder_view"),
    ("insight", "Elysium Planitia", "InSight", 4.498, 135.618, 216, .236, -2649, "insight_view"),
    ("jezero", "Jezero Crater", "Perseverance", 18.44, 77.50, 315, .149, -2647, "jezero_map"),
    ("oxia", "Oxia Planum", "Rosalind Franklin candidate", 18.25, 335.50, 467, .203, -3072, "oxia_view"),
    ("zhurong", "Utopia Planitia — Zhurong region", "Zhurong", 24.80, 110.30, 241, .231, -4052, "zhurong_view"),
]
for id, name, mission, lat, lon, ti, albedo, elevation, visual in landing_sites:
    kind = "candidate landing region" if id == "oxia" else "mission study area"
    area(id, name, kind, "landing", lat, lon, mission)
    for field, value, unit in (
        ("thermal_inertia", ti, "J m^-2 K^-1 s^-0.5"),
        ("albedo", albedo, "fraction"), ("elevation", elevation, "m"),
    ):
        obs(id, field, value, unit, "published regional input", "study reference area", "landing", "Table 2")
    asset(id, visual, "Site imagery or map", "visual")
    if visual != "oxia_view" and id != "zhurong":
        asset(id, "landing_map", "NASA landing sites overview", "regional map")

for id, items in {
    "jezero": [("jezero_dem", "CTX elevation model", "terrain"), ("jezero_geology", "Geologic units", "geology"),
               ("meda", "MEDA science tables", "archive")],
    "gale": [("gale_dem", "HiRISE merged elevation model", "terrain"),
             ("gale_rems", "Calibrated REMS", "archive"), ("gale_chemin", "CheMin mineralogy", "archive")],
    "insight": [("insight_terrain", "Slope and terrain illustrations", "terrain")],
}.items():
    for item in items:
        asset(id, *item)

from PIL import Image
import numpy as np

with Image.open(WORK / "jezero_dem.tif") as dem:
    cols, rows = dem.size
    dx, dy, _ = dem.tag_v2[33550]
    tie = dem.tag_v2[33922]
    assert tie[:3] == (0, 0, 0) and dx == dy == 20
    x_origin, y_origin = tie[3:5]
    nodata = float(dem.tag_v2[42113])
    params = dem.tag_v2[34736]
    assert params == (0., 0., 18.4663, 0., 0., 3396190., 3396190., 0.)
    parallel = math.radians(params[2])
    radius = params[5]
    spacing = 250  # 5 km square at 20 m postings
    for row in range(0, rows-spacing+1, spacing):
        for col in range(0, cols-spacing+1, spacing):
            elevations = np.asarray(dem.crop((col, row, col+spacing, row+spacing)), dtype=np.float64)
            valid = np.isfinite(elevations) & (elevations > nodata / 2)
            if valid.mean() < .90:
                continue
            elevations[~valid] = np.nan
            x0, x1 = x_origin+col*dx, x_origin+(col+spacing)*dx
            y0, y1 = y_origin-row*dy, y_origin-(row+spacing)*dy
            lat = math.degrees((y0+y1)/2/radius)
            lon = math.degrees((x0+x1)/2/(radius*math.cos(parallel)))
            slope_x = (elevations[1:-1,2:] - elevations[1:-1,:-2]) / (2*dx)
            local_latitude = (y0 - (np.arange(1,spacing-1)+.5)*dy) / radius
            slope_x *= (math.cos(parallel) / np.cos(local_latitude))[:,None]
            slope_y = (elevations[2:,1:-1] - elevations[:-2,1:-1]) / (2*dy)
            slopes = np.degrees(np.arctan(np.hypot(slope_x,slope_y)))
            slopes[~valid[1:-1,1:-1]] = np.nan
            sid = f"jezero_ctx_{row//spacing:02d}_{col//spacing:02d}"
            area(sid, f"Jezero CTX cell {row//spacing:02d}/{col//spacing:02d}", "terrain grid cell",
                 "jezero_dem", lat, lon, parent="jezero", role="5 km projected cell centroid",
                 note="Planetocentric centroid derived from native GeoTIFF using Mars 2000 sphere and standard parallel 18.4663° N.")
            wkt = f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"
            add("footprints", area_id=sid, native_crs="+proj=eqc +lat_ts=18.4663 +lat_0=0 +lon_0=0 +R=3396190 +units=m",
                axis_order="easting,northing (m)", vertical_reference="Native USGS DEM elevation reference",
                footprint_wkt=wkt, source_id="jezero_dem", raster_pixels=valid.size, valid_pixels=int(valid.sum()),
                slope_pixels=int(np.isfinite(slopes).sum()))
            locator = f"pixels col=[{col},{col+spacing}), row=[{row},{row+spacing})"
            for field, value, unit in [
                ("elevation_median",np.nanmedian(elevations),"m"),
                ("local_relief_p95_minus_p05",np.diff(np.nanpercentile(elevations,[5,95]))[0],"m"),
                ("slope_median",np.nanmedian(slopes),"degree"),
                ("slope_p90",np.nanpercentile(slopes,90),"degree"),
            ]:
                obs(sid, field, round(float(value),5), unit, "derived from public DEM", "5 km projected cell",
                    "jezero_dem", locator, baseline_m=40 if field.startswith("slope") else None,
                    note="20 m grid; 40 m central-difference baseline." if field.startswith("slope") else "20 m grid.")
            asset(sid, "jezero_dem", "Jezero terrain model preview", "regional terrain", locator)

area("mawrth", "Mawrth Vallis tributary", "orbital mineral target", "mawrth",
     note="Reference is the DTM footprint linked below; no point substituted.")
asset("mawrth", "mawrth", "HiRISE terrain and context", "terrain / visual")
for id, name in (("mawrth", "clay minerals"), ("oxia", "Fe/Mg-rich clay, including smectite")):
    src = "mawrth" if id == "mawrth" else "oxia_view"
    obs(id, "mineral_detection", name, None, "orbital spectral interpretation", "regional outcrops", src, "product description")

dunes = [
    ("nili", "Nili Patera", 8.7, 67.32, 9.2, 79, 22.4, 8.8, .5, .3, 11.6, 7.2, "b"),
    ("meroe", "Meroe Patera", 7.28, 67.75, 9.5, 50, 17.5, 6.9, .5, .2, 9.5, 3.6, "c"),
    ("herschel_w", "West Herschel", -15.26, 127.92, 9.2, 42, 12.5, 5.4, .3, .1, 3.6, 1.6, "d"),
    ("herschel_e", "East Herschel", -15.59, 131.88, 7.8, 12, 7.7, 3.1, .5, .2, 4.4, 1.5, "e"),
    ("mclaughlin", "McLaughlin Crater dunes", 21.57, -22.55, 7.6, 26, 11.2, 5.1, .2, .1, 2.4, 1.4, "f"),
    ("hellespontus", "Hellespontus Montes dunes", -44.45, 44.58, 11.3, 30, 9.7, 4.9, 1.1, .4, 10.2, 6.55, "g"),
]
for id, name, lat, lon, years, n, height, hsd, rate, rsd, flux, fsd, figure in dunes:
    area(id, name, "dune field", "dunes", lat, lon,
         note="Center of T1 image from Table 1; longitude converted to 0–360° E.")
    asset(id, "dunes", "Orbital photograph in the study", "visual", f"Figure 1{figure}")
    for field, value, unit, sd in [
        ("dune_height", height, "m", hsd), ("dune_migration_rate", rate, "m/Earth year", rsd),
        ("crest_sand_flux", flux, "m^3 m^-1/Earth year", fsd),
        ("study_elapsed_time", years, "Earth year", None), ("dunes_measured", n, "count", None),
    ]:
        obs(id, field, value, unit, "published orbital estimate", "sampled portion of dune field",
            "dunes", "Table 1", uncertainty=sd, uncertainty_kind="reported spread" if sd else None)
asset("nili", "nili_view", "HiRISE active dune image", "visual")

for id, name in [("snow_white", "Snow White trench"), ("stone_soup", "Stone Soup trench")]:
    area(id, name, "trench", "phoenix_ice" if id == "snow_white" else "phoenix_dig",
         parent="phoenix", note="Local trench in Phoenix workspace; separate coordinates not assigned.")
    asset(id, "phoenix_view", "Phoenix workspace imagery", "context visual")
obs("snow_white", "material_at_depth", "ice-cemented soil", None, "in situ sample",
    "trench sample", "phoenix_ice", "Table 1, Sorceress2", depth_top_m=.05, depth_bottom_m=.05)
obs("stone_soup", "icy_soil_reached", "no, through approximately 0.18 m", None, "in situ excavation",
    "trench", "phoenix_dig", "Stone Soup excavation narrative", depth_top_m=0, depth_bottom_m=.18)
obs("phoenix", "soil_thermal_conductivity", .085, "W m^-1 K^-1", "in situ derived",
    "lander workspace, near-surface layer", "tecp", "Introduction (Phoenix TECP cited from Zent et al.)",
    depth_top_m=0, depth_bottom_m=.015)
obs("insight", "soil_thermal_conductivity", .039, "W m^-1 K^-1", "in situ derived",
    "HP3 heating experiment", "hp3", "Abstract", uncertainty=.002, uncertainty_kind="published uncertainty",
    depth_top_m=.03, depth_bottom_m=.37)
obs("insight", "slope_mean", 3.2, "degree", "published terrain statistic",
    "majority of study ellipse", "insight_slope", "Abstract", baseline_m=1)
for label, value, sd in [("Smooth Terrain", 2.0, 1.0), ("Etched Terrain", 4.1, 2.9)]:
    obs("insight", "slope_mean", value, "degree", "published terrain statistic", label,
        "insight_terrain", "Figure 8c", uncertainty=sd, uncertainty_kind="within-class standard deviation",
        note="Derived in a 3×3 window on 1 m postings.")
for field, value in [("slope_median_lower", .5), ("slope_median_upper", 1.0)]:
    obs("phoenix", field, value, "degree", "published terrain statistic", "primary landing region (box 1)",
        "phoenix_slope", "Prelanding slope analysis, approximate range", baseline_m=250)

oxide_fields = ["Na2O", "MgO", "Al2O3", "SiO2", "P2O5", "SO3", "Cl", "K2O", "CaO",
                "TiO2", "Cr2O3", "MnO", "FeO", "Ni", "Zn", "Br"]
material_codes = {"S": "soil", "R": "rock", "O": "outcrop", "C": "cobble"}
with zipfile.ZipFile(WORK / "mer.zip") as archive:
    for rover, site in [("mer1", "meridiani"), ("mer2", "gusev")]:
        path = f"merap_2xxx/data/apxs_oxides_{rover}.csv"
        with io.TextIOWrapper(archive.open(path), encoding="latin1") as handle:
            for line, row in enumerate(csv.DictReader(handle), start=2):
                record = f"{path} line {line}: {row['Spectrum']}"
                code = row["Type"]
                sample = f"{site}:{line}"
                sol_match = re.match(r"[AB](\d+)_", row["Spectrum"])
                add("samples", id=sample, area_id=site, method="APXS", target=row["Name"],
                    material=material_codes.get(code[:1]), preparation_code=code,
                    sol=int(sol_match[1]) if sol_match else None,
                    source_id="mer", record_locator=record, integration_hours=number(row["Time/h"]),
                    instrument_norm=number(row["Norm"]))
                for field in oxide_fields:
                    obs(site, field, number(row[field]), "ppm" if field in ("Ni", "Zn", "Br") else "wt%",
                        "in situ derived", "APXS target", "mer", record, sample_id=sample,
                        uncertainty=number(row[field + ".err"]), uncertainty_kind="2sigma statistical precision")

with (WORK / "gale.csv").open(encoding="cp1252") as handle:
    for line, row in enumerate(csv.DictReader(handle), start=2):
        record = f"ds01_2021je007171r.csv line {line}: {row['Target']}"
        code = row["Preparation_method"] or ""
        sample = f"gale:{line}"
        stratigraphy = " / ".join(row[col] for col in ("Strat_group_formal", "Strat_fm", "Strat_mbr",
                                  "Informal waypoint/outcrop/region name") if row[col])
        add("samples", id=sample, area_id="gale", method="APXS", target=row["Target"],
            material=material_codes.get(code[:1]), preparation_code=code or None,
            sol=int(row["Sol"]), local_time_original=row["Start_Time"],
            easting_m=number(row["Easting_m"]), northing_m=number(row["Northing_m"]),
            elevation_m_original=number(row["Elevation_m"]), quality=row["Quality"] or None,
            duplicate_status=row["Duplicate_measurement"] or None, source_id="gale_apxs",
            record_locator=record, fit_type=row["Fit_Type"], stratigraphy=stratigraphy or None)
        for field in oxide_fields:
            trace = field in ("Ni", "Zn", "Br")
            obs("gale", field, number(row[field + ("_ppm" if trace else "_pct")]), "ppm" if trace else "wt%",
                "in situ derived", "APXS target", "gale_apxs", record, sample_id=sample,
                uncertainty=number(row[field + "_err"]), uncertainty_kind="source reported error")

pixl_targets = [("Guillaumes",167), ("Bellegarde",187), ("Dourbes",257), ("Dourbes2",270),
                ("Quartier1",294), ("Quartier2",301), ("Montpezat2",350), ("Alfalfa",369)]
pixl_data = {
    "Na2O": [(5.71,.72),(4.76,.56),(1.70,.56),(2.24,.54),(2.27,.77),(1.93,.60),(3.40,.97),(5.28,.66)],
    "MgO": [(2.63,.56),(2.19,.64),(19.73,.99),(18.53,.93),(15.86,.80),(13.13,.66),(6.15,.31),(.76,.32)],
    "Al2O3": [(7.56,.38),(6.96,.35),(1.96,.51),(3.08,.56),(1.50,.44),(2.35,.55),(5.82,.29),(11.88,.60)],
    "SiO2": [(38.28,1.92),(43.78,2.19),(40.36,2.02),(38.08,1.91),(34.13,1.71),(41.36,2.07),(44.95,2.25),(57.16,2.86)],
    "P2O5": [(1.64,.54),(2.75,.56),(.29,.25),(.74,.29),(.42,.24),(.29,.25),(1.09,.43),(.98,.37)],
    "SO3": [(2.69,.56),(3.21,.56),(.52,.21),(1.15,.36),(8.61,.46),(1.70,.47),(.93,.35),(1.96,.51)],
    "Cl": [(3.50,.54),(1.52,.44),(.62,.34),(.74,.25),(1.15,.48),(.96,.36),(.79,.27),(1.05,.34)],
    "K2O": [(.75,.26),(1.06,.34),(.12,.14),(.26,.23),(.12,.14),(.21,.21),(.73,.25),(1.93,.51)],
    "CaO": [(7.80,.39),(7.64,.38),(3.89,.49),(1.58,.45),(2.75,.56),(6.09,.31),(9.08,.46),(4.42,.40)],
    "TiO2": [(1.48,.54),(2.49,.58),(.39,.24),(.32,.23),(.25,.23),(1.01,.33),(1.06,.42),(.68,.29)],
    "Cr2O3": [(.03,.06),(.01,.03),(.30,.25),(.22,.21),(.05,.06),(.30,.24),(.07,.09),(.02,.05)],
    "MnO": [(.47,.20),(.44,.23),(.73,.31),(.62,.22),(.70,.24),(.59,.24),(.52,.21),(.32,.25)],
    "FeO": [(18.76,.94),(23.26,1.16),(30.01,1.50),(30.04,1.50),(30.16,1.51),(26.35,1.32),(20.86,1.04),(11.34,.57)],
}
for index, (target, sol) in enumerate(pixl_targets):
    sample = f"jezero:{target}"
    record = f"Table 4, {target}, sol {sol}"
    add("samples", id=sample, area_id="jezero", method="PIXL bulk sum", target=target,
        material="rock", preparation_code="abraded", sol=sol, source_id="pixl", record_locator=record)
    for field, pairs in pixl_data.items():
        value, error = pairs[index]
        obs("jezero", field, value, "wt%", "in situ derived", "PIXL scan area",
            "pixl", record, sample_id=sample, uncertainty=error, uncertainty_kind="1sigma reported error",
            note="Source labels total iron FeO-T." if field == "FeO" else None)

weather_cols = {"min_temp": ("air_temperature_min", "degC"), "max_temp": ("air_temperature_max", "degC"),
                "min_gts_temp": ("ground_temperature_min", "degC"), "max_gts_temp": ("ground_temperature_max", "degC"),
                "pressure": ("daily_pressure_reported", "Pa")}
weather = json.loads((WORK / "gale_weather.json").read_text(encoding="utf-8"))["soles"]
for row in weather:
    sol = int(row["sol"])
    key = f"gale:weather:{sol}"
    add("time_windows", id=key, area_id="gale", kind="daily outreach report", sol=sol,
        report_date=row["terrestrial_date"], ls_deg=number(row["ls"]), time_standard="Curiosity sol / source Earth report date",
        source_id="gale_weather")
    for col, (field, unit) in weather_cols.items():
        obs("gale", field, number(row[col]), unit, "outreach summary", "rover at varying locations",
            "gale_weather", f"soles id={row['id']}; sol={sol}; {col}", window_id=key)
    if row["local_uv_irradiance_index"] not in ("", "--", None, "N/A"):
        obs("gale", "uv_index_category", row["local_uv_irradiance_index"], None,
            "outreach summary", "rover at varying locations", "gale_weather",
            f"soles id={row['id']}; sol={sol}; local_uv_irradiance_index", window_id=key)

for start in range(0, 360, 90):
    group = [r for r in weather if (ls := number(r["ls"])) is not None and start <= ls < start + 90]
    win = f"gale:ls:{start}"
    add("time_windows", id=win, area_id="gale", kind="pooled seasonal outreach summary",
        ls_start_deg=start, ls_end_deg=start+90, sample_count=len(group),
        time_standard="Mars solar longitude Ls; all available Mars years pooled",
        source_id="gale_weather")
    for col, (field, unit) in weather_cols.items():
        values = [n for r in group if (n := number(r[col])) is not None]
        obs("gale", field + "_median", statistics.median(values), unit, "derived from outreach data",
            "rover at varying locations", "gale_weather", f"{start}<=Ls<{start+90}; {col}; n={len(values)}",
            window_id=win, note="Median of available sol summaries, not a simultaneous multi-variable window.")

for sol, first, last, pressure, count, wind, wind_count in [
    (259,"2019-08-19T08:03:59Z","2019-08-20T08:43:34Z",761.006,163012,4.35,154146),
    (260,"2019-08-20T08:43:34Z","2019-08-21T09:23:09Z",762.462,149206,None,None)
]:
    key = f"insight:weather:{sol}"
    add("time_windows", id=key, area_id="insight", kind="published daily example", sol=sol,
        start_utc=first, end_utc=last, time_standard="UTC source range and InSight mission sol",
        source_id="insight_weather")
    for field, value, unit, n in [("pressure_mean", pressure, "Pa", count),("wind_speed_mean",wind,"m/s",wind_count)]:
        obs("insight", field, value, unit, "published sensor summary", "lander station",
            "insight_weather", f"Appendix A, sol {sol}", window_id=key, note=f"Samples: {n}")

with zipfile.ZipFile(WORK / "craters.zip") as archive:
    with io.TextIOWrapper(archive.open(archive.namelist()[0]), encoding="utf-8-sig") as handle:
        def crater_rows():
            for row in csv.DictReader(handle):
                yield (row["CRATER_ID"], number(row["LAT_CIRC_IMG"]), number(row["LON_CIRC_IMG"]) % 360,
                       number(row["DIAM_CIRC_IMG"]), number(row["DIAM_CIRC_SD_IMG"]),
                       number(row["DIAM_ELLI_MAJOR_IMG"]), number(row["DIAM_ELLI_MINOR_IMG"]),
                       number(row["ARC_IMG"]), row["INT_MORPH1"] or None,
                       " / ".join(filter(None, (row["LAY_MORPH1"], row["LAY_MORPH2"], row["LAY_MORPH3"]))) or None, "craters")
        db.executemany("INSERT INTO craters VALUES(?,?,?,?,?,?,?,?,?,?,?)", crater_rows())

for key, value in {
    "scope": "Mars reference profiles and independently cataloged craters. Earth matching data are not in this release.",
    "coordinates": "Area points and crater centroids use source Mars coordinates and east longitude in [0, 360). Views may display points contextually; do not use an Earth CRS.",
    "sample_coordinates": "APXS easting/northing/elevation are verbatim source fields. Preserve original coordinates and confirm native rover frame and vertical reference before joining to a DEM.",
    "output_use": "Use area_coverage to see what is loaded. Linked sources in assets are not counts of loaded observations.",
    "units": "Oxide abundances use weight percent; trace Ni, Zn, and Br are ppm. FeO convention, preparation, standoff, and uncertainty depend on source.",
    "weather": "The 4 seasonal windows summarize outreach data across many Mars years and locations of the moving rover. They are excluded from the science_observations view.",
    "crater_scope": "2020 catalog entries are separate from multi-source reference profiles. Individual photos have not been assigned; use Mars Trek and centroid coordinates.",
}.items():
    add("metadata", key=key, value=value)

db.executescript((WORK / "views.sql").read_text(encoding="utf-8"))
db.commit()

assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert db.execute("PRAGMA foreign_key_check").fetchall() == []
assert db.execute("SELECT COUNT(*) FROM craters").fetchone()[0] == 385049
assert db.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 1743
assert db.execute("SELECT COUNT(*) FROM footprints").fetchone()[0] > 0
assert db.execute("SELECT COUNT(*) FROM areas a WHERE NOT EXISTS (SELECT 1 FROM assets WHERE area_id=a.id)").fetchone()[0] == 0
assert db.execute("SELECT COUNT(*) FROM observations o JOIN samples s ON o.sample_id=s.id WHERE o.area_id<>s.area_id").fetchone()[0] == 0
assert db.execute("SELECT value FROM observations WHERE sample_id='jezero:Dourbes' AND parameter='MgO'").fetchone()[0] == 19.73
assert db.execute("SELECT COUNT(*) FROM science_observations WHERE source_id='gale_weather'").fetchone()[0] == 0


def rows(sql):
    return [dict(row) for row in db.execute(sql)]


coverage = rows("SELECT * FROM area_coverage ORDER BY CASE WHEN id IN ('jezero','gale','insight','phoenix') THEN 0 WHEN kind='terrain grid cell' THEN 2 ELSE 1 END,id")
details = rows("""
SELECT area_id,parameter,value,value_text,unit,uncertainty,uncertainty_kind,evidence,
       spatial_support,source_id,record_locator,note,baseline_m,depth_top_m,depth_bottom_m
FROM observations o WHERE sample_id IS NULL AND
 (window_id IS NULL OR EXISTS(SELECT 1 FROM time_windows w WHERE w.id=o.window_id AND w.kind<>'daily outreach report'))
ORDER BY area_id, id
""")
chemistry = rows("""
SELECT s.area_id,s.target,s.method,s.material,s.preparation_code,s.sol,s.quality,s.duplicate_status,
 MAX(CASE WHEN o.parameter='SiO2' THEN o.value END) AS SiO2,
 MAX(CASE WHEN o.parameter='MgO' THEN o.value END) AS MgO,
 MAX(CASE WHEN o.parameter='Al2O3' THEN o.value END) AS Al2O3,
 MAX(CASE WHEN o.parameter='FeO' THEN o.value END) AS FeO,
 MAX(CASE WHEN o.parameter='CaO' THEN o.value END) AS CaO,
 s.source_id,s.record_locator
FROM samples s JOIN observations o ON s.id=o.sample_id GROUP BY s.id
ORDER BY s.area_id,s.sol,s.target
""")
assets = rows("SELECT a.*,s.url FROM assets a JOIN sources s ON s.id=a.source_id ORDER BY a.area_id,a.kind,a.title")
sources = rows("SELECT * FROM sources ORDER BY id")
weather_preview = rows("""
SELECT w.sol,w.report_date,w.ls_deg,
 MAX(CASE WHEN o.parameter='air_temperature_min' THEN o.value END) AS air_min_c,
 MAX(CASE WHEN o.parameter='air_temperature_max' THEN o.value END) AS air_max_c,
 MAX(CASE WHEN o.parameter='ground_temperature_min' THEN o.value END) AS ground_min_c,
 MAX(CASE WHEN o.parameter='ground_temperature_max' THEN o.value END) AS ground_max_c,
 MAX(CASE WHEN o.parameter='daily_pressure_reported' THEN o.value END) AS pressure_pa,
 'gale_weather' AS source_id
FROM time_windows w LEFT JOIN observations o ON o.window_id=w.id
WHERE w.kind='daily outreach report' GROUP BY w.id ORDER BY w.sol DESC
""")
counts = dict(db.execute("""SELECT 'areas',COUNT(*) FROM areas UNION ALL
 SELECT 'terrain',COUNT(*) FROM footprints UNION ALL SELECT 'craters',COUNT(*) FROM craters UNION ALL
 SELECT 'samples',COUNT(*) FROM samples UNION ALL SELECT 'science',COUNT(*) FROM science_observations UNION ALL
 SELECT 'assets',COUNT(*) FROM assets UNION ALL SELECT 'sources',COUNT(*) FROM sources
""").fetchall())
export = dict(coverage=coverage,details=details,chemistry=chemistry,assets=assets,sources=sources,weather=weather_preview)
template = (WORK / "atlas.html").read_text(encoding="utf-8")
payload = json.dumps(export, ensure_ascii=False, separators=(",",":")).replace("</", "<\\/")
(OUT / "Mars Atlas.html").write_text(template.replace("__DATA_JSON__",payload)
    .replace("__COUNTS__", f"{counts['areas']:,} אזורים וחלונות • {counts['samples']:,} רשומות כימיה • {counts['craters']:,} מכתשים ב־SQLite"), encoding="utf-8")
db.close()
import shutil
shutil.copyfile(DB, OUT / "mars.sqlite")
print(counts)
