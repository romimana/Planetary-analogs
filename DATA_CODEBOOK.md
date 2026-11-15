# Data codebook

The [Colab notebook](https://colab.research.google.com/github/romimana/Planetary-analogs/blob/main/explore_data.ipynb) reads [the versioned SQLite snapshot](data/ml-geology.sqlite). Run the last section to build `point_profiles` and `audit`. The three profiles contain one row per eligible sample. The audit counts missing values in every displayed column. For a scenario feature it counts samples with zero qualifying observations. The denominators are 4,024 Earth, 137 Mars and 12 Moon samples. Mars excludes 12 chemistry holds. Nine Moon samples use mission-area anchors. Detailed time series are available in the database and in the notebook's `tables` dictionary.

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
| `solar_zenith_deg` | Solar angle relative to local vertical, 0° overhead and 90° on the geometric horizon. Calculated in Colab for Earth ERA5 UTC windows | 3,738 | 137 | 12 |
| Atmospheric wind | Wind speed and direction, not imported. Lunar solar wind describes charged particles | 4,024 | 137 | N/A |
| Wet ground / flooding | Earth soil moisture or event inundation coverage, neither imported | 4,024 | N/A | N/A |
| Grain size / dry dust or sand | No comparable quantitative grain-size field imported | 4,024 | 137 | 12 |
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

### Environment extensions

- Solar modeling uses [NOAA geometry](https://gml.noaa.gov/grad/solcalc/solareqns.PDF) for Earth in Colab. At a dated Mars or Moon scenario use [NASA NAIF SPICE incidence](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/ilumin_c.html). Solar hour alone cannot identify the full geometry. Diviner's cumulative bins lack a single matching timestamp. Panel angle, terrain shadow and irradiance would need additional data.
- Wind sources are [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview) for Earth and [REMS](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=MSL-M-REMS-5-MODRDR-V1.0) for the Curiosity sites, subject to damaged-sensor flags. [MEDA](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html) covers Perseverance's Jezero route. Match instrument height, and account for air density for wind-loading tests. [The lunar exosphere](https://science.nasa.gov/moon/lunar-atmosphere/) supplies no comparable atmospheric wind.
- For Earth wet ground, [ERA5-Land upper soil moisture](https://climate.copernicus.eu/esotc/2025/about-data) is an estimate of water in the upper layer, separate from flood extent or measured mud. For dry ground, the [Apollo/Luna grain-size catalog](https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/19930012474.pdf) can be checked by sample ID. The [REMS dust-devil optical-depth study](https://doi.org/10.1029/2026JE009778) illustrates a distinct atmospheric dust quantity. Keep atmospheric dust and particle size as separate features.
