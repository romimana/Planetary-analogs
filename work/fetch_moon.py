from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
import shutil

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "lunar"
LOLA = "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp"
PRP = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/dlre_prp_south"
CHEM = "https://lunar-consortium.astrogeology.usgs.gov/data/chem_min"
# Each pair is an inclusive zero-based PRP grid stripe interval.
STRIPES = {"01": (597, 660), "04": (590, 643), "07": (615, 667),
           "11": (544, 596), "20": (338, 388), "23": (330, 420)}

def fetch(name, url, byte_range=None):
    RAW.mkdir(exist_ok=True)
    target = RAW / name
    headers = {"User-Agent": "Planetary-analogs/1.0"}
    if byte_range:
        start, end = byte_range
        headers["Range"] = f"bytes={start}-{end}"
    with urlopen(Request(url, headers=headers), timeout=90) as response, target.with_name(target.name + ".part").open("wb") as output:
        if byte_range:
            expected_range = f"bytes {start}-{end}/604800210"
            if response.status != 206 or response.headers.get("Content-Range") != expected_range:
                raise ValueError(f"Unexpected range response for {name}")
        shutil.copyfileobj(response, output)
    temporary = target.with_name(target.name + ".part")
    if byte_range and temporary.stat().st_size != end - start + 1:
        raise ValueError(f"Incomplete range for {name}")
    temporary.replace(target)
    print(name, target.stat().st_size, flush=True)

def fetch_thermal(site, first, last):
    fetch(f"prp{site}.tab", PRP + ".tab", (210 * (1 + 2400 * first), 210 * (1 + 2400 * (last + 1)) - 1))

if __name__ == "__main__":
    import sys

    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = [pool.submit(fetch_thermal, site, *limits) for site, limits in STRIPES.items()]
        if "--thermal-only" not in sys.argv:
            jobs.extend(pool.submit(fetch, f"lola{site}.tif", f"{LOLA}/Site{site}/Site{site}_final_adj_5mpp_surf.tif") for site in STRIPES)
            jobs.extend(pool.submit(fetch, f"tab{n}.asc", f"{CHEM}/tab7_{n}.asc") for n in (15, 16, 17))
            jobs.append(pool.submit(fetch, "prp.xml", PRP + ".xml"))
        for job in jobs:
            job.result()
