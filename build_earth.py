"""Build an Earth GIS comparison snapshot from versioned public inputs."""
import csv
import hashlib
import io
import json
import math
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
from PIL import Image
from build_context import terrain_metrics, distance
from build_pilot import FIELDS, OUT, archive_bytes, earth_rows, URL as GEMAS_URL

CACHE = Path(__file__).resolve().parent / "work/earth"
DEM = "https://opentopography.s3.sdsc.edu/raster/NASADEM/NASADEM_be/"
AU = "https://d28rz98at9flks.cloudfront.net/82869/Rec2011_020_110706.csv"
POWER = "https://power.larc.nasa.gov/api/temporal/hourly/point?"
RADIUS = 6371008.8
DAYS = ("20240115", "20240415", "20240715", "20241015")
# Conversion to oxide-equivalent mass uses the formula mass divided by the elemental mass in it.
O = 15.999
OXIDES = {"SiO2": ("Si",28.085,2), "TiO2": ("Ti",47.867,2), "MgO": ("Mg",24.305,1),
          "CaO": ("Ca",40.078,1), "K2O": ("K",2*39.0983,1), "MnO": ("Mn",54.938044,1)}
METRICS = ("slope_median_deg", "slope_p90_deg", "slope_over_10_deg_fraction",
           "relief_p90_p10_m", "local_roughness_rms_m")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def fetch(name, url):
    path = CACHE / name
    if not path.exists():
        with urlopen(url,timeout=30) as response:
            data = response.read()
        tmp = path.with_suffix(path.suffix+".part")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path.read_bytes()

def australia(raw):
    lines = csv.reader(io.StringIO(raw.decode("latin1")))
    for _ in range(11):
        next(lines)
    header = next(lines)
    specs = {}
    for oxide,(symbol,mass,oxygen) in OXIDES.items():
        idx, = [i for i,k in enumerate(header) if k.startswith(symbol+" XRF mg/kg ")]
        specs[oxide] = (idx,float(header[idx].split()[-1]),(mass+O*oxygen)/mass)
    for line,row in enumerate(lines,13):
        if not row or not row[0].isdigit() or row[8:10]!=["<2 mm","TOS"] or row[5].strip():
            continue
        values = {}
        raw_mgkg = {}
        for key,(idx,limit,factor) in specs.items():
            try:
                v=float(row[idx])
            except ValueError:
                break
            if not math.isfinite(v) or v < limit:
                break
            raw_mgkg[header[idx]]=v
            values[key]=v*factor/10000
        if len(values)==len(FIELDS) and sum(values.values()) <= 100:
            yield dict(id="NGSA:"+row[7],lat=float(row[2]),lon=float(row[3]),country="AUS",depth=10,
                       group="catchment outlet sediment",values=values,locator=f"CSV line {line}; site {row[0]}",
                       raw_mgkg=raw_mgkg, original_crs="GDA94", date_original=row[1])

def tile(lat,lon):
    return f"{'n' if lat>=0 else 's'}{abs(lat):02d}{'e' if lon>=0 else 'w'}{abs(lon):03d}"

def envelope(lat, lon):
    deg = 180 / (math.pi * RADIUS)
    return (lon-2500*deg/math.cos(math.radians(lat)),lat-2500*deg,
            lon+2500*deg/math.cos(math.radians(lat)),lat+2500*deg)

def terrain_batch(key, sites):
    name=tile(*key)
    url=DEM+f"NASADEM_HGT_{name}.tif"
    try:
        raw=fetch(name+".tif",url)
        with Image.open(io.BytesIO(raw)) as im:
            assert im.size==(3601,3601)
            dx,dy,_=im.tag_v2[33550]
            _,_,_,west,north,_=im.tag_v2[33922]
            keys=dict((entry[0],entry[-1]) for entry in np.array(im.tag_v2[34735][4:]).reshape(-1,4))
            assert keys[1025]==2 and keys[2048]==4326
            assert (west,north)==(key[1],key[0]+1) and dx==dy==1/3600
            nodata=int(im.tag_v2[42113])
            pixels=np.asarray(im)
    except (OSError,ValueError,HTTPError) as error:
        print("DEM unavailable",name,str(error),flush=True)
        return []
    sha=digest(raw)
    results=[]
    for site,lat,lon in sites:
        x0,y0,x1,y1=envelope(lat,lon)
        if not (west<=x0<x1<=west+1 and north-1<=y0<y1<=north):
            continue
        c0,c1=math.ceil((x0-west)/dx),math.ceil((x1-west)/dx)
        r0,r1=math.ceil((north-y1)/dy),math.ceil((north-y0)/dy)
        c=np.arange(c0,c1)
        r=np.arange(r0,r1)
        x=(c*dx+west-lon)*math.pi/180*RADIUS*math.cos(math.radians(lat))
        y=(r*dy-north+lat)*math.pi/180*RADIUS
        bins=np.floor((y[:,None]+2500)/500).astype(int).clip(0,9)*10+np.floor((x[None,:]+2500)/500).astype(int).clip(0,9)
        patch=pixels[r0:r1,c0:c1]
        valid=patch!=nodata
        counts=np.bincount(bins[valid],minlength=100)
        expected=np.bincount(bins.ravel(),minlength=100)
        if np.any(counts==0) or np.any(counts<.95*expected):
            continue
        grid=(np.bincount(bins[valid],weights=patch[valid],minlength=100)/counts).reshape(10,10)
        results.append((site,*terrain_metrics(grid,500,500).values(),url,sha,f"rows {r0}:{r1}; cols {c0}:{c1}",
                        int(counts.min()),int(counts.max())))
    return results

def weather_cell(key):
    lat,lon=key
    results=[]
    for day in DAYS:
        url=POWER+urlencode(dict(parameters="T2M,TS,PS",community="RE",latitude=lat,longitude=lon,
                                 start=day,end=day,format="JSON",**{"time-standard":"UTC"}))
        try:
            raw=fetch(f"power-{lat}-{lon}-{day}.json",url)
            data=json.loads(raw)
            assert data["header"]["time_standard"]=="UTC"
            assert data["header"]["sources"]==["MERRA2"]
            for var,unit in (("T2M","C"),("TS","C"),("PS","kPa")):
                assert data["parameters"][var]["units"]==unit
            coords=data["geometry"]["coordinates"]
            assert coords[:2]==[lon,lat]
            values=data["properties"]["parameter"]
            for when in sorted(set.intersection(*(set(values[k]) for k in ("T2M","TS","PS")))):
                air,skin,pressure=[values[k][when] for k in ("T2M","TS","PS")]
                if all(math.isfinite(x) and x!=data["header"]["fill_value"] for x in (air,skin,pressure)):
                    results.append((f"{lat}/{lon}/{when}",lat,lon,datetime.strptime(when,"%Y%m%d%H").isoformat()+"Z",
                                    air+273.15,skin+273.15,pressure*1000,url,digest(raw)))
        except (OSError,ValueError,HTTPError) as error:
            print("POWER unavailable",key,day,str(error),flush=True)
    return results

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--tiles-per-region",type=int,default=12)
    ap.add_argument("--weather-per-region",type=int,default=8)
    args=ap.parse_args()
    CACHE.mkdir(exist_ok=True,parents=True)
    OUT.mkdir(exist_ok=True)
    gr=archive_bytes()
    au=fetch("australia.csv",AU)
    assert digest(au)=="d9fa6d5b92642c56cc0b1ea7cc1ca22b763cde283cb71dc7194004a005f87812"
    sources=[("GEMAS",GEMAS_URL,digest(gr)),("NGSA",AU,digest(au))]
    samples=[]
    for key,raw in (("GEMAS",earth_rows(gr)),("NGSA",australia(au))):
        samples.extend((key,s) for s in raw)
    sites={}
    for src,s in samples:
        lat,lon=s["lat"],s["lon"]
        assert -90<lat<90 and -180<lon<180
        site=f"{lat:.4f}/{lon:.4f}"
        s["site"]=site
        sites[site]=(lat,lon,src)
    buckets=defaultdict(list)
    for site,(lat,lon,src) in sites.items():
        i,j=math.floor(lat),math.floor(lon)
        w,s,e,n=envelope(lat,lon)
        if i<=s and n<=i+1 and j<=w and e<=j+1 and -56<=i<60:
            buckets[src,i,j].append((site,lat,lon))
    def take(groups,n):
        return [g for src in ("GEMAS","NGSA")
                for g in sorted((k for k in groups if k[0]==src),key=lambda k:(-len(groups[k]),k))[:n]]
    terrain_tiles=take(buckets,args.tiles_per_region)
    terrain=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(lambda k:terrain_batch(k[1:],buckets[k]),terrain_tiles):
            terrain.extend(result)
    terrain_ids={r[0] for r in terrain}
    weather_buckets=defaultdict(list)
    for site in sorted(terrain_ids):
        lat,lon,src=sites[site]
        key=(round(lat*2)/2,round(lon/.625)*.625)
        weather_buckets[src,*key].append(site)
    weather_keys=take(weather_buckets,args.weather_per_region)
    weather={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for key,result in zip(weather_keys,pool.map(lambda k:weather_cell(k[1:]),weather_keys)):
            weather[key]=result
    dbpath=OUT/"earth-comparison.build.sqlite"
    dbpath.unlink(missing_ok=True)
    chem=", ".join(k.lower()+"_wt_pct REAL NOT NULL" for k in FIELDS)
    metrics=", ".join(k+" REAL NOT NULL" for k in METRICS)
    with sqlite3.connect(dbpath) as db:
        db.executescript(f"""PRAGMA foreign_keys=ON;
        CREATE TABLE sources(id TEXT PRIMARY KEY,url TEXT NOT NULL,sha256 TEXT NOT NULL);
        CREATE TABLE sites(id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
            footprint_wkt TEXT NOT NULL, crs TEXT NOT NULL DEFAULT 'EPSG:4326');
        CREATE TABLE samples(id TEXT PRIMARY KEY, site_id TEXT NOT NULL REFERENCES sites, source_id TEXT NOT NULL REFERENCES sources,
            region TEXT NOT NULL, material TEXT NOT NULL, depth_bottom_cm INTEGER NOT NULL, {chem}, source_locator TEXT NOT NULL,
            source_metadata_json TEXT NOT NULL);
        CREATE TABLE terrain(site_id TEXT PRIMARY KEY REFERENCES sites, {metrics}, source_url TEXT NOT NULL,
            sha256 TEXT NOT NULL, locator TEXT NOT NULL, min_bin_count INTEGER NOT NULL, max_bin_count INTEGER NOT NULL);
        CREATE TABLE weather(id TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL, utc TEXT NOT NULL,
            air_temperature_k REAL NOT NULL, surface_skin_temperature_k REAL NOT NULL, pressure_pa REAL NOT NULL,
            source_url TEXT NOT NULL, sha256 TEXT NOT NULL);
        CREATE TABLE site_weather(site_id TEXT REFERENCES sites,weather_id TEXT REFERENCES weather,
            distance_m REAL NOT NULL, PRIMARY KEY(site_id,weather_id));
        CREATE VIEW joined_inputs AS SELECT s.*, t.slope_median_deg,t.slope_p90_deg,t.slope_over_10_deg_fraction,
            t.relief_p90_p10_m,t.local_roughness_rms_m,w.utc,w.air_temperature_k,w.surface_skin_temperature_k,w.pressure_pa,
            l.distance_m FROM samples s JOIN terrain t ON t.site_id=s.site_id
            JOIN site_weather l ON l.site_id=s.site_id JOIN weather w ON w.id=l.weather_id;
        """)
        db.executemany("INSERT INTO sources VALUES(?,?,?)",sources)
        for site,(lat,lon,_) in sites.items():
            w,s,e,n=envelope(lat,lon)
            polygon=f"POLYGON (({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
            db.execute("INSERT INTO sites(id,latitude,longitude,footprint_wkt) VALUES(?,?,?,?)",(site,lat,lon,polygon))
        for src,s in samples:
            key=s["id"] if src=="NGSA" else f"GEMAS:{s['id']}"
            material=s["group"]
            meta={k:v for k,v in s.items() if k not in {"values","site"}}
            db.execute("INSERT INTO samples VALUES ("+",".join("?" for _ in range(14))+")",
                       (key,s["site"],src,s["country"],material,s["depth"],*(s["values"][k] for k in FIELDS),s["locator"],
                        json.dumps(meta,ensure_ascii=False,allow_nan=False)))
        db.executemany("INSERT INTO terrain VALUES (?,?,?,?,?,?,?,?,?,?,?)",terrain)
        for key,rows in weather.items():
            for row in rows:
                db.execute("INSERT OR IGNORE INTO weather VALUES (?,?,?,?,?,?,?,?,?)",row)
                for site in weather_buckets[key]:
                    lat,lon,_=sites[site]
                    db.execute("INSERT INTO site_weather VALUES (?,?,?)",(site,row[0],distance((lat,lon),key[1:],RADIUS)))
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        print("samples by source",Counter(src for src,_ in samples))
        for name in ("sites","samples","terrain","weather","site_weather","joined_inputs"):
            print(name,db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        print("joined sites",db.execute("SELECT source_id,COUNT(DISTINCT site_id) FROM joined_inputs GROUP BY 1").fetchall())
    db.close()
    dbpath.replace(OUT/"earth-comparison.sqlite")

if __name__=="__main__":
    main()
