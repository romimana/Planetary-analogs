# Proposed map-unit crosswalk

This is a proposed ranking rubric for the published sample locations. It describes mapped regional context. Keep `geology_product` and `geology_unit` as the original key and retain the original label and map locator. The numeric values below are heuristic penalties for comparing mapped settings.

| Earth GLiM code | Canonical label | Lunar Em / Im2 | Martian eHv |
| --- | --- | ---: | ---: |
| vb | mafic volcanic | 0.00 | 0.00 |
| vi | intermediate volcanic | 0.35 | 0.15 |
| va | felsic volcanic | 0.55 | 0.25 |
| pb | mafic plutonic | 0.30 | 0.45 |
| pi | intermediate plutonic | 0.60 | 0.55 |
| pa | felsic plutonic | 0.75 | 0.65 |
| py | pyroclastic deposit | 0.65 | 0.35 |
| mt | metamorphic | 0.90 | 0.90 |
| su | unconsolidated sediment | 1.00 | 1.00 |
| ss | siliciclastic sedimentary | 1.00 | 1.00 |
| sm | mixed sedimentary | 1.00 | 1.00 |
| sc | carbonate sedimentary | 1.00 | 1.00 |
| ev | evaporite | 1.00 | 1.00 |

A zero here means strongest available map-class analogy. Lunar mare units support a basaltic interpretation. Mafic plutonic rock shares a broad compositional family with mare basalt but forms by cooling below the surface, so it has a nonzero penalty. The official eHv legend describes plains-forming deposits with a likely volcanic origin. Its penalties favor volcanic settings, with a smaller penalty for intermediate and felsic volcanic units than for intrusive rocks. The eHv class alone gives limited evidence about the actual composition of any given sample. Use the chemistry group to compare measured composition. Surface texture requires evidence at the field scale.

| Body | Unit | Canonical map context | Earth rock-comparison treatment |
| --- | --- | --- | --- |
| Mars | eHv | plains-forming deposits, likely volcanic | Use rubric above |
| Mars | AHi | impact-related unit | Seek verified terrestrial impact context in a separate map |
| Mars | Htu | layered, possible aeolian or pyroclastic deposits | Retain `su` and `py` as hypotheses. Leave score unavailable |
| Mars | HNhu | undivided ancient highlands | Leave score unavailable |
| Moon | Em | basaltic mare volcanism | Use rubric above |
| Moon | Im2 | basaltic mare volcanism | Use rubric above |
| Moon | Iif | Fra Mauro impact ejecta | A terrestrial impact ejecta deposit is the closest process analog. The Ries comparison is documented by USGS |
| Moon | Nbm | impact-basin massif | Require independently mapped basin uplift for a process analog |
| Moon | Ip | Imbrian plains, origin uncertain at this level | Leave score unavailable |

Sources: [GLiM methods](https://doi.org/10.1029/2012GC004370), [USGS Mars SIM3292 legend](https://pubs.usgs.gov/sim/3292/pdf/sim3292_map.pdf), [USGS Unified Moon map](https://repository.hou.usra.edu/handle/20.500.11753/1598), [USGS Fra Mauro and Ries comparison](https://www.usgs.gov/publications/geologic-implications-apollo-14-fra-mauro-breccias-and-comparison-ejecta-ries-crater), and [USGS igneous rock classification](https://www.usgs.gov/faqs/what-are-igneous-rocks).

## Proposed scoring

Mixed starts at chemistry 35%, terrain 40% and mapped geology 25%. The geochemistry and terrain presets assign 55% to the focal group, 20% to the other numeric group, and 25% to mapped geology. With solar enabled, share its 10% equally from the two numeric groups. Set each inactive group's weight to zero and proportionally redistribute its share to active groups before ranking. Center chemistry values as log ratios across selected components. Fit each numeric feature's interquartile range on Earth rows with valid values for the selected numeric features, across all regions. A zero IQR uses a divisor of one. Keep those scales when a change only affects geology or solar eligibility. Compute an RMS of standardized differences within each numeric group, then bound it using `d/(1+d)`. For solar use the absolute difference between the raw horizontal projection values, already in [0,1]. Use the table directly for geology.

The geology score uses the same GLiM grid for all Earth candidates. Its 0.5° cells cover tens of kilometres and represent regional mapped surface lithology. The separate GSI 1:100,000 bedrock polygon is available for Irish sites as a reference. It describes the solid rock under a site and can differ from surficial sediment and from the material carried into a stream. Including it in the same scored field would change both the map scale and the material represented for only one country.

Geology-scored runs use known Earth map codes on all included candidates. For a target without a defensible row in the rubric, turn geology off for the whole run. Offer a separate chemistry/terrain ranking including sites without map coverage, and report eligible counts for both modes. Preserve missing, mixed and known-unmatched as distinct states. It is safe to collapse the latter to a display label while retaining original codes. The [analog explorer](app/index.html) implements these heuristic penalties for first-pass screening. They have no empirical calibration.

## Sensitivity check

The following runs keep the chemistry-to-terrain weight ratio at 35:40 and vary only the geology share. With no solar weighting, the entered geology weights 0, 10, 25, and 40 normalize to 0%, 11.8%, 25%, and 34.8%. All runs with a nonzero geology weight had 15,775 eligible sites without silica and 8,464 with it. The numeric feature distances for common candidates stayed fixed across geology settings.

| Target and silica selection | 0% geology | 11.8% geology | 25% geology | 34.8% geology |
| --- | --- | --- | --- | --- |
| Gusev, off | 1 mafic volcanic | 7 mafic volcanic | 9 mafic volcanic | 10 mafic volcanic |
| Gusev, on | 0 mafic volcanic | 8 mafic volcanic | 10 mafic volcanic | 10 mafic volcanic |
| Apollo 12, off | 2 mafic volcanic | 10 mafic volcanic | 10 mafic volcanic | 10 mafic volcanic |
| Apollo 12, on | 0 mafic volcanic | 9 mafic volcanic | 10 mafic volcanic | 10 mafic volcanic |

Counts describe the top ten. At 25% without silica, Gusev ranks nine Japanese sites and one US site, and Apollo 12 ranks eight Japanese sites and two US sites. With silica at 25%, both rank ten Australian sites. In the current scored pool, Australia has 15 mafic-volcanic samples with silica. Ireland has no such samples under the common map classification. Japan and the US have no eligible silica values. Results measure the behavior of the rubric and the surveyed candidate pool. They provide no independent validation of analog quality.
