# Soil reference codebook

This release freezes the inputs for a six-component soil composition comparison. Run `python curate_references.py` after both planetary builds. The exports retain the original weight percentages and provenance. This step does not calculate a similarity score or modify the earlier pilot.

## Feature dictionary

All six variables are reported oxide-equivalent mass fractions in weight percent, meaning grams per 100 grams as defined by the publisher. They describe bulk chemistry and cannot identify mineral phases by themselves.

| Key | Plain language | Why retain it |
|---|---|---|
| SiO2 | Silica, the reporting form of silicon | Distinguishes silica-rich material from lower-silica material |
| TiO2 | Titanium dioxide, the reporting form of titanium | Helps distinguish volcanic materials with different titanium content |
| MgO | Magnesium oxide, the reporting form of magnesium | Indicates magnesium enrichment |
| CaO | Calcium oxide, the reporting form of calcium | Indicates calcium enrichment |
| K2O | Potassium oxide, the reporting form of potassium | Adds information about parent material alongside other oxides |
| MnO | Manganese oxide, the reporting form of manganese | Helps distinguish compositions with otherwise similar major constituents |

The fixed six are a **subcomposition**. Other measured compounds remain in the source databases. Iron reporting conventions and the ambiguous aluminum and chromium labels in lunar Table 7.16 require separate resolution. No missing value is imputed.

## Record selection and provenance

| Dataset | Source and acceptance rules | Coverage |
|---|---|---|
| Mars, Gale | [Berger et al. PDS work](https://pds-geosciences.wustl.edu/missions/msl/apxs.htm) and [preparation table](https://doi.org/10.1029/2020JE006536). APXS is a rover surface chemistry instrument. Keep untouched soil/sand (SU) and rover-disturbed soil/sand (SD) as separate preparation categories. Exclude explicit quality/duplicate flags, mixtures and size-selected preparations. | 55 |
| Mars, Gusev and Meridiani | [NASA PDS MER APXS](https://pds-geosciences.wustl.edu/missions/mer/mer_apxs_oxide.htm), including archive `document/apxs_pds_notes.txt`. Apply the same preparation filter. Require at least one hour integration and Norm ≥50 as conservative project screening choices. Norm is a standoff proxy affected by source decay. These cutoffs do not constitute mission certification. | 44 Gusev, 50 Meridiani |
| Moon | [Lunar Sourcebook Table 7.16](https://lunar-consortium.astrogeology.usgs.gov/data/chem_min/tab7_16.pdf). Select laboratory measurements of returned bulk soil, with all six fields positive and present. Separate size fractions and overlapping mission averages stay in the base archive. Three Luna bulk rows lack silica in this table. | 12 across Apollo 11, 12, 14, 15, 16, 17 |
| Earth validation | [GEMAS extended dataset](https://umweltportal.niedersachsen.de/suche/detail?id=numis-metadaten-0554568e-c60f-4106-b099-839bb30f9c44). Pinned BGR ZIP, archive Data description PDF §2.4.1, oxidized reporting tables 13b/23b, detection-limit files 13d/23c. Wavelength-dispersive X-ray fluorescence measures total content. The archive records agricultural soil at 0–20 cm and grazing soil at 0–10 cm. | 4,343 pilot rows meet all six limits at 4,238 distinct coordinate pairs. European coverage. |

All selected Mars values have positive reported error below the measured concentration. MER values are reported with 2-sigma repeatability errors. These are distinct from cross-instrument bias. Lunar Table 7.16 lacks per-value uncertainties. Documented source repeat and quality flags are applied where present, so these are counts of records rather than independent field sites.

Exports contain `id`, `area_id`, `target`, `method`, `material`, `preparation_code`, source locators, and `measurements` by key with raw value, unit and available uncertainty. `area_latitude` and `area_longitude` are mission anchors, with planetary east longitude 0–360°. Gale retains source rover coordinates in metres for future CRS validation. The exports mark cross-method validation pending. A mission anchor is not a sample coordinate. No weather or terrain is joined to a chemistry measurement in this release.

## Composition matching after the freeze

Use all six positive components from the same sample. Calculate each component's natural log relative to the geometric mean of the six, and compare the resulting vectors with Euclidean distance (Aitchison distance). Proportionally scaling every component leaves the distance unchanged. Keep the original mass percentages visible for review, including when absolute content matters to the test. A user-selected emphasis can later be added as a weighted distance in log-ratio coordinates, clearly distinguished from the default. Keep a fixed panel per search so missing fields cannot give candidates an advantage. [Published geochemical log-ratio example](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2018JB016145).

Next gate: check method bias on material reference standards where feasible and confirm sample geolocation before any terrain/weather join. Keep published map resolution and climate-pixel support instead of assigning coarse conditions to a precise sampling point. Expand Earth sources by applying this same feature and evidence contract.
