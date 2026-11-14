# Analog matching datasets

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
