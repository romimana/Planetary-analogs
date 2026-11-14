# Analog matching datasets

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
