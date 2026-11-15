# Feature coverage and matching priorities

Snapshot `26111d1`, `data/ml-full.sqlite`. Counts are missing **samples** out of 4,024 Earth, 12 Moon, and 137 Mars eligible samples. The Mars denominator excludes 12 chemistry holds. Eligible Moon samples include nine mission anchors whose terrain describes the landing area. Environmental absence means no qualifying scenario for that sample. Planetary environmental counts require rover or station context. Earth uses MODIS for surface temperature and ERA5 for air temperature and pressure.

| Feature | Meaning | Earth | Moon | Mars | Default relevance / 5 |
| --- | --- | ---: | ---: | ---: | ---: |
| `sio2_wt_pct` | Silica, a major indicator of silicate composition | 3,022 | 0 | 0 | 5 |
| `tio2_wt_pct` | Titanium dioxide, distinguishes titanium-rich material including some lunar basalts | 0 | 0 | 4 |
| `mgo_wt_pct` | Magnesium oxide, helps distinguish magnesium-rich geologic material | 0 | 0 | 4 |
| `cao_wt_pct` | Calcium oxide, indicates calcium contribution across possible minerals | 0 | 0 | 4 |
| `k2o_wt_pct` | Potassium oxide, helps distinguish potassium-rich material | 0 | 0 | 3 |
| `mno_wt_pct` | Manganese oxide, an additional discriminator of bulk composition | 0 | 0 | 2 |
| `slope_median_deg` | Typical slope across the 5 km window | 3,410 | 0 | 0 | 3 |
| `slope_p90_deg` | Slope at the 90th percentile, describing the steeper part of the window | 3,410 | 0 | 0 | 5 |
| `slope_over_10_deg_fraction` | Fraction of measured gradient cells above 10 degrees | 3,410 | 0 | 0 | 4 |
| `relief_p90_p10_m` | Elevation difference between the 90th and 10th percentiles | 3,410 | 0 | 0 | 3 |
| `local_roughness_rms_m` | Elevation departures from neighboring cells on the 500 m grid | 3,410 | 0 | 0 | 4 |
| Surface temperature in K | MODIS land surface, REMS ground brightness, or Diviner bolometric brightness | 3,588 | 9 | 128 | 3 |
| `air_temperature_k` | Near-surface air temperature | 3,738 | N/A | 128 | 2 |
| `pressure_pa` | Atmospheric pressure at the surface | 3,738 | N/A | 128 | 1 |

The scores are judgment calls for general analog screening. Surface temperature rises to 5 for thermal testing. Use pressure as a test constraint for equipment affected by low pressure. A lunar ambient-air comparison is inapplicable. Rainfall, engineering texture, wind, and humidity are unavailable as harmonized comparison features. Use local solar time and date to select scenarios. Use coordinates, sample medium, source, distance, and quality as filters or provenance.

Start with a fixed chemistry subset for every candidate and target in a run. Compare ratios together. Select a reduced slope set or cap the slope group's total weight to avoid double-counting. Apply the terrain profile only when the selected fields exist, and report the eligible count for every run. The common terrain grid is intended for regional screening.

The local expanded Earth dataset has 8,367 samples. Silica is missing from 3,022. Each terrain field is missing from 7,627, MODIS from 4,267, and ERA5 from 8,014. These are sample counts, so multiple samples at a geographic site can share coverage.

## Chemistry and terrain profile

In the Colab notebook, set `INCLUDE_TERRAIN = True` and `INCLUDE_SILICA = False`. This selects five chemistry features and the five terrain measures for 614 Earth samples (558 GSJ and 56 NGSA). With silica enabled, coverage is 56 NGSA samples. Environmental fields stay available in the full archive.

All 3,410 Earth samples missing terrain sit within the nominal NASADEM latitude band. Rechecking their full 5 km windows shows 3,023 fit inside one tile (2,181 GSJ, 842 NGSA), across 546 candidate tile keys. Another 387 windows cross tile boundaries (283 GSJ, 104 NGSA). These are geometric eligibility counts, pending tile availability and valid-pixel checks. The existing build selected eight tiles in Japan and 12 per survey in the Earth build. First expand [NASADEM](https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001) and mosaic tile edges in GIS. Use [Copernicus GLO-30](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) as a fallback after comparing an overlap sample. GLO-30 is a surface model that can include vegetation and structures. Preserve source and quality per site.

Prototype additional terrain metrics on the same 5 km window and 500 m grid using NASADEM or GLO-30 on Earth, [MOLA](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) on Mars and [SLDEM2015](https://pgda.gsfc.nasa.gov/products/54) on the Moon. Candidate metrics are slope variation (p90 minus p10 slope, in degrees) and the size of the largest connected low-slope region (fraction of valid interior cells under a fixed slope threshold, using four-neighbor adjacency). The second metric measures terrain continuity at regional scale. Keep cell support and threshold identical across bodies. Check redundancy with the current slope statistics before weighting either metric. Test local relative elevation against known valley and ridge sites as a secondary feature. These metrics can be computed from the cited elevation grids and have no published values in the current export.
