PRAGMA foreign_keys=ON;
CREATE TABLE sources(
 id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
 product_id TEXT, file_sha256 TEXT, use_note TEXT NOT NULL
);
CREATE TABLE areas(
 id TEXT PRIMARY KEY, body TEXT NOT NULL DEFAULT 'Mars', name TEXT NOT NULL,
 kind TEXT NOT NULL, mission TEXT, parent_id TEXT REFERENCES areas,
 latitude_deg REAL CHECK(latitude_deg BETWEEN -90 AND 90),
 longitude_e_deg REAL CHECK(longitude_e_deg>=0 AND longitude_e_deg<360),
 geometry_role TEXT NOT NULL, coordinate_note TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources
);
CREATE TABLE time_windows(
 id TEXT PRIMARY KEY, area_id TEXT NOT NULL REFERENCES areas,
 kind TEXT NOT NULL, sol INTEGER, start_utc TEXT, end_utc TEXT, report_date TEXT,
 ls_deg REAL, ls_start_deg REAL, ls_end_deg REAL, sample_count INTEGER,
 time_standard TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources
);
CREATE TABLE samples(
 id TEXT PRIMARY KEY, area_id TEXT NOT NULL REFERENCES areas,
 target TEXT NOT NULL, method TEXT NOT NULL, material TEXT, preparation_code TEXT,
 sol INTEGER, local_time_original TEXT, easting_m REAL, northing_m REAL,
 elevation_m_original REAL, quality TEXT, duplicate_status TEXT,
 source_id TEXT NOT NULL REFERENCES sources, record_locator TEXT NOT NULL,
 integration_hours REAL, instrument_norm REAL, fit_type TEXT,
 stratigraphy TEXT
);
CREATE TABLE observations(
 id INTEGER PRIMARY KEY, area_id TEXT NOT NULL REFERENCES areas,
 sample_id TEXT REFERENCES samples, window_id TEXT REFERENCES time_windows,
 parameter TEXT NOT NULL, value REAL, value_text TEXT, unit TEXT,
 uncertainty REAL, uncertainty_kind TEXT, evidence TEXT NOT NULL,
 spatial_support TEXT NOT NULL, baseline_m REAL,
 depth_top_m REAL, depth_bottom_m REAL,
 source_id TEXT NOT NULL REFERENCES sources, record_locator TEXT NOT NULL,
 note TEXT,
 CHECK((value IS NULL) != (value_text IS NULL)),
 CHECK(depth_top_m IS NULL OR depth_bottom_m IS NULL OR depth_top_m<=depth_bottom_m)
);
CREATE TABLE assets(
 area_id TEXT NOT NULL REFERENCES areas, title TEXT NOT NULL,
 kind TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources, locator TEXT,
 PRIMARY KEY(area_id,title)
);
CREATE TABLE footprints(
 area_id TEXT PRIMARY KEY REFERENCES areas, native_crs TEXT NOT NULL,
 axis_order TEXT NOT NULL, vertical_reference TEXT, footprint_wkt TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources, raster_pixels INTEGER NOT NULL,
 valid_pixels INTEGER NOT NULL, slope_pixels INTEGER NOT NULL
);
CREATE TABLE craters(
 crater_id TEXT PRIMARY KEY, latitude_deg REAL NOT NULL, longitude_e_deg REAL NOT NULL,
 diameter_km REAL NOT NULL, diameter_fit_sd_km REAL,
 ellipse_major_km REAL, ellipse_minor_km REAL, rim_arc_fraction REAL,
 interior_morphology TEXT, ejecta_morphology TEXT,
 source_id TEXT NOT NULL REFERENCES sources
) WITHOUT ROWID;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
