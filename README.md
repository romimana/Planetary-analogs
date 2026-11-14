# Planetary Analogs · Mars data baseline

NASA Space Apps 2026 · [Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars](https://www.spaceappschallenge.org/2026/challenges/permanent-moon-base-locations-and-mars/)

This release organizes Mars reference measurements for a future search for terrestrial analogs. It contains 20 named sites and sub-sites, 340 Jezero terrain cells, 1,743 chemistry records, 4,745 Gale outreach weather reports, and a separate inventory of 385,049 cataloged craters. Lunar and Earth datasets and analog rankings are pending.

## Reproduce

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
