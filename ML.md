# Analog matching datasets

## Chemistry, terrain and mapped geology

Use [ml-geology.sqlite](data/ml-geology.sqlite) for the expanded modeling data. It contains the full archive plus `earth_model_profiles`, `mars_model_profiles`, and `moon_model_profiles`. These views expose chemistry, terrain and mapped geology. Colab loads this database by default and verifies the checksum in [the coverage report](data/ml-geology.json). The local build also includes GEMAS under its source terms.

GIS reads [NASADEM HGT](https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001) windows for all Earth candidates. At tile boundaries it combines valid elevation sums and counts before calculating the 500 m bin means, assigns each boundary posting once, and requires 95% source posting validity in each of the 100 bins. Each Earth result carries the source window URL, row and column bounds and SHA-256 of its little-endian int16 values followed by its Boolean valid mask. The row-level SHA-256 is the hash of that window manifest. Mars uses [MOLA](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) and the Moon uses [SLDEM2015](https://pgda.gsfc.nasa.gov/products/54), with source hashes and windows in planetary provenance.

`largest_gentle_patch_fraction` is the size of the largest four-neighbor connected region with slope at or below 10° divided by 64. The 64 interior 500 m cells support the common 1 km central-difference slope calculation. One means all interior cells are in the same gentle region. This is a regional screening metric. At this scale almost all of the sampled Mars windows have values near one.

GIS assigns Earth geology from the containing 0.5° [GLiM cell](https://doi.org/10.1594/PANGAEA.788537) (Hartmann and Moosdorf, 2012, CC BY 3.0). Unclassified, water and ice cells yield no lithology. In Mars and Moon GIS the point is transformed to the source map CRS and joined to the containing [USGS Mars SIM 3292 polygon](https://doi.org/10.3133/sim3292) (1:20M) or [Unified Moon v2 polygon](https://astrogeology.usgs.gov/search/map/Moon/Geology/Unified_Geologic_Map_of_the_Moon_GIS_v2/) (1:5M). Mars uses the pinned mirror of the original USGS shapefile identified in the builder. Moon positions use lunar body-fixed longitude and the published spherical map projection. The mapped unit is regional context. A sample's material is kept separately, and mission-anchor locations represent the area around landing. The three map legends use distinct categories. Colab can require a mapped unit as a coverage filter and keeps map codes outside the numeric distance.

Reproduce after building the full archive. Install `rasterio==1.5.2 pyproj==3.8.0 pyshp==3.1.8 shapely==2.2.0`, run `python enrich_terrain.py`, then `python build_geology_ml.py`. To include European records locally run `python enrich_terrain.py --local` and `python build_geology_ml.py --local`. NASADEM coverage is approximately 56°S to 60°N. Sites outside that band are still present with missing terrain.

See [feature coverage and matching priorities](FEATURES.md) for the per-body missing-value audit.

## Full dataset with missing values

Open [`ml-full.sqlite`](data/ml-full.sqlite) for flexible matching. See [coverage and checksums](data/ml-full-coverage.json). The local file `outputs/ml-full-local.sqlite` adds GEMAS under its publisher terms. Run the comparison and final builds, then run `python build_full_ml.py` to reproduce both files. The complete dataset remains available in the `complete_earth`, `complete_mars`, and `complete_moon` tables.

| Table or view | Grain and content |
| --- | --- |
| `earth_profiles` | One row per sample, with coordinates, chemistry and available terrain |
| `earth_modis` | Surface temperature observations keyed by site, granule and pass |
| `earth_site_era5`, `earth_era5` | Geographic links by `site_id`, with atmospheric temperature and surface pressure by `weather_id = id` |
| `earth_site_power`, `earth_power` | Coarser regional weather, with the same join keys |
| `earth_radar` | Canadian RADARSAT-1 context keyed by site and scene |
| `planet_samples`, `planet_sample_scenarios`, `planet_scenarios` | Planetary samples, links and environment windows |
| `planetary_profiles` | Sample and scenario view retaining samples without a scenario. Filter `comparison_status <> 'chemistry_hold'` for eligible chemistry |

Treat SQL `NULL` as unavailable. Use the same explicitly selected fields for every candidate in a ranking. A candidate is eligible only if all selected fields are present for both target and candidate. For ratios, apply the log-ratio transform on the same selected set of at least two chemistry components on both sides. Coordinate IDs are join keys and provenance and quality fields are metadata. Atmospheric scenarios and MODIS overpasses have different time support. Use `complete_earth` when both are needed within the validated time tolerance.

### Japan

Source: Geological Survey of Japan, AIST, [Geochemical Map downloads](https://gbank.gsj.jp/geochemmap/data/download.htm), [map-specific terms](https://gbank.gsj.jp/geochemmap/setumei/licence.html) and [GSJ numerical data terms](https://www.gsj.jp/en/license/). These are adapted numerical records. The builder joins the chemistry and coordinate files by survey sample ID, and omits both entries with ambiguous ID 78013. File hashes and source URLs appear in `additional_sources`. Preserve original JGD2000 coordinates. For regional GIS extraction treat the coordinates as approximate WGS84. GIS computes the same 5 km terrain features for sites covered by the eight densest eligible NASADEM tiles and associates ERA5 for those sites using the same grid-cell distance rule.

The Japanese river sediment was sieved to 180 µm and the magnetic fraction removed. The five retained components are reported in oxide-equivalent weight percent after acid digestion and ICP-AES. The material fraction and analytical method can shift the composition compared with the Australian and planetary measurements. Use Japan for exploratory rankings with a source and material filter. Silica, a major component for comparing silicate-rich material, stays NULL in the Japanese rows. See [method and material](https://doi.org/10.2343/geochemj.2.0618).

## Complete dataset

**Use the [final SQLite snapshot](data/ml-final.sqlite) for modeling.** It has exactly three tables, `earth`, `mars` and `moon`. Every column in these tables is required. See [final coverage and checksums](data/ml-final-coverage.json). The earlier comparison snapshots below are source material with broader coverage.

| Table | Required environment fields | Independent locations |
| --- | --- | --- |
| `earth` | MODIS surface temperature, ERA5 air temperature and surface pressure | 13 in GitHub and 65 in the local snapshot |
| `mars` | REMS air temperature, surface pressure and ground brightness temperature | 7, from 9 samples |
| `moon` | Diviner bolometric surface brightness temperature by local solar hour | 3 Apollo 17 stations |

All three require six positive chemistry values and the five terrain metrics. Each row is one sample linked to one environmental scenario. Earth GIS joins by the sample's site ID and uses the nearest ERA5 grid cell on the 0.25-degree grid. The project accepts a cell center up to 10 km from the site. That distance is a spatial eligibility threshold and the estimate still represents a coarse grid. Earth observations use four dates in 2024. These are seasonal snapshots. GIS converts the MODIS local solar hour to an approximate UTC time on the granule's UTC day, using site longitude, and takes the nearest ERA5 hour within 30 minutes. A MODIS daily pixel may represent an average of valid overpasses. Mars retains distance to the rover waypoint proxy and sol offset. Moon retains distance to the Diviner bin center and local solar hour. Lunar air temperature and atmospheric pressure are inapplicable to this comparison.

Earth weather is from [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) with `models=era5`, `elevation=nan` and `cell_selection=nearest`. Use the API's surface-pressure variable, which is a modeled estimate. Generated using Copernicus Climate Change Service information (2024). Convert Celsius to Kelvin and hPa to Pa. Surface temperatures preserve their source-specific names and physical meaning. Use a unit-compatible but exploratory thermal distance. Refer to [NASA's MODIS user guide](https://modis-land.gsfc.nasa.gov/pdf/MOD11_User_Guide_V61.pdf).

To reproduce, build the comparison snapshots following the steps below, then run `python fetch_final_weather.py` and `python build_final_ml.py`. The broader Earth snapshot provides site coordinates for the weather fetch. The final local database is `outputs/ml-final-local.sqlite`. Japanese and Peruvian rows were excluded because the six required chemistry measurements and full GIS joins could not be verified. The RADARSAT scene observations remain in the comparison archive.

The final snapshot supports an exploratory weighted nearest-neighbor baseline. It has no ground-truth analog labels. For evaluation group Earth by site and regional block, and group planetary queries by location. A row count is a count of scenarios, and repeated scenarios from a location should stay together.

## Comparison snapshots

Open [Earth](data/earth.sqlite) and [Mars and Moon](data/planetary.sqlite) in SQLite. [Coverage and SHA-256](data/coverage.json) records the exact release. Within the planetary file, filter the `samples` or `chemistry_inputs` view by `body = 'mars'` or `body = 'moon'`.

| Purpose | Earth view | Planetary view |
| --- | --- | --- |
| Bulk chemistry | `chemistry_inputs` | `chemistry_inputs` |
| Chemistry and regional terrain | `terrain_inputs` | `chemistry_inputs` also includes terrain |
| Surface temperature | `surface_temperature_inputs` | `mars_surface_inputs` or `moon_thermal_inputs` |
| Surface temperature and terrain | `surface_terrain_inputs` | `mars_surface_inputs` or `moon_thermal_inputs` |
| Regional air temperature and pressure | `joined_inputs` | `mars_atmosphere_inputs` |

```sql
SELECT id, area, location_role, material, sio2_wt_pct, slope_median_deg
FROM chemistry_inputs WHERE body = 'mars' LIMIT 5;
```

See [chemistry feature definitions](CODEBOOK.md) and [planetary measurements, terrain and scenario methods](CONTEXT.md). Values are on common reporting units. Chemistry uses weight percent of oxides or oxide equivalents. The six values are a subset of the whole composition. Compare their ratios jointly with a centered log-ratio transform in a distance model. XRF methods, preparation, collection depth and sampled medium can affect the result. Terrain uses the shared 5 km square with 500 m bins and the common gradient calculation. The terrain metrics describe a region needed for screening. Route planning requires finer coverage. MODIS surface temperature, REMS ground brightness and Diviner bolometric brightness use Kelvin and different retrievals, footprints and averaging intervals. Treat thermal distances as exploratory. NASA POWER represents a coarse grid, with source distance preserved. RADARSAT-1 median digital numbers are retained for scene context.

There are no match labels. For a first baseline use purpose-weighted nearest neighbors. Test chemistry and terrain independently before combining them. Keep all repeated observations at a GIS site in the same evaluation group, and use spatial blocks to reduce leakage between nearby sites. Report the eligible site count for each purpose. Each input view requires that purpose's data. The source tables retain missing values where applicable. Several planetary samples share coordinates or environmental windows.

## Reproduce the snapshots

For the local Earth database use [Earth build instructions](EARTH.md). For the planetary database build [context](CONTEXT.md) and run `python build_comparison.py`. Run `python package_ml.py` to validate database integrity, foreign keys and chemistry ranges, rebuild the Earth views, and generate the data bundle and coverage manifest. The full Earth copy is written to `outputs/earth-ml-local.sqlite`. The GitHub Earth snapshot uses Geoscience Australia NGSA observations with attribution. GEMAS data is locally retrievable from the publisher under its [listed conditions](https://umweltportal.niedersachsen.de/suche/detail?id=numis-metadaten-0554568e-c60f-4106-b099-839bb30f9c44). Lunar measurements are selected numerical data points attributed to their original source tables. Full archive tables, imagery and original bulk files stay with their providers.
