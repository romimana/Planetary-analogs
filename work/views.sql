CREATE INDEX observation_area_parameter ON observations(area_id,parameter);
CREATE INDEX observation_sample ON observations(sample_id);
CREATE INDEX observation_window ON observations(window_id);
CREATE INDEX windows_area ON time_windows(area_id,kind);
CREATE INDEX crater_diameter ON craters(diameter_km);
CREATE INDEX crater_coordinates ON craters(latitude_deg,longitude_e_deg);
CREATE VIEW science_observations AS
 SELECT * FROM observations WHERE evidence NOT IN ('outreach summary','derived from outreach data');
CREATE VIEW area_coverage AS
 SELECT a.id,a.name,a.kind,a.mission,a.latitude_deg,a.longitude_e_deg,
  (SELECT COUNT(*) FROM samples s WHERE s.area_id=a.id) AS chemistry_samples,
  (SELECT COUNT(*) FROM science_observations o WHERE o.area_id=a.id) AS science_values,
  (SELECT COUNT(*) FROM time_windows w WHERE w.area_id=a.id AND w.kind='daily outreach report') AS outreach_sols,
  (SELECT COUNT(*) FROM assets m WHERE m.area_id=a.id) AS linked_assets
 FROM areas a;
CREATE VIEW observation_provenance AS
 SELECT o.*, a.name AS area_name, sa.target, sa.method, sa.material, sa.preparation_code,
        sa.quality, sa.duplicate_status, COALESCE(sa.sol,w.sol) AS sol, w.ls_deg, w.report_date,
        s.title AS source_title, s.url AS source_url, s.product_id
 FROM observations o JOIN areas a ON a.id=o.area_id JOIN sources s ON s.id=o.source_id
 LEFT JOIN samples sa ON sa.id=o.sample_id LEFT JOIN time_windows w ON w.id=o.window_id;
