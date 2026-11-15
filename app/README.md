# Planetary Analogs explorer

Open `index.html` in a browser. Choose a planetary target, configure weights, and run the ranking. Choose a result to see the feature distances, weighted group contributions, and map location. The map shows the top ten candidates on a Natural Earth overview. The Google Earth link sends the selected coordinates to Google Earth's web search. You can also download the selected point as KML for import.

## Rebuild

From the repository root, run `python build_app.py` with the project requirements installed. The builder verifies the public SQLite snapshot checksum, then bundles the HTML, CSS, JavaScript and data. The bundled public dataset contains 4,024 Earth sites, 137 Mars samples, and 12 lunar samples. Edit the source files in this directory and rebuild `index.html`.

## Ranking and sources

- [Data and coverage](../DATA_CODEBOOK.md) defines the features and their spatial support. The ranking calculates distances on demand for the current target. Chemistry uses centered log ratios. Chemistry and terrain use Earth interquartile ranges for scaling and a bounded RMS within each group. The feature table displays the absolute distance in standardized units for those two groups. The group cards display the bounded distance, normalized weight, and weighted contribution.
- [Geology](../GEOLOGY_MATCHING.md) uses the documented rubric. Where unavailable for the selected target, the app normalizes the active weights. If geology is active, Earth candidates must have a mapped class. RADARSAT-1 scene links are shown for candidates with those historical observations.
- Solar uses the absolute difference in the horizontal projection for the selected UTC scenarios. See the [SPICE audit](../data/solar-audit.json). Surface illumination and mapped geology support initial screening.
- Mars image by [NASA/JPL-Caltech](https://science.nasa.gov/resource/mars-planet-globe/). Land polygons from [Natural Earth 1:110m](https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/), release 5.1.2.
