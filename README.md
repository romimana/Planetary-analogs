# Planetary Analogs · Mars and Moon reference data

NASA Space Apps 2026 · [Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars](https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/)

Start with the [ML dataset and codebook](ML.md). The snapshot includes Earth candidates and Mars and Moon targets, with SQLite views for chemistry, terrain, and environmental comparisons. The source builds below reconstruct the broader inventories.

## Interactive analog explorer

[Deploy to Render](https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fromimana%2FPlanetary-analogs) to create a public URL on the Free web service plan. Paste your [Gemini API key](https://aistudio.google.com/app/apikey) into the Render setup field for `GEMINI_API_KEY`. It stays in the service environment. Once the deploy is live, open the service URL, choose an analog, and click **Explain with Gemini**. For later Git updates, use **Manual Deploy** in the Render dashboard.

Download [app/index.html](app/index.html) from GitHub and open it in a browser. The file bundles the public comparison data, ranking engine, and overview map. Terrain only is the default, with optional measured chemistry and mapped geology. An internet connection is needed to open Google Earth and linked sources. See [the demo guide](app/README.md) and [the terrain survey](TERRAIN_SURVEY.md).

Open [the data exploration notebook in Colab](https://colab.research.google.com/github/romimana/Planetary-analogs/blob/main/explore_data.ipynb) to inspect the SQLite tables with pandas, review missing values, and select comparable features. It loads the latest published snapshot by default. Set `DATA_REF` to a commit SHA for reproducibility.

## Reproduce Mars

Tested with Python 3.12.3 and SQLite 3.45.1. From the repository root:

```sh
python -m pip install -r requirements.txt
python build.py
```

The build verifies source SHA-256 hashes, downloads missing inputs from their original publishers, and writes `outputs/mars.sqlite` and `outputs/Mars Atlas.html`. If the live NASA/CAB feed has changed, place the original 2026-11-14 snapshot named `gale_weather.json` in `work/`. A matching local copy is required for an exact replay; the steps will fail visibly if it differs.

- [Methods and audit queries](METHODS.md)
- [Sources and third-party terms](SOURCES.md)
- [Competition notes and AI disclosure](SUBMISSION.md)

Open the atlas in a browser and start with the coverage table. The SQLite view `observation_provenance` links values to their original file, line, sol or published table.

## Reproduce the Moon

```sh
python -m pip install -r requirements.txt
python work/fetch_moon.py
python work/build_moon.py
```

Outputs are `outputs/moon.sqlite` and `outputs/Moon Atlas.html`. See the [Moon methods and sources](MOON.md) for coverage, calculations, and audit queries.

Run `python audit.py` after both builds. See the [audit and Earth matching plan](AUDIT.md).

[Analog matching pilot](PILOT.md)

[Curated soil references and codebook](CODEBOOK.md)

[Planetary sample context and environmental windows](CONTEXT.md)

[Earth GIS comparison dataset](EARTH.md)
