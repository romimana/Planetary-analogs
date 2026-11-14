# Reference data audit and Earth matching

Run both builds, then `python audit.py`. The audit checks the 21 pinned inputs, integrity and relationships of both SQLite files, identical schemas, provenance fields, the atlas inventories, slope ranges and baselines, 27,760 APXS values with units and errors against their original CSVs, and all 385,049 Mars crater IDs, center coordinates and diameters against the author archive.

## Corrected during the audit

- The [Diviner PDS XML label](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/dlre_prp_south.xml) defines annual mean at 2 cm below the surface and annual maximum at the surface. Rename the mean and record its depth on all 1,727 summaries. These are modeled annual statistics, including the six parent areas.
- The [Lunar Sourcebook table 7.15](https://lunar-consortium.astrogeology.usgs.gov/data/chem_min/tab7_15.pdf) ASCII total row has values that cross fixed-width column boundaries. Parse the complete total row as tokens and preserve fixed widths for rows with blanks. Luna 24 now reads 100.4 wt% as printed. Total is a source diagnostic and should be excluded from similarity features.
- [Davis et al., Table 1](https://agupubs.onlinelibrary.wiley.com/doi/abs/10.1029/2019EA000874) gives Nili Patera as 8.7° N, 67.32° E. Both coordinates are now populated.

## Limits that affect judging

- Source matching does not certify that a quantity is comparable between worlds. A fresh Mars clone cannot reconstruct the exact full snapshot if the rolling NASA/CAB feed no longer matches the pinned hash. The pipeline fails visibly. This feed is excluded from scientific use. The only tabulated wind and pressure science examples are from two InSight sols in API documentation. REMS and MEDA are links in the current database. The crater redistribution terms still need primary-source confirmation before packaging that catalog publicly.
- Mars chemistry combines APXS targets and PIXL rock scans. Moon chemistry combines summaries and returned soils, sometimes repeated in separate size fractions. Regional coordinates do not resolve the positions of individual returned samples. Jezero chemical scans are not spatially joined to terrain cells. Keep FeO conventions, material, preparation, replicate flags and reporting limits explicit. A major oxide abundance is a chemical composition measurement. Identifying a mineral phase requires separate evidence.
- Jezero cells are 5 km across while Moon cells are 1 km across. A nominal 40 m slope baseline does not make those spatial summaries equivalent. Moon polar footprints can overlap, and Diviner cell statistics can have as few as four triangle centroids. Keep support counts and coverage as quality fields. Earth elevation uses a separate vertical datum. Compare a common within-cell relief definition after recomputation.
- A link probe reached 42 of 60 source entries directly with HTTP 200 or 206. Other requests returned 403, 406, 203 or a timeout. Some of these publications were independently located via their DOI, archive or primary manuscript. Browser access for every link and every handwritten value in the papers was not certified. Official 2026 judging and submission guide pages did not load in the audit web session. Follow the [2026 terms](https://www.spaceappschallenge.org/legal/) and verify the guides in a browser before submission.

## Fields to take forward

| Feature | Mars archive | Moon archive | Earth join and use |
|---|---|---|---|
| Terrain | Jezero slope median, p90 and p95-p05 relief | Polar slope median, p90 and p90-p10 relief | Recompute using a common footprint size, baseline and relief definition. Retain DEM resolution and vertical datum. |
| Oxide chemistry | SiO2, TiO2, Al2O3, Cr2O3, FeO, MnO, MgO, CaO, Na2O, K2O in wt%, with additional Mars-only oxides and elements | Same ten labels across the lunar compilation, with incomplete coverage and source-specific exclusions | Start with mutually observed chemistry and comparable materials. Document iron basis before using FeO. Keep one record per sample/preparation; handle compositional closure and detection limits. |
| Ground temperature | Gale daily ground temperature is outreach only. Calibrated REMS/MEDA still to load. | Annual modeled surface maximum and annual modeled mean at 2 cm | Get surface and subsurface quantities separately. Compare matching statistics and effective depth. A short Earth field window can be tagged as a test condition. |
| Atmosphere | InSight example pressure and wind only for now | No atmospheric series | Build an atmospheric comparison only for Mars where calibrated measurements and spatial support exist. Earth conditions can also describe the test itself. |
| Ice and material | Phoenix trench context and local conductivity | Cabeus localized inferred ice fraction | Compare only equivalent depth, quantity and measurement support; otherwise leave contextual. |

## Earth design

Publish three comparable dataset views, one per body. Under the Earth view, use `sites(site_id, geometry, CRS)`, `samples(sample_id, site_id, location, depth, material, method, source_id)`, and `time_windows(window_id, site_id, start_utc, end_utc, grid_or_station, distance, source_id)` with linked observations. Use point-in-polygon or a documented proximity threshold and keep spatial supports, dates and uncertainty. For 6 samples and 18 weather windows, store 6 sample rows and 18 window rows. Produce one rank row per site and eligible window, using documented chemistry at that site and preserving sample variability. Never count a Cartesian product as independent evidence.

Use [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) to evaluate synchronized local-time or UTC windows. Record its weather grid separately from the terrain footprint. Start with a transparent weighted nearest-neighbor ranking. Apply minimum feature coverage, show per-feature differences, and report whether results hold when weather windows, scale or weights change. Use known analogs as a benchmark and hold out nearby sites together to avoid spatial leakage. Reserve separate scores for terrain, material and thermal or atmospheric test objectives where coverage differs.
