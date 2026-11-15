"""Package GSI's CC BY GEMAS release with independently calculated GIS context."""
import argparse
import json
import math
from urllib.parse import urlencode

from build_earth import OUT
from build_earth_expansion import ROOT, build, make_row, pinned
from build_terrain_sites import locate_regions
from enrich_terrain import earth_metrics

BASE = ("https://gsi.geodata.gov.ie/server/rest/services/Geochemistry/"
        "IE_GSI_GEMAS_Geochemistry_Agricultural_Grazing_Land_Soil_EU_WGS84/MapServer")
FIELDS = ("SIO2", "TIO2", "MGO", "CAO", "K2O", "MNO")
LIMITS = (.1, .001, .01, .005, .005, .001)
# Conflicting values in the GSI and BGR releases exceed reporting precision.
DISPUTED = {"Ap-3232", "Ap-3233", "Ap-3459", "Ap-3461", "Ap-3539", "Ap-3649",
            "Ap-3869", "Ap-4068", "Ap-4588", "Ap-4589", "Ap-4844", "Ap-5236"}
LAYERS = {
    "Ap": (190, "da3c130730191557ceaf83ee42c9993131b7c8825fd9df26b1a92a1f5d74f65c", 2113, "Arable soil 0–20 cm; XRF"),
    "Gr": (228, "36e672eb87569caa8da9979ed49088ffeb804606771e718478d368c371e01f68", 2024, "Grazing soil 0–10 cm; XRF"),
}


def source_records():
    params = urlencode(dict(where="1=1", outFields="OBJECTID,ID,COUNTRY,TYPE_," + ",".join(FIELDS),
                            returnGeometry="true", outSR="4326", f="json", orderByFields="OBJECTID"))
    records = []
    for group, (layer, sha, count, material) in LAYERS.items():
        spec = (f"gsi-gemas-{group}.json", f"{BASE}/{layer}/query?{params}", sha)
        document = json.loads(pinned(spec))
        features = document["features"]
        if len(features) != count or document.get("exceededTransferLimit") or document["spatialReference"]["wkid"] != 4326:
            raise ValueError(f"Incomplete or unexpected GEMAS layer {layer}")
        for feature in features:
            attrs, point = feature["attributes"], feature["geometry"]
            identifier = attrs["ID"]
            if attrs["TYPE_"] != group or identifier is None or int(identifier) != identifier:
                continue
            sample_id = f"{group}-{int(identifier)}"
            if sample_id in DISPUTED:
                continue
            values = [attrs[field] for field in FIELDS]
            if any(v is None or not math.isfinite(v) or v < limit for v, limit in zip(values, LIMITS, strict=True)):
                continue
            lat, lon = (round(point[key], 4) for key in ("y", "x"))
            records.append(dict(latitude=lat, longitude=lon, id=sample_id, values=values,
                                material=material, source=spec, locator=f"Layer {layer}, OBJECTID {attrs['OBJECTID']}"))
    locate_regions(records)
    rows = [make_row(r["id"], r["region"], "GSI-GEMAS", r["material"], r["latitude"], r["longitude"],
                     r["values"], r["source"], r["locator"]) for r in records]
    rows = sorted(row for row in rows if row is not None)
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError("Duplicate GEMAS sample ID")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--terrain-cache", action="store_true",
                        help="Reuse locally archived NASADEM windows at exactly matching four-decimal coordinates")
    args = parser.parse_args()
    records = source_records()
    sites = {row[1]: (row[5], row[6]) for row in records}
    if args.terrain_cache:
        cache = json.loads((OUT / "terrain-local.json").read_text(encoding="utf-8"))
        terrain = {site: cache[key] for site, (lat, lon) in sites.items()
                   if (key := f"{lat:.4f}/{lon:.4f}") in cache}
    else:
        terrain = earth_metrics([(site, *coords) for site, coords in sorted(sites.items())])
    print(f"{len(records)} published chemistry records pass screening; {len(terrain)} sites have GIS terrain", flush=True)
    build(records, terrain, ROOT / "data/gemas-public.sqlite")


if __name__ == "__main__":
    main()
