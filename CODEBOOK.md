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

## Chemistry QA decision

Use records marked `reference_for_relative_composition` for the initial six-component screening. Of the 149 Mars records, 137 meet the indicative APXS thresholds (55 Gale, 32 Gusev, 50 Meridiani); 12 Gusev records have potassium oxide below the 0.20 wt% reference threshold and are retained with `hold_for_six_component_comparison`. The threshold is a conservative project rule applied across these APXS datasets. It does not prove that a particular measurement was below its own detection limit. All 12 Apollo records remain reference candidates. Their source round-trip was checked for all six fields. All 4,343 GEMAS pilot rows meet their own published detection limits.

[Berger et al., Table 1](https://doi.org/10.1029/2020JE006536) gives the following indicative limits and relative calibration deviations. The deviation describes reference-material performance. It gives neither the direction nor the magnitude of any individual sample correction. The [MER calibration report](https://doi.org/10.1029/2005JE002555) and archive notes distinguish calibration deviation from measurement-level fit or repeatability error. The Curiosity export also retains spectral width and instrument offset from the source CSV. All 55 selected Gale spectra have reported Fe-line widths 142.8–195.3 eV, below the 210 eV criterion discussed by [Berger et al. 2022](https://doi.org/10.1029/2021JE007171).

| Feature | Indicative limit, wt% | Relative calibration deviation |
|---|---:|---:|
| Silica | 1 | 3% |
| Titanium dioxide | 0.2 | 20% |
| Magnesium oxide | 1 | 14% |
| Calcium oxide | 0.2 | 7% |
| Potassium oxide | 0.2 | 15% |
| Manganese oxide | 0.05 | 8% |

### Material and depth

- **Mars.** APXS measures a small patch in place. Berger et al. give a diameter of roughly 15–20 mm under close placement and element-dependent signal depths of roughly 3–90 micrometers in an example basalt. These are instrument response depths. They cannot be used as collection depth. The fit assumes a sufficiently homogeneous target; grain size, matrix and standoff can shift reported ratios. Keep untouched and disturbed preparation codes. MER Norm and integration-hour cutoffs above remain screening choices.
- **Moon.** Laboratory results are for returned bulk aliquots; the reference suite includes bulk material below 1 mm, which is a grain-size cutoff. The collection depth is unknown in this export. [Lunar Sample Atlas](https://www.lpi.usra.edu/lunar/samples/atlas/index.cfm) gives collection descriptions or stations for some parents. NASA's [10084 Compendium](https://www.lpi.usra.edu/lunar/samples/atlas/compendium/10084.pdf), Table 1a, reproduces the values in the Laul column and lists analyses of other splits. For titanium dioxide one comparison is 7.50 vs 7.56 wt%, and for calcium oxide 12.50 vs 12.08 wt%. Differences reflect both preparation/aliquot and analytical effects. One sample cannot establish a correction for the suite.
- **Earth.** GEMAS covers mixed soil over 0–10 cm (grazing) or 0–20 cm (agricultural), prepared below 2 mm, with total concentrations measured by wavelength-dispersive X-ray fluorescence. See the dataset's internal Data description §2.4.1 and [GEMAS quality-control documentation](https://gemas.eurogeosurveys.org/GEMAS.htm). Depth is collection support and must be retained as such. The source quality program and detector thresholds support the Earth measurements on their own terms.

**Decision.** These sources support measured composition vectors for relative screening. No matched-material result establishes a transfer correction across APXS, the lunar compilation and GEMAS. Apply no universal correction. Preserve raw values, method, depth and uncertainty metadata. When ranking is implemented, report sensitivity to APXS relative calibration deviations and avoid awarding a definitive winner when plausible variations change the ranking. This codebook does not certify matching soil depth, mineral phases or suitability for a field experiment. A terrain or thermal join requires confirmed sample or station geometry. Mission anchors remain suitable for context.
