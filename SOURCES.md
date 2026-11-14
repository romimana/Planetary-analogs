# Data sources and third-party terms

Each source ID below appears in SQLite and the atlas. Source links identify the publisher. The build fetches five original inputs; their URLs and verified SHA-256 hashes are in [inputs.json](inputs.json).

| Input | Terms and use |
|---|---|
| NASA PDS APXS archives | Public PDS scientific archives, cited by bundle DOI and row. See [NASA science information policy FAQ](https://science.nasa.gov/researchers/science-information-policy_faq/) and the individual archive notices. |
| USGS Jezero CTX elevation | USGS product with NASA mission data. Cite the named product and its credits. See [USGS copyrights and credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). |
| NASA/CAB weather feed | Public outreach data. The publisher discourages other uses. The source is identified as outreach in the build and atlas. |
| Robbins–Hynek 2020 crater catalog | Publicly downloadable from its author. No explicit redistribution license for this release located on the download page. Link to the source before redistribution review. |
| Published research and visual assets | Cite papers for transcribed numeric facts and the applicable method. Visuals are publisher links. Follow their product credits and [NASA image and media terms](https://www.nasa.gov/nasa-brand-center/images-and-media/) where applicable. |

Dependencies: [NumPy 2.4.4](https://numpy.org/doc/stable/license) (BSD-3-Clause, with separately licensed bundled components) and [Pillow 12.2.0](https://github.com/python-pillow/Pillow/blob/12.2.0/LICENSE) (MIT-CMU). The build uses the Python standard library and its SQLite module. Source data and dependency licenses remain with their respective publishers.

## Source register

| ID | Source | Product | Use |
|---|---|---|---|
| `craters` | [Robbins–Hynek — Mars Crater Database, 2020 release](https://craters.sjrdesign.net/) | Catalog_Mars_Release_2020_1kmPlus_FullMorphData.csv | Original author archive. Circle-fit geological inventory; not candidate site profiles. Coverage and morphologic classifications have documented limitations. 2020 CSV lacks depth. |
| `dunes` | [Davis et al. — Quantified Aeolian Dune Changes, Table 1 and Figure 1](https://discovery.ucl.ac.uk/id/eprint/10088261/1/2019EA000874.pdf) | 10.1029/2019EA000874 | Published geometric-mean estimates from repeat CTX imagery and terrain models; uncertainty is reported spread, not instrument accuracy. |
| `gale_apxs` | [NASA PDS — Berger Curiosity APXS targets, sols 0–3076](https://pds-geosciences.wustl.edu/msl/urn-nasa-pds-msl_apxs_supplement_sols_0_3076/data/) | 10.17189/6q8a-kg55 / ds01_2021je007171r.csv | Original target coordinates in metres and original elevation retained. Do not treat easting/northing as lon/lat. Source duplicate and low-quality flags retained verbatim. |
| `gale_chemin` | [Gale Crater Mineralogy and Geochemistry Database](https://galecrater.samples.odr.io/odr/chemin) | — | Mineral-phase archive linked; chemical oxide rows are stored separately. |
| `gale_dem` | [USGS — Gale merged DEM](https://astrogeology.usgs.gov/search/map/mars_msl_gale_merged_dem_1m) | — | 1 m postings; linked. |
| `gale_rems` | [NASA PDS — Curiosity REMS science archive](https://pdsatmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/curiosity/rems.html) | — | Calibrated archive linked for science use. |
| `gale_view` | [NASA — Gale surface materials](https://science.nasa.gov/photojournal/gale-craters-surface-materials/) | — | THEMIS false-color context. |
| `gale_weather` | [NASA / CAB — Curiosity REMS daily public weather feed](https://mars.nasa.gov/rss/api/?category=msl&feed=weather&feedtype=json) | NASA/CAB weather JSON, accessed 2026-11-14 | OUTREACH ONLY per publisher. Sampling is incomplete and the rover moves. Earth date is the source report date, not start UTC. Do not use these data as calibrated scientific evidence. |
| `hp3` | [Grott et al. — InSight thermal conductivity](https://doi.org/10.1029/2021JE006861) | — | Active heating measurement; value applies to a depth interval. |
| `insight_slope` | [USGS / Fergason et al. — Slopes at InSight](https://pubs.usgs.gov/publication/70177060) | — | Published slope at 1 m baseline, representative of most of the studied ellipse. |
| `insight_terrain` | [Warner et al. — InSight stratigraphic characterization](https://doi.org/10.1029/2022JE007232) | — | Figure 8c, slopes calculated using 3 × 3 pixels of a 1 m DEM; variability is within terrain class. |
| `insight_view` | [NASA/JPL — InSight press kit, landing site](https://www.jpl.nasa.gov/news/press_kits/insight/landing/mission/landing-site/) | — | Topographic and landing-ellipse views. |
| `insight_weather` | [NASA / JPL — InSight weather API documentation, Appendix A](https://api.nasa.gov/assets/insight/InSight%20Weather%20API%20Documentation.pdf) | — | Published example for sols 259 and 260; pressure and wind fields only. Temperature omitted because this document conflicts on its unit. |
| `jezero_dem` | [USGS — Mars 2020 Jezero CTX DEM mosaic](https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic) | M20_JezeroCrater_CTXDEM_20m.tif | Read the original numeric elevations and GeoTIFF metadata. Slope from central differences at 20 m postings; only cells with all four neighbors plus center valid. |
| `jezero_geology` | [USGS — Geologic map of Jezero and Nili Planum](https://pubs.usgs.gov/publication/sim3464) | — | Regional geological GIS resource. |
| `jezero_map` | [NASA — Perseverance location map](https://science.nasa.gov/mission/mars-2020-perseverance/location-map/) | — | Interactive rover traverse. |
| `landing` | [Mellon et al. — History of ground ice, Table 2](https://doi.org/10.1016/j.icarus.2021.114667) | — | Landing-area model inputs from published Table 2. Reference coordinates as printed; Jezero is the study reference near the landing site. Elevation is relative to the Mars reference surface. |
| `landing_map` | [NASA/JPL — Mars landing sites overview](https://science.nasa.gov/image-detail/45468-landingsitescontextmap-featperseverance/) | — | Orbital context map with nine NASA landing sites. |
| `mars_trek` | [NASA/JPL — Mars Trek](https://trek.nasa.gov/mars/) | — | Planet-wide basemap and context for catalog crater coordinates. |
| `mawrth` | [HiRISE — Layering Along a Tributary to Mawrth Vallis](https://hirise.lpl.arizona.edu/dtm/PSP_002074_2025) | — | Stereo terrain model and context for CRISM/OMEGA orbital clay detections. |
| `meda` | [NASA PDS — Perseverance MEDA](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html) | — | Calibrated and derived environmental sensor archives linked. |
| `mer` | [NASA PDS — Spirit and Opportunity APXS oxide abundances](https://pds-geosciences.wustl.edu/missions/mer/mer_apxs_oxide.htm) | 10.17189/1518973 | 2021 ZIP; the source .err columns are 2σ statistical precision. Norm is a standoff indicator, and short integration/standoff can affect precision. Coordinates are not in these two tables. |
| `nili_view` | [HiRISE — The Active Dunes of Nili Patera](https://hirise.lpl.arizona.edu/ESP_035603_1890) | — | Orbital image of active dunes. |
| `opportunity_view` | [NASA — Opportunity Eagle Crater traverse area](https://science.nasa.gov/photojournal/eagle-crater-traverse-area/) | — | Overhead view of the landing site and planned traverse. |
| `oxia_view` | [ESA — Oxia Planum close up](https://www.esa.int/ESA_Multimedia/Images/2018/11/Oxia_Planum_close_up) | — | HiRISE image and orbital clay interpretation. |
| `pathfinder_view` | [NASA — Pathfinder landing site](https://science.nasa.gov/resource/mars-pathfinder-landing-site/) | — | Orbital and horizon features. |
| `phoenix_dig` | [Arvidson et al. — Phoenix robotic arm experiment](https://doi.org/10.1029/2009JE003408) | — | Stone Soup excavation did not reach icy soil by approximately 18 cm. |
| `phoenix_ice` | [Stoker et al. — Habitability of the Phoenix landing site](https://doi.org/10.1029/2009JE003421) | — | Phoenix trench samples and context, Table 1. |
| `phoenix_slope` | [Mellon et al. — Prelanding assessment of the Phoenix ice table](https://doi.org/10.1029/2007JE003067) | — | Primary landing area (box 1); approximate range of median slopes over a 250 m baseline. |
| `phoenix_view` | [NASA/JPL — Phoenix’s Lay of the Land](https://www.jpl.nasa.gov/images/pia10908-phoenixs-lay-of-the-land/) | — | Trench imagery and context. |
| `pixl` | [Simon et al. — Jezero crater floor samples, Table 4](https://doi.org/10.1029/2022JE007474) | 10.1029/2022JE007474 | Bulk sums on abraded rock spots. Source has separate 1σ error and within-scan standard deviation columns; the database uses the 1σ error. |
| `spirit_view` | [NASA/JPL — Spirit from orbit](https://www.jpl.nasa.gov/news/nasa-mars-orbiter-photographs-spirit-and-vikings-on-the-ground/) | — | HiRISE view of Spirit in Columbia Hills. |
| `tecp` | [Grott et al. — Seasonal variations in soil conductivity](https://doi.org/10.1029/2023GL102975) | — | Phoenix conductivity cited from Zent et al.; different depth and method from HP³. |
| `viking_gallery` | [NASA — Viking imagery](https://science.nasa.gov/mars/resources/viking-mission-resources/) | — | Lander images from both locations. |
| `zhurong_view` | [NASA/JPL — The Zhurong Rover Explores Utopia Planitia](https://www.jpl.nasa.gov/images/pia24914-the-zhurong-rover-explores-utopia-planitia/) | — | HiRISE orbital context. |
