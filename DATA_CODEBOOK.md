# Data codebook

## Matching inputs

The notebook exposes all six chemistry fields, all six terrain metrics, latitude, east longitude, and mapped geology in `X_earth`, `X_mars`, and `X_moon`. These inspection tables keep missing values and use sample IDs as the index. The default ranking profile uses four chemistry fields (titanium dioxide for titanium-rich material, magnesium oxide for magnesium-bearing material, calcium oxide for calcium-bearing material, and potassium oxide for potassium-rich material) plus the six regional terrain metrics. Silica and manganese oxide are optional in the ranking. The `_ready` matrices keep candidates with all selected values, transform the selected chemistry subset to centered log ratios, and scale all three matrices using Earth medians and interquartile ranges. A feature with zero Earth IQR uses divisor one.

Use one weighted nearest-neighbor ranker for both comparisons. Choose a target sample and a fixed feature profile, then apply the same profile to all Earth candidates in that run. Reuse the prepared Earth matrix when the selected features and scenario stay the same. Assign weights by feature group and average the squared standardized differences within each group before combining them. This keeps a group with more columns from automatically dominating the score. Return the candidate count and per-group distances with the ranking. Geology can filter candidates by a selected Earth map unit. Cross-world lithology distance requires a documented legend mapping.

For a solar match select one published UTC scenario per body. Reuse the Earth scenario for both comparisons. The numeric input is `horizontal_projection`, with zero below the geometric horizon and one for overhead Sun. Treat zero as a distinct case if a test requires direct sunlight. Air and ground temperature, pressure, wind, moisture and grain-size evidence remain in archive tables. They are excluded from the prepared feature matrices.

GIS geology fields are strings. A unit code is scoped to its map product and is joined to Earth samples by `site_id` and to planetary samples by sample ID. The model input excludes geology codes and coordinates from its numeric feature vectors. Use map units as filters or spatial context. Cross-world scoring would require an independently documented common legend. Terrain uses identical units and regional grid support, with different original sensor resolutions. A DEM-derived gentle patch describes regional-scale connectivity.

### Solar verification

`python audit_solar.py` checks the geometric projection in all 99,960 published rows and queries [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html) for airless topocentric elevation at 27 spot checks. Three locations spanning the sampled latitude range and three published times per location are checked on each body. Maximum absolute zenith-angle differences were 0.07270° (Earth), 0.07521° (Mars), and 0.00586° (Moon). The threshold for this screening check was 0.5°. The comparison uses geometric SPICE zenith and apparent airless Horizons elevation, with different reference surface conventions. These results support geometric screening at the sampled coordinates. They do not validate local shadow or power output. [Recorded checks and exact query links](data/solar-audit.json)

The [Colab notebook](https://colab.research.google.com/github/romimana/Planetary-analogs/blob/main/explore_data.ipynb) reads [the versioned SQLite snapshot](data/ml-enriched.sqlite). Run the last section to build `point_profiles` and `audit`. The three profiles contain one row per eligible sample. The audit counts missing values in every displayed column. For a scenario feature it counts samples with zero qualifying observations. The denominators are 4,024 Earth, 137 Mars and 12 Moon samples. Mars excludes 12 chemistry holds. Nine Moon samples use mission-area anchors. Detailed time series are available in the database and in the notebook's `tables` dictionary.

| Field | Meaning and units | Missing Earth | Missing Mars | Missing Moon |
| --- | --- | ---: | ---: | ---: |
| `sio2_wt_pct` | Silica (silicon dioxide), a major component for comparing silicate materials, mass percent | 3,022 | 0 | 0 |
| `tio2_wt_pct` | Titanium dioxide, distinguishes titanium-rich materials such as some lunar basalts, mass percent | 0 | 0 | 0 |
| `mgo_wt_pct` | Magnesium oxide, tracks magnesium-rich components, mass percent | 0 | 0 | 0 |
| `cao_wt_pct` | Calcium oxide, tracks the contribution of calcium-bearing components, mass percent | 0 | 0 | 0 |
| `k2o_wt_pct` | Potassium oxide, distinguishes potassium-rich materials, mass percent | 0 | 0 | 0 |
| `mno_wt_pct` | Manganese oxide, an additional bulk-composition discriminator, mass percent | 0 | 0 | 0 |
| `slope_median_deg` | Typical slope, degrees | 0 | 0 | 0 |
| `slope_p90_deg` | Slope at the 90th percentile, degrees | 0 | 0 | 0 |
| `slope_over_10_deg_fraction` | Fraction of interior cells above 10° | 0 | 0 | 0 |
| `relief_p90_p10_m` | 90th–10th percentile elevation difference, metres | 0 | 0 | 0 |
| `local_roughness_rms_m` | RMS elevation difference from the mean of four neighbors, metres | 0 | 0 | 0 |
| `largest_gentle_patch_fraction` | Largest four-neighbor connected region at or below 10°, fraction of 64 interior cells | 0 | 0 | 0 |
| `geology_unit`, `geology_description`, `geology_product`, `geology_url`, `geology_locator` | Source-specific mapped unit, description, product, URL and cell or polygon locator. Each field has the stated count | 420 | 0 | 0 |
| Surface temperature | Earth MODIS land surface temperature, Mars REMS ground brightness, Moon Diviner bolometric brightness, K | 3,588 | 128 | 9 |
| `air_temperature_k` | Near-surface air temperature, K | 3,738 | 128 | N/A |
| `pressure_pa` | Surface air pressure, Pa | 3,738 | 128 | N/A |
| `solar_zenith_deg` | Geometric solar angle relative to vertical, 0° overhead and 90° at the horizon | 0 | 0 | 0 |
| Atmospheric wind speed | Earth ERA5 at 10 m. Mars REMS preliminary coverage shown here | 3,738 | 128 | N/A |
| Earth soil moisture | ERA5 top 7 cm volumetric water fraction | 3,738 | N/A | N/A |
| Grain or texture context | GSJ field notes, exact Mars target descriptions, or same-aliquot Apollo sieve bins | 1,739 | 133 | 11 |
| `median_dn` | Median uncalibrated RADARSAT-1 image digital number. Historical Earth context | 4,009 | N/A | N/A |

IDs, source, material, location role and coordinates are metadata. The model-profile metadata fields applicable to each world are populated. `NULL` means missing in SQLite. N/A means physically inapplicable to the comparison.

## Sources and joins

| Layer | Earth | Mars | Moon |
| --- | --- | --- | --- |
| Chemistry | Geoscience Australia NGSA and Japan GSJ. GEMAS is available in the separate local copy | NASA PDS rover chemistry archives | Apollo measurements from Lunar Sourcebook, with sample provenance |
| Terrain | NASADEM HGT v001, NASA Earthdata | Mars Global Surveyor MOLA MEGDR | LRO LOLA and Kaguya SLDEM2015 |
| Mapped geology | Hartmann and Moosdorf GLiM raster at 0.5° | USGS SIM 3292, 1:20M | USGS Unified Geologic Map v2, 1:5M |
| Environment | MODIS MOD11A1.061 for surface temperature, ERA5 via Open-Meteo for air and pressure. NASA POWER is available for regional context | Curiosity REMS MODRDR, quality-filtered windows | LRO Diviner cumulative local-solar-time bins |

See [chemistry methods and sources](CODEBOOK.md), [Earth GIS sources](EARTH.md), [MOLA and lunar terrain and environment](CONTEXT.md), and [geology URLs and reproducible builds](ML.md). GIS joins Earth observations by `site_id` and planetary observations by sample and scenario IDs. It measures terrain in the common 5×5 km window and assigns geology using the containing raster cell or polygon. The geology field describes mapped surroundings. Use the source and location role to interpret an individual sample. Keep MODIS and ERA5 as separate time series unless using the audited near-time associations in `complete_earth`.

### Canadian data

[CSA RADARSAT-1 archive](https://www.csa-asc.gc.ca/eng/satellites/radarsat1/data-access.asp), Open Government Licence – Canada. GIS transforms site coordinates using scene ground control points and takes the median positive valid pixel over a 21×21 window with at least 400 valid pixels. The GitHub release has one historical scene at 15 Australian sites. The local comparison copy adds one European scene/site. `earth_radar` stores scene, acquisition time, pixel coordinates, count, source URL and hash. The published values are image digital numbers without backscatter calibration. A flood or wet-ground test would use an event scene and a comparable baseline, with independently verified event coverage. This is actual use of CSA data. See the [CSA Space Apps resources](https://www.csa-asc.gc.ca/eng/open-data/space-apps-challenge.asp) for the listed RADARSAT missions.

### Added environmental data

- **Solar geometry** uses NASA/JPL [SPICE kernels](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/) with source hashes in `solar_sources`. `solar_scenarios` contains geometric angles for a fixed schedule in 2024. Earth and Mars use six UTC hours on each of four dates. The Moon uses eight noon-UTC dates four days apart. Use `body, location_id, utc` as the key. Use Earth site IDs or planetary sample IDs for the join. These are reference scenarios independently of other measurement times. The projections use an Earth ellipsoid and spherical approximations for Mars and the Moon, with geometric ephemerides and the Mars barycenter as the center approximation. Horizontal projection is the nonnegative cosine of the zenith angle. It excludes irradiance, slope, panel tilt and local shadow. Diviner cumulative bins have no single matching timestamp.
- **Earth wind and moisture** come from ERA5 through Open-Meteo. GIS uses the existing 0.25° grid cells and UTC hours with a 10 km site-to-cell-center limit. `earth_environment` includes wind direction in degrees and keeps weather source and file hashes. Moisture is volume of water per volume of soil; it does not measure flood extent or mud. Generated using Copernicus Climate Change Service information (2024).
- **Mars wind** comes from [Curiosity REMS MODRDR](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MSL-M-REMS-5-MODRDR-V1.0). The first five confidence characters must all be 1. The final character distinguishes reliable and preliminary readings. The sampled windows had only preliminary readings. The median, p90, observation count and flag are kept in `mars_wind_windows` and joined in `mars_environment`. The Moon has no corresponding atmospheric wind.
- **Sand and grain size** use separate evidence. Japan's original GSJ grain notes are in `earth_grain_notes`. Mars descriptions in `mars_texture_context` are linked by named Curiosity target and sol. `moon_grain_bins` retains measured weight percentages by sieve size from the [NASA digitized catalog](https://ntrs.nasa.gov/citations/20250001791). Use `join_level='same_aliquot'` when the chemistry and grain measurement must refer to the same numbered split. Other rows link different splits of the same parent, and are contextual. These three sources do not supply an interchangeable numeric sand fraction.

Earthdata topic portals for land surface and hydrology point to useful alternatives. [NASA POWER MERRA-2](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/) offers hourly winds, and [NASA SMAP L4](https://catalog.data.gov/dataset/smap-l4-global-3-hourly-9-km-ease-grid-surface-and-root-zone-soil-moisture-analysis-update-49882) offers modeled soil moisture constrained by satellite observations. The current wind and moisture observations use ERA5.

Rebuild from the geology snapshot with `python fetch_extra_weather.py`, then `python build_enriched_ml.py` with `spiceypy==8.4.0`. See [coverage and checksum](data/ml-enriched.json).
