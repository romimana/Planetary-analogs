# Proposed map-unit crosswalk

This is a proposed ranking rubric for the published sample locations. It describes mapped regional context. Keep `geology_product` and `geology_unit` as the original key and retain the original label and map locator. The numeric values below are heuristic penalties for comparing mapped settings.

| Earth GLiM code | Canonical label | Lunar Em / Im2 | Martian eHv |
| --- | --- | ---: | ---: |
| vb | mafic volcanic | 0.00 | 0.00 |
| vi | intermediate volcanic | 0.35 | 0.25 |
| va | felsic volcanic | 0.55 | 0.35 |
| pb | mafic plutonic | 0.40 | 0.40 |
| pi | intermediate plutonic | 0.60 | 0.55 |
| pa | felsic plutonic | 0.75 | 0.65 |
| py | pyroclastic deposit | 0.65 | 0.60 |
| mt | metamorphic | 0.90 | 0.90 |
| su | unconsolidated sediment | 1.00 | 1.00 |
| ss | siliciclastic sedimentary | 1.00 | 1.00 |
| sm | mixed sedimentary | 1.00 | 1.00 |
| sc | carbonate sedimentary | 1.00 | 1.00 |
| ev | evaporite | 1.00 | 1.00 |

A zero here means strongest available map-class analogy. Lunar mare units support a basaltic interpretation. Mars eHv supports a volcanic-flow interpretation at map scale. Keep composition and texture checks separate. In the lunar comparison, mafic plutonic material such as gabbro can be more informative than felsic lava for a composition-sensitive experiment. For surface texture, study the field material directly.

| Body | Unit | Canonical map context | Earth rock-comparison treatment |
| --- | --- | --- | --- |
| Mars | eHv | volcanic flows | Use rubric above |
| Mars | AHi | impact-related unit | Seek verified terrestrial impact context in a separate map |
| Mars | Htu | layered, possible aeolian or pyroclastic deposits | Retain `su` and `py` as hypotheses. Leave score unavailable |
| Mars | HNhu | undivided ancient highlands | Leave score unavailable |
| Moon | Em | basaltic mare volcanism | Use rubric above |
| Moon | Im2 | basaltic mare volcanism | Use rubric above |
| Moon | Iif | Fra Mauro impact ejecta | A terrestrial impact ejecta deposit is the closest process analog. The Ries comparison is documented by USGS |
| Moon | Nbm | impact-basin massif | Require independently mapped basin uplift for a process analog |
| Moon | Ip | Imbrian plains, origin uncertain at this level | Leave score unavailable |

Sources: [GLiM methods](https://doi.org/10.1029/2012GC004370), [USGS Mars SIM3292 legend](https://repository.si.edu/server/api/core/bitstreams/9f9936a8-bb2a-4a21-b00b-6977fe03ed4c/content), [USGS Unified Moon map](https://repository.hou.usra.edu/handle/20.500.11753/1598), [USGS Fra Mauro and Ries comparison](https://www.usgs.gov/publications/geologic-implications-apollo-14-fra-mauro-breccias-and-comparison-ejecta-ries-crater), and [USGS igneous rock classification](https://www.usgs.gov/faqs/what-are-igneous-rocks).

## Proposed scoring

Start with chemistry 45%, terrain 45% and mapped geology 10%. With solar enabled, use chemistry 40%, terrain 40%, solar 10% and mapped geology 10%. Set each inactive group's weight to zero and proportionally redistribute its share to active groups before ranking. Compute an RMS of standardized differences within a numeric group, then map its magnitude to `d/(1+d)`. For solar use the absolute difference between the raw horizontal projection values, already in [0,1]. Use the table directly for geology.

Geology-scored runs use known Earth map codes on all included candidates. For a target without a defensible row in the rubric, turn geology off for the whole run. Offer a separate chemistry/terrain ranking including sites without map coverage, and report eligible counts for both modes. Preserve missing, mixed and known-unmatched as distinct states. It is safe to collapse the latter to a display label while retaining original codes. The [analog explorer](app/index.html) implements these heuristic penalties for first-pass screening. They have no empirical calibration.
