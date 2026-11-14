"""Read authenticated MOD11A1 granules and join valid pixels to survey sites."""
import hashlib
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

from pyhdf.SD import SD, SDC

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "work/earth"

def pixel(lat, lon):
    y = (90 - lat) / 10
    x = (180 + lon * math.cos(math.radians(lat))) / 10
    h, v = math.floor(x), math.floor(y)
    return f"h{h:02}v{v:02}", int((y-v)*1200), int((x-h)*1200)

def main():
    entries = json.loads((ROOT / "modis-granules.json").read_text(encoding="utf-8"))
    paths = [(entry, CACHE / entry["file"]) for entry in entries]
    missing = [path.name for _, path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} NASA granules are missing. First missing file: {missing[0]}")
    db = sqlite3.connect(ROOT/"outputs/earth-comparison.sqlite")
    sites = {}
    for site, lat, lon in db.execute("SELECT id,latitude,longitude FROM sites"):
        tile, row, col = pixel(lat, lon)
        sites.setdefault(tile, []).append((site,row,col))
    with db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN")
        db.execute("DROP TABLE IF EXISTS modis_temperature")
        db.execute("""CREATE TABLE IF NOT EXISTS modis_temperature (
            site_id TEXT NOT NULL REFERENCES sites, granule_id TEXT NOT NULL, date TEXT NOT NULL,
            pass TEXT NOT NULL, row INTEGER NOT NULL, col INTEGER NOT NULL, temperature_k REAL NOT NULL,
            local_observation_hour REAL NOT NULL, quality_code INTEGER NOT NULL,
            sha256 TEXT NOT NULL, PRIMARY KEY(site_id,granule_id,pass))""")
        for entry,path in paths:
            _,day,tile,*_ = path.name.split(".")
            date = datetime.strptime(day[1:],"%Y%j").date().isoformat()
            with path.open("rb") as file:
                sha = hashlib.file_digest(file,"sha256").hexdigest()
            if sha != entry["sha256"]:
                raise ValueError(f"SHA-256 mismatch for {path.name}")
            dataset = SD(str(path), SDC.READ)
            try:
                for period in ("Day","Night"):
                    temp = dataset.select(f"LST_{period}_1km").get()
                    qc = dataset.select(f"QC_{period}").get()
                    times = dataset.select(f"{period}_view_time").get()
                    assert temp.shape == qc.shape == times.shape == (1200,1200)
                    rows=[]
                    for site,r,c in sites[tile]:
                        flags, value, hour = int(qc[r,c]), int(temp[r,c]), int(times[r,c])
                        if flags & 3 or (flags >> 6) != 0 or not 7500 <= value <= 65535 or not 0 <= hour < 240:
                            continue
                        rows.append((site,entry["id"],date,period,r,c,value*.02,hour*.1,flags,sha))
                    db.executemany("INSERT INTO modis_temperature VALUES(?,?,?,?,?,?,?,?,?,?)",rows)
            finally:
                dataset.end()
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        print(db.execute("SELECT COUNT(*),COUNT(DISTINCT site_id) FROM modis_temperature").fetchone())
    db.close()

if __name__=="__main__":
    main()
