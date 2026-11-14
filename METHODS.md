# Methods and audit

| Table | Unit of record |
|---|---|
| `areas` | Mars reference site, sub-site, or terrain cell |
| `footprints` | Jezero cell polygon in the native projected Mars CRS, plus coverage counts |
| `samples` | Individual source chemistry record, with target and source quality flags where supplied |
| `observations` | One numerical or categorical result, its unit, uncertainty, spatial support and source locator |
| `time_windows` | Source sol, UTC interval, or pooled solar-longitude interval |
| `assets`, `sources` | Area resource links and source provenance |
| `craters` | Global inventory with circle-fit position and diameter and optional shape attributes |

## Terrain

Read elevations from the USGS Jezero CTX DEM, 20 m grid spacing. Split the native grid into non-overlapping 250 × 250 pixel cells (5 km projected sides). Discard partial edge cells and cells below 90% valid elevation coverage. Mask the GeoTIFF nodata sentinel. In the native equirectangular projection, compute east–west rise/run from the two adjacent cells with a 40 m nominal baseline, adjusted for latitude by cos(standard parallel) / cos(local latitude). Compute north–south rise/run using the same nominal baseline. Slope in degrees is atan(hypot(east–west rise/run, north–south rise/run)) converted to degrees. A slope requires a valid center and four neighbors. Store the median and 90th percentile of slope, median elevation, and local relief defined as elevation p95 minus p05. The source pixel bounds and valid counts are recorded per cell. This method resolves terrain at DEM scale.

## Chemistry

Read instrument CSVs for Spirit, Opportunity and Curiosity. Preserve sample identifiers, source row, chemistry values, quality/duplicate flags where present, and original coordinates where present. Import eight Jezero PIXL bulk scan summaries and reported 1σ errors from Simon et al., Table 4. MER uncertainties are reported 2σ statistical precision. Keep major constituents in wt% and Ni/Zn/Br in ppm. Keep chemical abundances separate from mineral detections. Rows may represent repeated measurements and instrument or preparation differences remain relevant. Curiosity easting and northing remain in source coordinates. No chemistry record has been joined to a Jezero slope cell.

## Weather, regional data, and craters

- Curiosity's NASA/CAB outreach feed is stored as source-tagged sol reports. Ignore missing values. The four summaries are per-variable medians of available values in disjoint 90-degree Ls bins pooled over all available years. They do not establish simultaneous exposure and are excluded from `science_observations`. Two InSight sol examples are tabulated separately.
- Published landing-area values, dune summaries, slope statistics and soil/depth observations are keyed to their cited table, figure or narrative. Material or uncertainty text distinguishes proxies and direct readings. Maps and images appear as links.
- The crater inventory uses the author’s 2020 release. Longitudes are represented as positive east modulo 360, and the published identifiers and circle-fit dimensions are preserved. Catalog rows have no inferred chemistry or weather.

## Audit

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT * FROM area_coverage WHERE id IN ('jezero','gale','insight','phoenix');
SELECT target, parameter, value, unit, uncertainty, record_locator, source_url
FROM observation_provenance WHERE sample_id='jezero:Dourbes' AND parameter='MgO';
SELECT COUNT(*), MIN(value), MAX(value) FROM observations WHERE parameter='slope_p90';
SELECT COUNT(*) FROM craters;
SELECT COUNT(*) FROM science_observations WHERE source_id='gale_weather';
```

Expected checks on the pinned build: integrity `ok`, no foreign-key violations, Dourbes MgO 19.73 wt% with reported error 0.99 wt%, 340 p90 slope records (2.75743–49.41976°), 385,049 crater rows, and zero outreach rows in the science view.
