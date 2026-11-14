"""Build an offline analog picker and its auditable SQLite input."""
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
ARCHIVE = ROOT / "work/gemas.zip"
URL = "https://download.bgr.de/bgr/geochemie/GEMAS_ExtendedDataset/csv/ExtendedDataset_CSV.zip"
DOC = "https://umweltportal.niedersachsen.de/suche/detail?id=numis-metadaten-0554568e-c60f-4106-b099-839bb30f9c44"
HASH = "1867d519c4b27644a185369759438073ef5d0c427d12fd55d0d758d97d686587"
FIELDS = {
    "SiO2": ("סיליקה", "עוזרת להבחין בין סוגי חומר סלעי"),
    "TiO2": ("תחמוצת טיטניום", "מבדילה בין חומרים געשיים בהרכב שונה"),
    "MgO": ("תחמוצת מגנזיום", "מסמנת חומר עשיר במגנזיום"),
    "CaO": ("תחמוצת סידן", "מסמנת חומר עשיר בסידן"),
    "K2O": ("תחמוצת אשלגן", "עוזרת להבחין בין מקורות סלעיים"),
    "MnO": ("תחמוצת מנגן", "מוסיפה הבחנה בין דגימות דומות"),
}
TARGETS = {
    "mars": [("Gale · Portage", ["gale:10"]), ("Gusev", ["gusev:2"]),
             ("Meridiani Planum", ["meridiani:2"]), ("Gale · Bagnold Dunes", ["gale:157"])],
    "moon": [("Apollo 11", ["apollo11:soil16:line 6"]), ("Apollo 12", ["apollo12:soil16:line 12", "apollo12:soil16:line 18"]),
             ("Apollo 14", ["apollo14:soil16:line 24"]), ("Apollo 17", ["apollo17:soil16:line 54", "apollo17:soil16:line 60", "apollo17:soil16:line 66"])],
}

def archive_bytes():
    raw = ARCHIVE.read_bytes() if ARCHIVE.exists() else urlopen(URL, timeout=60).read()
    if hashlib.sha256(raw).hexdigest() != HASH:
        raise ValueError("GEMAS source hash mismatch")
    if not ARCHIVE.exists():
        ARCHIVE.write_bytes(raw)
    return raw

def earth_rows(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for group, prefix, depth in (("Ap", "1", 20), ("Gr", "2", 10)):
            ident = f"{prefix}1 GEMAS {group} - Ident.csv"
            oxides = f"{prefix}3b GEMAS {group} - WD-XRF Oxides.csv"
            sites = {r["ID"]: r for r in csv.DictReader(io.StringIO(z.read(ident).decode("latin1")))}
            for line, row in enumerate(csv.DictReader(io.StringIO(z.read(oxides).decode("latin1"))), 2):
                site = sites.get(row["ID"])
                if not site or not site["X_Coo"] or not site["Y_Coo"]:
                    continue
                vals = {k: float(row[k]) if row[k] else None for k in FIELDS}
                if any(v is None or not math.isfinite(v) or not 0 < v <= 100 for v in vals.values()):
                    continue
                lat, lon = float(site["Y_Coo"]), float(site["X_Coo"])
                if not (28 <= lat <= 72 and -32 <= lon <= 46):
                    continue
                yield dict(id=group + "-" + row["ID"], country=site["Country"], lat=lat, lon=lon,
                           group=group, depth=depth, values=vals, locator=f"{oxides}, line {line}")

def references():
    result = []
    for body, areas in TARGETS.items():
        with sqlite3.connect((OUT / f"{body}.sqlite").as_uri() + "?mode=ro", uri=True) as db:
            for i, (name, samples) in enumerate(areas):
                for sid in samples:
                    row = db.execute("""SELECT s.target,s.sol,s.method,s.preparation_code,s.record_locator,
                        src.url,s.quality,s.duplicate_status,s.material
                        FROM samples s JOIN sources src ON s.source_id=src.id WHERE s.id=?""", (sid,)).fetchone()
                    target, sol, method, prep, locator, url, quality, duplicate, material = row
                    assert quality != "Low" and duplicate != "Duplicate"
                    assert material in {"soil", "lunar regolith"}
                    values = dict(db.execute("SELECT parameter,value FROM observations WHERE sample_id=? AND unit='wt%'", (sid,)))
                    clean = {k: values[k] for k in FIELDS}
                    assert all(0 < v <= 100 for v in clean.values())
                    result.append(dict(body=body, area=f"{body}-{chr(65+i)}", name=name, id=sid, target=target,
                                       sol=sol, method=method, prep=prep, locator=locator, url=url, values=clean))
    return result

def main():
    earth = list(earth_rows(archive_bytes()))
    refs = references()
    assert len(earth) > 2000 and len({r["id"] for r in earth}) == len(earth)
    assert len({r["area"] for r in refs}) == 8
    scales = {k: statistics.quantiles([r["values"][k] for r in earth], n=4, method="inclusive")
              for k in FIELDS}
    iqr = {k: q[2]-q[0] for k,q in scales.items()}
    assert min(iqr.values()) > 0
    path = OUT / "analog-pilot.build.sqlite"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE features(id TEXT PRIMARY KEY, label TEXT, purpose TEXT, unit TEXT, earth_iqr REAL);
        CREATE TABLE records(id TEXT PRIMARY KEY, body TEXT, area TEXT, target TEXT, latitude REAL,
            longitude REAL, metadata_json TEXT NOT NULL);
        CREATE TABLE measurements(record_id TEXT REFERENCES records, feature_id TEXT REFERENCES features,
            value REAL NOT NULL, PRIMARY KEY(record_id,feature_id));
        CREATE TABLE sources(id TEXT PRIMARY KEY, url TEXT, sha256 TEXT);
        """)
        db.executemany("INSERT INTO features VALUES(?,?,?,?,?)",
                       [(k, *notes, "wt%", iqr[k]) for k,notes in FIELDS.items()])
        db.execute("INSERT INTO sources VALUES(?,?,?)", ("GEMAS", URL, HASH))
        for item in earth + refs:
            rec_id = item["id"]
            db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)", (
                rec_id,item.get("body","earth"),item.get("area"),item.get("target",rec_id),item.get("lat"),
                item.get("lon"),json.dumps({k:v for k,v in item.items() if k!="values"},ensure_ascii=False)))
            db.executemany("INSERT INTO measurements VALUES(?,?,?)",
                           [(rec_id,k,v) for k,v in item["values"].items()])
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()
    path.replace(OUT / "analog-pilot.sqlite")
    payload = json.dumps(dict(features=FIELDS, scales=iqr, earth=earth, refs=refs, source=DOC),
                         ensure_ascii=False, separators=(",",":")).replace("</","<\\/")
    html = (ROOT/"analog_pilot.html").read_text(encoding="utf-8")
    (OUT/"Analog Pilot.html").write_text(html.replace("__PILOT_DATA__",payload),encoding="utf-8")
    print(len(earth), len(refs), iqr)

if __name__ == "__main__":
    main()
