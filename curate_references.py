"""Export traceable planetary soil reference records before similarity scoring."""
import csv
import io
import json
import math
import sqlite3
import zipfile
from pathlib import Path

from build_pilot import FIELDS, OUT, archive_bytes, earth_rows

def planetary_rows(body):
    path = OUT / f"{body}.sqlite"
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        samples = db.execute("""
            SELECT s.*, a.body, a.name AS area_name, a.latitude_deg AS area_latitude,
                a.longitude_e_deg AS area_longitude, src.url AS source_url
            FROM samples s JOIN areas a ON a.id=s.area_id JOIN sources src ON src.id=s.source_id
            WHERE s.material IN ('soil','lunar regolith')
            ORDER BY s.area_id, s.sol, s.id
        """)
        for sample in samples:
            src, prep = sample["source_id"], sample["preparation_code"]
            if body == "mars" and (prep not in {"SU", "SD"} or sample["quality"] or sample["duplicate_status"]):
                continue
            if body == "moon" and (src != "soil16" or prep != "bulk"):
                continue
            observed = {r["parameter"]: dict(r) for r in db.execute("""
                SELECT parameter,value,unit,uncertainty,uncertainty_kind,record_locator
                FROM observations WHERE sample_id=?
            """, (sample["id"],))}
            if any(k not in observed or observed[k]["unit"] != "wt%" or
                   not math.isfinite(observed[k]["value"]) or not 0 < observed[k]["value"] <= 100
                   for k in FIELDS):
                continue
            if body == "mars" and any(
                observed[k]["uncertainty"] is None or not math.isfinite(observed[k]["uncertainty"])
                or not 0 < observed[k]["uncertainty"] < observed[k]["value"] for k in FIELDS
            ):
                continue
            if src == "mer" and (sample["integration_hours"] < 1 or sample["instrument_norm"] < 50):
                continue
            item = dict(sample)
            item["measurements"] = {k: observed[k] for k in FIELDS}
            item["location_role"] = ("mission anchor plus original rover coordinates pending CRS validation"
                                     if src == "gale_apxs" else "mission anchor")
            item["cross_method_validation"] = "pending"
            yield item

def validate_earth():
    raw = archive_bytes()
    rows = list(earth_rows(raw))
    selected = set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for group, prefix in (("Ap", "1"), ("Gr", "2")):
            templates = [n for n in archive.namelist()
                         if n.startswith(prefix) and "WD-XRF DL's" in n]
            assert len(templates) == 1
            source = io.StringIO(archive.read(templates[0]).decode("latin1"))
            limits = {r["Parameter"]: float(r["LDL"]) for r in csv.DictReader(source)
                      if r["Unit"] == "wt%" and r["Parameter"] in FIELDS}
            assert set(limits) == set(FIELDS)
            selected.update(r["id"] for r in rows if r["group"] == group and
                            all(r["values"][k] >= limits[k] for k in FIELDS))
    return {"pilot_rows": len(rows), "above_published_limits": len(selected),
            "distinct_locations_above_limits": len({(r["lat"], r["lon"]) for r in rows if r["id"] in selected})}

def main():
    refs = {body: list(planetary_rows(body)) for body in ("mars", "moon")}
    assert all(refs.values())
    counts = {body: {area: sum(row["area_id"] == area for row in items)
                     for area in sorted({row["area_id"] for row in items})}
              for body, items in refs.items()}
    earth = validate_earth()
    for body, items in refs.items():
        content = {"features": {k: {"label_he": label, "purpose_he": use, "unit": "wt%"}
                                for k, (label, use) in FIELDS.items()}, "records": items}
        (OUT / f"{body}-soil-reference.json").write_text(json.dumps(
            content, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"references_by_site": counts, "earth_audit": earth}, indent=2))

if __name__ == "__main__":
    main()
