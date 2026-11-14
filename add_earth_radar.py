"""Measure archive RADARSAT pixel values at surveyed sites using published GCPs."""
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import GCPTransformer
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parent
BASE = "https://radarsat-r1-l1-cog.s3.ca-central-1.amazonaws.com/"

def main():
    keys = json.loads((ROOT/"earth-radar-scenes.json").read_text())
    db = sqlite3.connect(ROOT/"outputs/earth-comparison.sqlite")
    with db as transaction, rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="25"):
        transaction.execute("PRAGMA foreign_keys=ON")
        transaction.execute("""CREATE TABLE IF NOT EXISTS radar (
            site_id TEXT REFERENCES sites, scene TEXT, acquisition_source TEXT NOT NULL,
            source_url TEXT NOT NULL, pixel_row INTEGER NOT NULL, pixel_column INTEGER NOT NULL,
            valid_pixels INTEGER NOT NULL, median_dn REAL NOT NULL, pixel_sha256 TEXT NOT NULL,
            PRIMARY KEY(site_id,scene))""")
        sites = transaction.execute("SELECT id,latitude,longitude FROM sites").fetchall()
        observations = []
        for key in keys:
            with rasterio.open(BASE+key) as image:
                gcps, crs = image.gcps
                assert gcps and str(crs)=="EPSG:4326" and image.count==1
                assert not image.dtypes[0].startswith("complex")
                xs,ys = [g.x for g in gcps],[g.y for g in gcps]
                acquisition = image.tags()["CEOS_ACQUISITION_TIME"].strip()
                with GCPTransformer(gcps,tps=True) as project:
                    for site,lat,lon in sites:
                        if not min(xs)<lon<max(xs) or not min(ys)<lat<max(ys):
                            continue
                        row,col = project.rowcol(lon,lat)
                        if not (10<=row<image.height-10 and 10<=col<image.width-10):
                            continue
                        pixels = image.read(1,window=Window(col-10,row-10,21,21),masked=True).compressed()
                        valid = pixels[np.isfinite(pixels)&(pixels>0)]
                        if len(valid)>=400:
                            sha=hashlib.sha256(np.asarray(valid,dtype="<f8").tobytes()).hexdigest()
                            observations.append((site,key,acquisition,BASE+key,int(row),int(col),
                                                 len(valid),float(np.median(valid)),sha))
        assert observations
        transaction.execute("DELETE FROM radar")
        transaction.executemany("INSERT INTO radar VALUES(?,?,?,?,?,?,?,?,?)",observations)
        assert not transaction.execute("PRAGMA foreign_key_check").fetchall()
        assert transaction.execute("PRAGMA integrity_check").fetchone()==("ok",)
        print("RADARSAT rows",len(observations))
    db.close()

if __name__=="__main__":
    main()
