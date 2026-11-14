"""Build a sample-to-environment context database from source products."""
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen

import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
CACHE = ROOT / "work/context"
PDS = "https://pds-geosciences.wustl.edu/"
LOLA = PDS + "lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/sldem2015/tiles/float_img/"
DIVINER = PDS + "lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp/"
MOLA = PDS + "mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
REMS = "https://pds-atmospheres.nmsu.edu/PDS/data/mslrem_1001/DATA/"
WAYPOINTS = "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/MSL_waypoints.json"
PLACES = "https://planetarydata.jpl.nasa.gov/w10n/msl/msl_places/document/PLACES_PDS_SIS.pdf"
HAASE = "https://doi.org/10.1029/2018EA000408"
APOLLO = {
    "72501": (20.09916,30.53033,"station 2 · South Massif landslide soil"),
    "76501": (20.28993,30.79997,"station 6 · North Massif soil near crater ejecta"),
    "78221": (20.27663,30.87753,"station 8 · soil collected beneath a boulder"),
}
RADII = {"mars":3396190, "moon":1737400}

def download(url, name, start=None, size=None):
    path = CACHE / name
    if path.exists():
        raw = path.read_bytes()
    else:
        headers = {}
        if start is not None:
            headers["Range"] = f"bytes={start}-{start+size-1}"
        with urlopen(Request(url,headers=headers), timeout=45) as response:
            if start is not None and (response.status != 206 or not
                response.headers.get("Content-Range","").startswith(f"bytes {start}-{start+size-1}/")):
                raise ValueError(f"Range response mismatch for {url}")
            raw = response.read()
        if size is not None and len(raw) != size:
            raise ValueError(f"Incomplete {name}")
        path.write_bytes(raw)
    if size is not None and len(raw) != size:
        raise ValueError(f"Incomplete {name}")
    return raw

def distance(a, b, radius):
    lat1, lon1 = map(math.radians,a)
    lat2, lon2 = map(math.radians,b)
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * radius * math.asin(math.sqrt(min(1,h)))

def terrain(body, lat, lon):
    radius = RADII[body]
    if body == "moon":
        band = "00n_30n" if lat >= 0 else "30s_00s"
        north = 30 if lat >= 0 else 0
        west = 45 * math.floor(lon/45)
        stem = f"sldem2015_512_{band}_{west:03}_{west+45:03}_float"
        base, ppd, width, height, dtype = LOLA, 512, 23040, 15360, "<f4"
    else:
        north = 0 if lat < 0 else 44
        west = 90 * math.floor(lon/90)
        stem = f"megt{north:02}n{west:03}hb"
        base, ppd, width, height, dtype = MOLA, 128, 11520, 5632, ">i2"
    # Product bounds describe exterior edges. Select cell centers within the local 5 km square.
    dy = radius*math.pi/180/ppd
    dx = dy*math.cos(math.radians(lat))
    c, r = (lon-west)*ppd-.5, (north-lat)*ppd-.5
    c0,c1 = math.ceil(c-2500/dx), math.floor(c+2500/dx)+1
    r0,r1 = math.ceil(r-2500/dy), math.floor(r+2500/dy)+1
    assert 0 <= c0 < c1 <= width and 0 <= r0 < r1 <= height
    item = np.dtype(dtype).itemsize
    # Fetch full rows in fixed blocks so nearby samples reuse the same input bytes.
    blocks = []
    url = base + stem + ".img"
    for first in range((r0//128)*128,r1,128):
        n = min(128,height-first)
        start,size = first*width*item,n*width*item
        raw = download(url,f"{stem}-{first}.bin",start,size)
        blocks.append((first,raw,start,size))
    pixels = np.vstack([np.frombuffer(raw,dtype=dtype).reshape(-1,width)
                        [max(r0-first,0):min(r1-first,128),c0:c1]
                        for first,raw,_,_ in blocks]).astype(float)
    if body == "moon":
        pixels *= 1000  # SLDEM2015 float IMG height is stored in kilometers.
    assert pixels.shape == (r1-r0,c1-c0)
    assert np.isfinite(pixels).all() and np.max(np.abs(pixels)) < 15000
    # Aggregate source cell centers into the same 500 m bins on both bodies.
    bx = np.floor(((np.arange(c0,c1)-c)*dx + 2500)/500).astype(int).clip(0,9)
    by = np.floor(((np.arange(r0,r1)-r)*dy + 2500)/500).astype(int).clip(0,9)
    bins = by[:,None]*10+bx[None,:]
    count = np.bincount(bins.ravel(),minlength=100)
    assert np.all(count > 0)
    common = (np.bincount(bins.ravel(),weights=pixels.ravel(),minlength=100)/count).reshape(10,10)
    common_metrics = terrain_metrics(common,500,500)
    return dict(url=url,label_url=base+stem+".lbl",support="5 km centered square, native grid",
                cell_m=[dx,dy],baseline_m=[2*dx,2*dy],pixels=pixels.size,
                **terrain_metrics(pixels,dx,dy),
                common_500m=dict(common_metrics, pixels=100, baseline_m=1000,
                                 minimum_source_pixels_per_bin=int(count.min()),
                                 maximum_source_pixels_per_bin=int(count.max())),
                locator=f"rows [{r0},{r1}), cols [{c0},{c1})",
                inputs=[dict(start=start,size=size,sha256=hashlib.sha256(raw).hexdigest())
                        for _,raw,start,size in blocks])

def terrain_metrics(pixels, dx, dy):
    gx = (pixels[1:-1,2:]-pixels[1:-1,:-2])/(2*dx)
    gy = (pixels[2:,1:-1]-pixels[:-2,1:-1])/(2*dy)
    slope = np.degrees(np.arctan(np.hypot(gx,gy)))
    residual = pixels[1:-1,1:-1] - (pixels[1:-1,:-2]+pixels[1:-1,2:]+pixels[:-2,1:-1]+pixels[2:,1:-1])/4
    return dict(slope_median_deg=float(np.median(slope)),slope_p90_deg=float(np.percentile(slope,90)),
                slope_over_10_deg_fraction=float(np.mean(slope>10)),
                relief_p90_p10_m=float(np.percentile(pixels,90)-np.percentile(pixels,10)),
                local_roughness_rms_m=float(np.sqrt(np.mean(residual**2))))


def diviner(lat, lon):
    lon = (lon+180)%360-180
    south = math.floor(lat/10)*10
    def lat_label(v):
        return f"{abs(v):02}{'s' if south<0 and v<=0 else 'n'}"
    stem = f"global_cumul_avg_cyl_{lat_label(south)}{lat_label(south+10)}_002"
    i, j = math.floor((lon+180)*2), math.floor((lat-south)*2)
    start = (1+(i*20+j)*96)*113
    url = DIVINER + stem + ".tab"
    raw = download(url,f"{stem}-{i}-{j}.tab",start,96*113)
    center = (south+(j+.5)/2,-180+(i+.5)/2)
    values = []
    for line,row in enumerate(csv.reader(io.StringIO(raw.decode("ascii")))):
        x,y,t = map(float,row[:3])
        assert (y,x) == center and abs(t-(line+.5)/4) <= .0051
        value = float(row[10])
        if value > 0:
            values.append(dict(window=f"{line/4:05.2f}–{(line+1)/4:05.2f}",local_solar_hour=t,
                               surface_brightness_k=value,source_record=start//113+line+1))
    return dict(url=url,label_url=url[:-3]+"lbl",distance_m=distance((lat,lon),center,RADII["moon"]),
                center=center,coverage_deg=.5,kind="binned lunar local solar time; cumulative 2009–2015",
                start_byte=start,sha256=hashlib.sha256(raw).hexdigest(),windows=values)

def rems_url(sol):
    index=download(REMS,"rems-root.index").decode()
    bands=set(re.findall(r"SOL_(\d{5})_(\d{5})/",index))
    lo,hi=next((lo,hi) for lo,hi in sorted(bands) if int(lo)<=sol<=int(hi))
    folder=REMS+f"SOL_{lo}_{hi}/SOL{sol:05d}/"
    page=download(folder,f"rems{sol}.index").decode()
    files=sorted(set(re.findall(r'href="([^"]*RMD[^"]*\.TAB)"',page,re.I)))
    if not files:
        raise ValueError(f"No MODRDR for sol {sol}")
    return folder+files[-1]

def rems(sol):
    url = rems_url(sol)
    raw = download(url,f"rems{sol}.tab")
    label = download(url[:-3]+"LBL",f"rems{sol}.lbl").decode()
    expected=int(re.search(r"^FILE_RECORDS\s*=\s*(\d+)",label,re.M)[1])
    assert re.search(r"PLANET_DAY_NUMBER\s*=\s*"+str(sol)+r"\b",label)
    assert re.search(r'\^REMS_SCIENCE_TABLE\s*=\s*"([^"]+)"',label)[1] == url.rsplit("/",1)[1]
    stats = defaultdict(lambda: defaultdict(list))
    for row in csv.reader(io.StringIO(raw.decode("ascii"))):
        assert len(row) == 40 and int(row[1][:5]) == sol
        hour=int(row[2].strip().split()[-1].split(":")[0])
        air,ground,pressure=float(row[15]),float(row[7]),float(row[37])
        if row[16].strip().endswith("11") and 100 < air < 400:
            stats[hour]["air_temperature_k"].append(air)
        if row[10].strip()=="1111" and 100 < ground < 400:
            stats[hour]["ground_brightness_k"].append(ground)
        if row[39].strip().endswith("1") and 100 < pressure < 1500:
            stats[hour]["pressure_pa"].append(pressure)
    assert len(raw.splitlines()) == expected
    windows=[]
    for hour, measurements in sorted(stats.items()):
        if measurements.get("air_temperature_k") and measurements.get("pressure_pa"):
            values={k:dict(median=median(v),minimum=min(v),maximum=max(v),n=len(v))
                    for k,v in measurements.items()}
            windows.append(dict(window=f"sol {sol} · {hour:02}:00 LTST",sol=sol,local_solar_hour=hour,values=values))
    return dict(url=url,label_url=url[:-3]+"LBL",kind="calibrated REMS MODRDR hourly samples",
                sha256=hashlib.sha256(raw).hexdigest(),windows=windows)

def main():
    CACHE.mkdir(exist_ok=True)
    raw=download(WAYPOINTS,"waypoints-all.json")
    waypoints=sorted((x["properties"] for x in json.loads(raw)["features"]),key=lambda x:x["sol"])
    assert all(distance((w["lat"],w["lon"]),
                        (math.degrees(w["northing"]/RADII["mars"]),math.degrees(w["easting"]/RADII["mars"])),
                        RADII["mars"]) < 2 for w in waypoints)
    mars=json.loads((OUT/"mars-soil-reference.json").read_text(encoding="utf-8"))["records"]
    moon=json.loads((OUT/"moon-soil-reference.json").read_text(encoding="utf-8"))["records"]
    output=[]
    waypoint_hash=hashlib.sha256(raw).hexdigest()
    anchors={}
    area_location_source={}
    for body in RADII:
        with sqlite3.connect((OUT/f"{body}.sqlite").as_uri()+"?mode=ro", uri=True) as db:
            area_location_source[body]=dict(db.execute("SELECT a.id,s.url FROM areas a JOIN sources s ON a.source_id=s.id"))
    for row in mars+moon:
        body=row["body"].lower()
        lat,lon=row["area_latitude"],row["area_longitude"]
        role="mission anchor"
        locator=area_location_source[body][row["area_id"]]
        material=row["material"]
        material_source=row["source_url"]
        name=row["target"]
        if body=="mars" and row["area_id"]=="gale":
            lat,lon=(math.degrees(row[field]/RADII[body]) for field in ("northing_m","easting_m"))
            role="APXS published rover position, inverse PLACES projection"
            locator=PLACES
            assert -5 < lat < -4 and 137 < lon < 138
        if body=="moon" and name.split(",")[0] in APOLLO:
            parent=name.split(",")[0]
            lat,lon,material=APOLLO[parent]
            role="Apollo 17 collection station, LRV parking position"
            locator=HAASE
            material_source=(f"https://www.lpi.usra.edu/lunar/samples/atlas/compendium/{parent}.pdf"
                             if parent!="78221" else "https://www.lpi.usra.edu/lunar/samples/atlas/compendium/78221.pdf")
        key=(body,lat,lon)
        anchors[key]=None
        output.append(dict(id=row["id"],body=body,name=name,area=row["area_name"],lat=lat,lon=lon,
            location_role=role,location_source=locator,material=material,material_source=material_source,sol=row["sol"],
            chemistry=row["measurements"],chemistry_url=row["source_url"],chemistry_locator=row["record_locator"],
            chemistry_status=row["chemistry_status"],preparation=row["preparation_code"]))
    # Fetch sources in order so nearby samples reuse the same cached raster blocks.
    for body,lat,lon in anchors:
        anchors[body,lat,lon]=terrain(body,lat,lon)
    planned=[58,83,84,85,89,523,530,558,605,673,801]
    rems_inputs={}
    def load(sol):
        try:
            return sol,rems(sol)
        except (OSError,ValueError) as error:
            print("Unavailable REMS",sol,error,flush=True)
            return sol,None
    download(REMS, "rems-root.index")
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sol,result in pool.map(load,planned):
            if result and result["windows"]:
                rems_inputs[sol]=result
    lunar={}
    for row in output:
        body,lat,lon=row["body"],row["lat"],row["lon"]
        row["terrain"]=anchors[body,lat,lon]
        row["environment"]=[]
        if body=="moon":
            key=(lat,lon)
            if key not in lunar:
                lunar[key]=diviner(lat,lon)
            row["environment"]=[lunar[key]]
        elif row["area"]=="Gale Crater":
            for sol,product in rems_inputs.items():
                prev=max((i for i,w in enumerate(waypoints) if w["sol"]<=sol),default=-1)
                if prev==-1:
                    continue
                w=waypoints[prev]
                if w["sol"]==sol:
                    continue  # End-of-drive alone does not locate the full sol.
                d=distance((lat,lon),(w["lat"],w["lon"]),RADII[body])
                if d<=1000:
                    row["environment"].append(dict(product,distance_m=d,waypoint_sol=w["sol"],
                        waypoint_rmc=w["RMC"],waypoint_source=WAYPOINTS, waypoint_sha256=waypoint_hash,
                        waypoint_coordinates=[w["lat"],w["lon"]],
                        position_method="latest prior published drive waypoint; not an instrument footprint",
                        chemistry_sol_delta=sol-row["sol"]))
    for row in output:
        fine_location = row["location_role"] != "mission anchor"
        eligible = row["chemistry_status"] == "reference_for_relative_composition"
        if row["environment"] and eligible:
            row["profile_status"] = "linked_at_station_or_rover_scale" if fine_location else "linked_at_mission_scale"
        else:
            row["profile_status"] = "missing_environment_or_chemistry_screen"
    assert sum(r["profile_status"] == "linked_at_station_or_rover_scale" and r["body"] == "mars"
               for r in output) >= 9
    assert sum(r["profile_status"] == "linked_at_station_or_rover_scale" and r["body"] == "moon"
               for r in output) == 3
    assert all(r["environment"][0]["windows"] for r in output if r["body"]=="moon")
    write_output(output)

def write_output(rows):
    temp=OUT/"planetary-context.build.sqlite"
    temp.unlink(missing_ok=True)
    with sqlite3.connect(temp) as db:
        db.executescript("""PRAGMA foreign_keys=ON;
        CREATE TABLE profiles(id TEXT PRIMARY KEY, body TEXT, area TEXT, name TEXT, latitude REAL,
          longitude_e REAL, location_role TEXT, chemistry_status TEXT, profile_json TEXT NOT NULL);
        CREATE TABLE environment_windows(profile_id TEXT REFERENCES profiles, window_id TEXT,
          distance_m REAL, source_url TEXT, data_json TEXT NOT NULL, PRIMARY KEY(profile_id,window_id));""")
        for row in rows:
            values={k:v for k,v in row.items() if k!="environment"}
            db.execute("INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?,?)",(
                row["id"],row["body"],row["area"],row["name"],row["lat"],row["lon"],row["location_role"],
                row["chemistry_status"],json.dumps(values,ensure_ascii=False,allow_nan=False)))
            for product in row["environment"]:
                meta={k:v for k,v in product.items() if k!="windows"}
                db.executemany("INSERT INTO environment_windows VALUES(?,?,?,?,?)",(
                     (row["id"],w["window"],product["distance_m"],product["url"],
                      json.dumps(dict(meta,**w),ensure_ascii=False,allow_nan=False)) for w in product["windows"]))
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        print(db.execute("SELECT p.body,count(distinct p.id),count(distinct w.profile_id),count(w.window_id) FROM profiles p LEFT JOIN environment_windows w ON w.profile_id=p.id GROUP BY 1").fetchall())
    db.close()
    temp.replace(OUT/"planetary-context.sqlite")
    from build_pilot import FIELDS
    payload=json.dumps({"rows":rows,"fields":FIELDS},ensure_ascii=False,allow_nan=False,separators=(",",":")).replace("</","<\\/")
    template=(ROOT/"planetary_context.html").read_text(encoding="utf-8")
    (OUT/"Planetary Context.html").write_text(template.replace("__CONTEXT__",payload),encoding="utf-8")

if __name__=="__main__":
    main()
