"""Join Irish chemistry sites to the GSI bedrock polygons for source inspection."""
import hashlib
import io
import json
import sqlite3
from contextlib import closing
from zipfile import ZipFile

import shapefile
from pyproj import CRS, Transformer
from shapely import Point, STRtree, box, make_valid
from shapely.geometry import shape

from build_earth_expansion import ROOT, pinned

SOURCE = (
    "gsi-bedrock-100k.zip",
    "https://gsi.geodata.gov.ie/downloads/Bedrock/Data/IE_GSI_Bedrock_Geology_Datasets_100K_IE26_ITM.zip",
    "d5bc44224c5d57ddc712c2e04f14683ee214179322913d88162ec0f048933629",
)
LAYER = "IE_GSI_Bedrock_Geology_100K_IE26_ITM_MS"
OUTPUT = ROOT / "data/irish-bedrock.json"


def read_sites():
    db_path = ROOT / "data/earth-expansion.sqlite"
    digest = hashlib.sha256(db_path.read_bytes()).hexdigest()
    if digest != json.loads(db_path.with_suffix(".json").read_text())["sha256"]:
        raise ValueError("Earth expansion checksum mismatch")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as db:
        sites = db.execute("""SELECT DISTINCT site_id,longitude,latitude FROM earth_samples
                              WHERE region='IRL' ORDER BY site_id""").fetchall()
    return sites, digest


def join(sites, data):
    with ZipFile(io.BytesIO(data)) as archive:
        files = {ext: archive.read(f"{LAYER}.{ext}") for ext in ("dbf", "shp", "shx", "prj")}
    crs = CRS.from_wkt(files.pop("prj").decode("ascii"))
    if crs.to_epsg() != 2157:
        raise ValueError("Expected Irish Transverse Mercator")
    transform = Transformer.from_crs(4326, crs, always_xy=True)
    points = STRtree([Point(transform.transform(lon, lat)) for _, lon, lat in sites])
    matches = {}
    with shapefile.Reader(**{ext: io.BytesIO(content) for ext, content in files.items()}, encoding="utf-8") as layer:
        for entry in layer.iterShapeRecords():
            if not len(points.query(box(*entry.shape.bbox))):
                continue
            polygon = shape(entry.shape.__geo_interface__)
            if not polygon.is_valid:
                polygon = make_valid(polygon)
            for index in points.query(polygon, predicate="contains"):
                props = entry.record.as_dict()
                matches.setdefault(sites[index][0], []).append([
                    entry.record.oid, props["NEWCODE"], props["STRATCODE"], props["LITHCODE"],
                    props["UNIT_NAME"], props["DESCRIPT"],
                ])
    return {site: entries[0] for site, entries in sorted(matches.items()) if len(entries) == 1}


def main():
    sites, site_sha = read_sites()
    rows = join(sites, pinned(SOURCE))
    if not rows:
        raise ValueError("No unambiguous bedrock joins")
    result = {"product": "GSI Bedrock Geology 1:100,000", "url": SOURCE[1], "sha256": SOURCE[2],
              "earthExpansionSha256": site_sha, "layer": LAYER, "siteCount": len(sites),
              "columns": ["polygon_record", "unit_id", "stratigraphy", "lithology_code", "unit_name", "description"],
              "rows": rows}
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(rows):,} of {len(sites):,} Irish sites matched one bedrock polygon")


if __name__ == "__main__":
    main()
