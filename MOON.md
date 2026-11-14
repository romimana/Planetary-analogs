# Moon reference database

The database uses the Mars tables and provenance views. All lunar `areas` are explicitly marked with `body = 'Moon'`. A named south-pole DEM area is the footprint of an orbital terrain product. A mission site is a landing anchor tied to historical sample records. The Cabeus record is a localized impact measurement. Image and map links are in `assets`.

The build validates all downloaded inputs against `moon-inputs.json`.

## Terrain and temperature

- [NASA LOLA adjusted polar DEMs](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/) provide six projected 5 m grids. NASA describes extensive interpolation between laser tracks. Mean elevations over non-overlapping 4×4 source pixels produce a 20 m grid. Central differences across 40 projected meters yield east and north gradient components. Their magnitude is corrected for the local stereographic scale factor before applying arctangent. The database records median and 90th-percentile slope, median elevation, and elevation relief between the 10th and 90th percentiles.
- One-kilometer cells partition each parent DEM. Neighboring DEM footprints can overlap. Percentiles use NumPy's linear interpolation. `footprints` stores WKT polygons in lunar south polar stereographic meters, the reference radius, and valid pixel counts. Polygon boundaries are GIS-ready in the CRS specified in that table.
- The [NASA PDS Diviner Polar Resource Product](https://ode.rsl.wustl.edu/mercury/pagehelp/Content/Missions_Instruments/LRO/DIVINER/PRP.htm) supplies fitted annual mean and maximum surface temperature for triangles. Their geographic centroids are projected into the LOLA CRS, then assigned with half-open footprint bounds. Aggregation uses unweighted triangle counts and quantiles, and stores the coldest annual maximum among included triangles. The SHA-256 attached to each Diviner slice refers to the listed inclusive HTTP byte interval. Annual thermal summaries have no UTC window or Earth weather equivalence.

## Returned samples and impact spectroscopy

- [Lunar Sourcebook chapter 7](https://lunar-consortium.astrogeology.usgs.gov/) tables 7.15, 7.16 and 7.17 supply summaries, bulk soil and size fractions. Original table columns and lines appear in the provenance view. Weight percent and ppm remain separate. A parent sample can recur across tables and size fractions. Sample geolocation is at mission level. [LROC hardware coordinates](https://lroc.im-ldi.com/data/support/downloads/2016_LROC_Coordinates_of_Human_Features.pdf) supply location anchors and elevation at the spacecraft.
- The archived 7.15 Apollo 11 sodium value appears as 47 wt%, inconsistent with the oxide total, and is excluded. Ambiguous 7.15 phosphorus and 7.16 aluminum/chromium oxide labels are omitted. The typeset 7.16 PDF establishes the size fractions in micrometers. Table 7.17 nickel is excluded because the source flags contamination. Blanks stay missing.
- For Cabeus, the [LCROSS paper](https://pubmed.ncbi.nlm.nih.gov/20966242/) estimates 5.6 ± 2.9 wt% water ice for observable excavated regolith. The value applies to the localized impact estimate. The position comes from the [weighted impact reconstruction](https://ntrs.nasa.gov/citations/20140005563).

## Audit queries

```sql
SELECT kind, COUNT(*) FROM areas GROUP BY kind;
SELECT area_name, parameter, value, unit, spatial_support, source_url, record_locator
FROM observation_provenance
WHERE area_id IN ('lola01', 'apollo11', 'cabeus_lcross')
ORDER BY area_name, parameter;

SELECT a.id, a.name, f.native_crs, f.footprint_wkt
FROM areas a JOIN footprints f ON f.area_id = a.id
WHERE a.parent_id IS NULL;
```

The current release covers the six polar terrain products and nine sample-return landing sites. Polar terrain cells contain terrain and annual thermal statistics; laboratory chemistry is available at the returned-sample mission anchors. The catalog has no global crater inventory, direct polar soil chemistry, or lunar radiation series.
