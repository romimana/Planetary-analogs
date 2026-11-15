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

def read_payload():
    path = ROOT / "data/ml-enriched.sqlite"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = json.loads(path.with_suffix(".json").read_text())["sha256"]
    if actual != expected:
        raise ValueError("The database does not match its published checksum")
    result = {}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        fields = ",".join(f"p.{name}" for name in FIELDS)
        for body in ("earth", "mars", "moon"):
            if body == "earth":
                query = f"""SELECT p.id,p.site_id,p.region,p.latitude,p.longitude,p.material,
                    p.geology_unit,p.geology_description,p.geology_url,p.source_id,{fields}
                    FROM earth_model_profiles p ORDER BY p.id"""
            else:
                query = f"""SELECT p.id,p.area,p.latitude,p.longitude_e AS longitude,p.material,
                    p.geology_unit,p.geology_description,p.geology_url,p.location_role,s.name,{fields}
                    FROM {body}_model_profiles p JOIN planet_samples s USING(id) ORDER BY p.id"""
            rows = [dict(row) for row in db.execute(query)]
            times = [stamp for stamp, in db.execute("SELECT DISTINCT utc FROM solar_scenarios WHERE body=? ORDER BY 1",
                                                    (body,))]
            solar = {}
            for location, stamp, power in db.execute("""SELECT location_id,utc,horizontal_projection
                FROM solar_scenarios WHERE body=? ORDER BY location_id,utc""", (body,)):
                solar.setdefault(location, {})[stamp] = power
            for row in rows:
                row["values"] = [row.pop(name) for name in FIELDS]
                row["solar"] = [round(solar[row.get("site_id", row["id"])][stamp], 7) for stamp in times]
            result[body] = {"rows": rows, "times": times}
        result["radar"] = {
            site: {"scene": scene, "source": url}
            for site, scene, url in db.execute("SELECT site_id,scene,source_url FROM earth_radar ORDER BY scene")
        }
    rubric = {}
    for line in (ROOT / "GEOLOGY_MATCHING.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and len(line.split("|")) == 6:
            code, _, moon, mars = [part.strip() for part in line.split("|")[1:-1]]
            if len(code) == 2 and code.isalpha():
                rubric[code] = [float(moon), float(mars)]
    if len(rubric) != 13:
        raise ValueError("Expected 13 documented map-unit penalties")
    return {**result, "rubric": rubric, "sha256": actual}

def main():
    source = (APP / "template.html").read_text(encoding="utf-8")
    land = json.loads((APP / "assets/land.geojson").read_text(encoding="utf-8"))
    payload = read_payload()
    payload["land"] = [feature["geometry"] for feature in land["features"]]
    photo = base64.b64encode((APP / "assets/mars.jpg").read_bytes()).decode("ascii")
    replacements = {
        "/*APP_STYLE*/": (APP / "style.css").read_text(encoding="utf-8"),
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
