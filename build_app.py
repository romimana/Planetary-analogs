"""Build the standalone Planetary Analogs demo from the published SQLite snapshot."""
import base64
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from package_ml import CHEMISTRY, TERRAIN
NEW = "largest_gentle_patch_fraction"

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app"
FIELDS = (*CHEMISTRY, *TERRAIN, NEW)

def json_script(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")

def verified_snapshot(path):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = json.loads(path.with_suffix(".json").read_text())["sha256"]
    if actual != expected:
        raise ValueError(f"{path.name} does not match its published checksum")
    return actual

def add_expansion(result):
    path = ROOT / "data/earth-expansion.sqlite"
    sha = verified_snapshot(path)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        weather = {}
        for site, stamp, value in db.execute("SELECT location_id,utc,horizontal_projection FROM solar_scenarios"):
            weather.setdefault(site, {})[stamp] = value
        fields = ",".join(FIELDS)
        for record in db.execute(f"""SELECT id,site_id,region,latitude,longitude,material,source_id,
            chemistry_source_url,geology_unit,geology_description,geology_product,geology_url,geology_locator,{fields}
            FROM earth_model_profiles ORDER BY id"""):
            row = dict(record)
            row["values"] = [row.pop(name) for name in FIELDS]
            row["solar"] = [round(weather[row["site_id"]][stamp], 7) for stamp in result["earth"]["times"]]
            result["earth"]["rows"].append(row)
    return sha


def terrain_sites(times):
    path = ROOT / "data/earth-terrain-sites.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    if len(source["rows"]) != source["report"]["terrain_passed"]:
        raise ValueError("Terrain site count differs from its manifest")
    for row in source["rows"]:
        geology = row.pop("geology")
        row.update(zip(("geology_unit", "geology_description", "geology_product", "geology_url",
                        "geology_sha256", "geology_locator"), geology or [None]*6, strict=True))
        row.update(id=row["site_id"], source_id="Copernicus GLO-30 / ESA WorldCover",
                   material="Terrain window · chemistry unavailable")
        row["values"] = [row.pop(name, None) for name in FIELDS]
        row["solar"] = [row["solar"][stamp] for stamp in times]
    return source["rows"]

def read_payload():
    path = ROOT / "data/ml-enriched.sqlite"
    actual = verified_snapshot(path)
    result = {}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        fields = ",".join(f"p.{name}" for name in FIELDS)
        for body in ("earth", "mars", "moon"):
            if body == "earth":
                query = f"""SELECT p.id,p.site_id,p.region,p.latitude,p.longitude,p.material,
                    p.geology_unit,p.geology_description,p.geology_product,p.geology_url,p.geology_locator,p.source_id,{fields}
                    FROM earth_model_profiles p ORDER BY p.id"""
            else:
                query = f"""SELECT p.id,p.area,p.latitude,p.longitude_e AS longitude,p.material,
                    p.geology_unit,p.geology_description,p.geology_product,p.geology_url,p.geology_locator,p.location_role,
                    s.name,s.provenance_json,{fields}
                    FROM {body}_model_profiles p JOIN planet_samples s USING(id) ORDER BY p.id"""
            rows = [dict(row) for row in db.execute(query)]
            times = [stamp for stamp, in db.execute("SELECT DISTINCT utc FROM solar_scenarios WHERE body=? ORDER BY 1",
                                                    (body,))]
            solar = {}
            for location, stamp, power in db.execute("""SELECT location_id,utc,horizontal_projection
                FROM solar_scenarios WHERE body=? ORDER BY location_id,utc""", (body,)):
                solar.setdefault(location, {})[stamp] = power
            for row in rows:
                if body != "earth":
                    provenance = json.loads(row.pop("provenance_json"))
                    row["sample"] = {key: provenance.get(key) for key in
                                     ("sol", "preparation", "chemistry_url", "chemistry_locator", "location_source")}
                row["values"] = [row.pop(name) for name in FIELDS]
                row["solar"] = [round(solar[row.get("site_id", row["id"])][stamp], 7) for stamp in times]
            result[body] = {"rows": rows, "times": times}
        result["radar"] = {
            site: {"scene": scene, "source": url}
            for site, scene, url in db.execute("SELECT site_id,scene,source_url FROM earth_radar ORDER BY scene")
        }
    expansion_sha = add_expansion(result)
    result["earth"]["rows"].extend(terrain_sites(result["earth"]["times"]))
    irish_bedrock = json.loads((ROOT / "data/irish-bedrock.json").read_text(encoding="utf-8"))
    if irish_bedrock["earthExpansionSha256"] != expansion_sha:
        raise ValueError("Irish bedrock GIS join refers to a different Earth expansion snapshot")
    rubric = {}
    for line in (ROOT / "GEOLOGY_MATCHING.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and len(line.split("|")) == 6:
            code, _, moon, mars = [part.strip() for part in line.split("|")[1:-1]]
            if len(code) == 2 and code.isalpha():
                rubric[code] = [float(moon), float(mars)]
    if len(rubric) != 13:
        raise ValueError("Expected 13 documented map-unit penalties")
    return {**result, "rubric": rubric, "sha256": actual, "expansionSha256": expansion_sha,
            "irishBedrock": irish_bedrock}

def main():
    source = (APP / "template.html").read_text(encoding="utf-8")
    land = json.loads((APP / "assets/land.geojson").read_text(encoding="utf-8"))
    payload = read_payload()
    payload["land"] = [feature["geometry"] for feature in land["features"]]
    photo = base64.b64encode((APP / "assets/mars.jpg").read_bytes()).decode("ascii")
    replacements = {
        "/*APP_STYLE*/": (APP / "style.css").read_text(encoding="utf-8"),
        "/*LEAFLET_STYLE*/": (APP / "assets/leaflet.css").read_text(encoding="utf-8"),
        "/*LEAFLET_SCRIPT*/": (APP / "assets/leaflet.js").read_text(encoding="utf-8").split("//# sourceMappingURL=")[0],
        "/*APP_DATA*/": json_script(payload),
        "/*RANKING_ENGINE*/": (APP / "ranking.js").read_text(encoding="utf-8"),
        "/*APP_SCRIPT*/": (APP / "app.js").read_text(encoding="utf-8"),
        "MARS_PHOTO_DATA": f"data:image/jpeg;base64,{photo}",
    }
    for marker, replacement in replacements.items():
        if source.count(marker) != 1:
            raise ValueError(f"Unexpected template marker count for {marker}")
        source = source.replace(marker, replacement)
    (APP / "index.html").write_text(source, encoding="utf-8", newline="\n")

if __name__ == "__main__":
    main()
