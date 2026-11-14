"""Export normalized comparison tables from the rebuilt planetary context."""
import json
import math
import sqlite3

from build_context import OUT, RADII, distance
from build_pilot import FIELDS

TERRAIN = ("slope_median_deg", "slope_p90_deg", "slope_over_10_deg_fraction",
           "relief_p90_p10_m", "local_roughness_rms_m")
MEASURES = ("air_temperature_k", "pressure_pa", "ground_brightness_k")

def scenario(window):
    if "sol" in window:
        key = ("rems", window["url"], window["sol"], window["local_solar_hour"])
        values = {k: window["values"].get(k, {}).get("median") for k in MEASURES}
        values["lunar_surface_bolometric_k"] = None
        anchor = window["waypoint_coordinates"]
    else:
        key = ("diviner", window["url"], window["source_record"])
        values = dict.fromkeys(MEASURES)
        values["lunar_surface_bolometric_k"] = window["surface_brightness_k"]
        anchor = window["center"]
    return json.dumps(key, separators=(",", ":")), values, anchor

def main():
    source = OUT / "planetary-context.sqlite"
    temporary = OUT / "planetary-comparison.build.sqlite"
    temporary.unlink(missing_ok=True)
    chemistry_columns = ", ".join(f"{k.lower()}_wt_pct REAL NOT NULL" for k in FIELDS)
    terrain_columns = ", ".join(f"{k} REAL NOT NULL" for k in TERRAIN)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as raw, sqlite3.connect(temporary) as db:
        db.executescript(f"""
        PRAGMA foreign_keys=ON;
        CREATE TABLE samples(id TEXT PRIMARY KEY, body TEXT NOT NULL, area TEXT NOT NULL, name TEXT NOT NULL,
            latitude REAL NOT NULL, longitude_e REAL NOT NULL, location_role TEXT NOT NULL,
            material TEXT NOT NULL, comparison_status TEXT NOT NULL, {chemistry_columns},
            {terrain_columns}, provenance_json TEXT NOT NULL);
        CREATE TABLE scenarios(id TEXT PRIMARY KEY, window_label TEXT NOT NULL, local_solar_hour REAL NOT NULL,
            source_url TEXT NOT NULL, air_temperature_k REAL, pressure_pa REAL, ground_brightness_k REAL,
            lunar_surface_bolometric_k REAL, provenance_json TEXT NOT NULL);
        CREATE TABLE sample_scenarios(sample_id TEXT REFERENCES samples, scenario_id TEXT REFERENCES scenarios,
            distance_m REAL NOT NULL, chemistry_sol_delta INTEGER, PRIMARY KEY(sample_id,scenario_id));
        CREATE VIEW chemistry_inputs AS SELECT * FROM samples
            WHERE comparison_status <> 'chemistry_hold';
        CREATE VIEW mars_atmosphere_inputs AS SELECT s.*, l.scenario_id,l.distance_m,l.chemistry_sol_delta,
            w.window_label,w.local_solar_hour,w.source_url,w.air_temperature_k,w.pressure_pa
            FROM samples s JOIN sample_scenarios l ON l.sample_id=s.id JOIN scenarios w ON w.id=l.scenario_id
            WHERE s.body='mars' AND s.comparison_status='rover_or_station'
              AND w.air_temperature_k IS NOT NULL AND w.pressure_pa IS NOT NULL;
        CREATE VIEW mars_surface_inputs AS SELECT a.*,w.ground_brightness_k
            FROM mars_atmosphere_inputs a JOIN scenarios w ON w.id=a.scenario_id
            WHERE w.ground_brightness_k IS NOT NULL;
        CREATE VIEW moon_thermal_inputs AS SELECT s.*,l.scenario_id,l.distance_m,
            w.window_label,w.local_solar_hour,w.source_url,w.lunar_surface_bolometric_k
            FROM samples s JOIN sample_scenarios l ON l.sample_id=s.id JOIN scenarios w ON w.id=l.scenario_id
            WHERE s.body='moon' AND s.comparison_status='rover_or_station'
              AND w.lunar_surface_bolometric_k IS NOT NULL;
        """)
        assert raw.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not raw.execute("PRAGMA foreign_key_check").fetchall()
        records = {}
        for body in RADII:
            data = json.loads((OUT / f"{body}-soil-reference.json").read_text(encoding="utf-8"))
            records.update({r["id"]: r for r in data["records"]})
        points = {}
        for (blob,) in raw.execute("SELECT profile_json FROM profiles ORDER BY id"):
            r = json.loads(blob)
            ref = records[r["id"]]
            assert r["chemistry"] == ref["measurements"]
            assert (r["chemistry_url"], r["chemistry_locator"]) == (ref["source_url"], ref["record_locator"])
            t = r["terrain"]["common_500m"]
            assert t["pixels"] == 100 and t["baseline_m"] == 1000
            points[r["id"]] = (r["body"], (r["lat"], r["lon"]))
            status = {"linked_at_station_or_rover_scale": "rover_or_station",
                      "linked_at_mission_scale": "mission_context",
                      "missing_environment_or_chemistry_screen": "chemistry_and_terrain"}[r["profile_status"]]
            if r["chemistry_status"].startswith("hold"):
                status = "chemistry_hold"
            fields = (r["id"], r["body"], r["area"], r["name"], r["lat"], r["lon"], r["location_role"],
                      r["material"], status, *(r["chemistry"][k]["value"] for k in FIELDS),
                      *(t[k] for k in TERRAIN), blob)
            db.execute("INSERT INTO samples VALUES (" + ",".join("?" for _ in fields) + ")", fields)
        assert set(points) == set(records)
        seen = {}
        for sample_id, reported, blob in raw.execute(
            "SELECT profile_id,distance_m,data_json FROM environment_windows ORDER BY profile_id,window_id"):
            w = json.loads(blob)
            sid, values, anchor = scenario(w)
            body, point = points[sample_id]
            assert math.isclose(reported, distance(point, anchor, RADII[body]), abs_tol=1e-8)
            assert all(x is None or math.isfinite(x) for x in values.values())
            provenance = {k: v for k, v in w.items() if k not in {"distance_m", "chemistry_sol_delta"}}
            fields = (sid, w["window"], w["local_solar_hour"], w["url"], *values.values(),
                      json.dumps(provenance, sort_keys=True, ensure_ascii=False))
            if sid not in seen:
                db.execute("INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?)", fields)
                seen[sid] = fields
            assert seen[sid] == fields
            db.execute("INSERT INTO sample_scenarios VALUES (?,?,?,?)",
                       (sample_id, sid, reported, w.get("chemistry_sol_delta")))
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        for name in ("samples", "scenarios", "sample_scenarios", "chemistry_inputs", "mars_atmosphere_inputs",
                     "mars_surface_inputs", "moon_thermal_inputs"):
            print(name, db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
    db.close()
    temporary.replace(OUT / "planetary-comparison.sqlite")

if __name__ == "__main__":
    main()
