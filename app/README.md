# Planetary Analogs explorer

Open `index.html` in a browser. Choose a planetary target. Terrain only is the default. Mixed, Geochemistry-oriented and Terrain-oriented start with 25% for mapped geology where supported, and individual weights remain editable. Use the Earth sites filter to inspect the [survey windows](../TERRAIN_SURVEY.md) or the lab-sample locations. Choose a result to see feature distances, weighted group contributions, the original map labels and its map location. Use the zoom controls or scroll and drag the map. Focus centers the selected site. When served over HTTP or HTTPS, Focus also loads OpenStreetMap tiles. Opening the file directly uses the bundled Natural Earth coastline, with street-map and Google Earth links plus KML export for geographic detail.

## Rebuild

From the repository root, run `python build_app.py` with the project requirements installed. The builder verifies the public SQLite snapshot and [Earth expansion](../data/earth-expansion.sqlite) checksums, then bundles the HTML, CSS, JavaScript and data. [Expansion coverage](../data/earth-expansion.json) reports samples, unique sites, and valid silica and geology counts. Edit the source files in this directory and rebuild `index.html`. To serve locally, run `python -m http.server 8000 --bind 127.0.0.1 --directory app` and open `http://127.0.0.1:8000`.

## Ranking and sources

- [Data and coverage](../DATA_CODEBOOK.md) defines the features and their spatial support. The ranking calculates distances on demand for the current target. Chemistry uses centered log ratios. Chemistry and terrain use Earth interquartile ranges for scaling and a bounded RMS within each group. The feature table displays the absolute distance in standardized units for those two groups. The group cards display the bounded distance, normalized weight, and weighted contribution.
- [Geology](../GEOLOGY_MATCHING.md) uses the documented rubric. Where unavailable for the selected target, the app normalizes the active weights. If geology is active, Earth candidates must have a mapped class. RADARSAT-1 scene links are shown for candidates with those historical observations.
- Solar uses the absolute difference in the horizontal projection for the selected UTC scenarios. See the [SPICE audit](../data/solar-audit.json). Surface illumination and mapped geology support initial screening.
- Earth region and site pool filter the global score output. Numeric scales fit independently on valid Earth values for each active group across all regions. With chemistry enabled, each ranked row has the selected measured components. The app reports eligible counts by region. The global top ten may all come from a single country. The data include distinct surveyed materials and analytical methods, so use geographic and source coverage in interpreting the rankings.
- Mars image by [NASA/JPL-Caltech](https://science.nasa.gov/resource/mars-planet-globe/). Land polygons from [Natural Earth 1:110m](https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/), release 5.1.2.
- Interactive mapping uses [Leaflet 1.9.4](https://leafletjs.com/reference-1.9.4.html) under its [BSD-2-Clause license](assets/leaflet-LICENSE). Online detail uses © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).

The Irish GSI and USGS additions, selection criteria and provenance are documented in [Earth expansion](../EARTH_EXPANSION.md).
