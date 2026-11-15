"use strict";
const chemistry = [
  ["Silica", "wt%"], ["Titanium dioxide", "wt%"], ["Magnesium oxide", "wt%"],
  ["Calcium oxide", "wt%"], ["Potassium oxide", "wt%"], ["Manganese oxide", "wt%"]
];
const terrain = [
  ["Median slope", "°"], ["90th percentile slope", "°"], ["Area steeper than 10°", "%"],
  ["Elevation relief", "m"], ["Local roughness", "m"], ["Largest connected gentle area", "%"]
];
const groups = ["chemistry", "terrain", "geology", "solar"];

function geologyColumn(body, unit) {
  if (body === "mars" && unit === "eHv") return 1;
  if (body === "moon" && ["Em", "Im2"].includes(unit)) return 0;
  return null;
}

function percentile(sorted, percent) {
  const index = (sorted.length - 1) * percent;
  return sorted[Math.floor(index)] + (index % 1) * (sorted[Math.ceil(index)] - sorted[Math.floor(index)]);
}

function logRatios(values) {
  if (!values.length) return [];
  const logs = values.map(Math.log);
  const average = logs.reduce((a, b) => a + b, 0) / logs.length;
  return logs.map(value => value - average);
}

function daylightScenarios(values, limit = 4) {
  const daylight = values.map((value, index) => ({value, index}))
    .filter(({value}) => Number.isFinite(value) && value > 0)
    .sort((a, b) => a.value - b.value || a.index - b.index)
    .filter(({value}, i, sorted) => i === 0 || value !== sorted[i - 1].value);
  if (daylight.length <= limit) return daylight;
  return Array.from({length: limit}, (_, i) => daylight[Math.round(i * (daylight.length - 1) / (limit - 1))]);
}

function solarMatch(targetWindows, earthValues) {
  let best = null;
  for (const {value, index} of targetWindows) {
    for (let i = 0; i < earthValues.length; i++) {
      const earthSun = earthValues[i];
      if (!Number.isFinite(earthSun) || earthSun <= 0) continue;
      const distance = Math.abs(value - earthSun);
      if (!best || distance < best.distance) best = {distance, targetTime: index, earthTime: i};
    }
  }
  return best;
}

function rankAnalogs(data, body, target, settings) {
  const weights = {...settings.weights};
  const geoColumn = geologyColumn(body, target.geology_unit);
  if (geoColumn === null) weights.geology = 0;
  if (!settings.useSolar) weights.solar = 0;
  const totalWeight = groups.reduce((total, key) => total + weights[key], 0);
  if (!totalWeight) return {ranked: [], weights, geoColumn, error: "Choose at least one available comparison weight."};
  for (const key of groups) weights[key] /= totalWeight;
  const chemIndices = weights.chemistry ? settings.chemIndices : [];
  if (weights.chemistry && chemIndices.length < 2) {
    return {ranked: [], weights, geoColumn, error: "Select at least two chemistry components to compare their ratios."};
  }
  const terrainIndices = weights.terrain ? [6, 7, 8, 9, 10, 11] : [];
  const indices = [...chemIndices, ...terrainIndices];
  const vector = (row, subset, compositional) => {
    const raw = subset.map(index => row.values[index]);
    if (raw.some(v => !Number.isFinite(v) || (compositional && v <= 0))) return null;
    return compositional ? logRatios(raw) : raw;
  };
  const targetChem = vector(target, chemIndices, true);
  const targetTerrain = vector(target, terrainIndices, false);
  if (!targetChem || !targetTerrain) return {ranked: [], weights, geoColumn, error: "The target lacks a selected feature."};
  const targetVector = [...targetChem, ...targetTerrain];
  const numericCandidates = data.earth.rows.map(row => {
    return {row, chem: vector(row, chemIndices, true), terrain: vector(row, terrainIndices, false),
            geology: data.rubric[row.geology_unit]?.[geoColumn]};
  });
  const targetWindows = weights.solar ? daylightScenarios(target.solar) : [];
  if (weights.solar && !targetWindows.length) {
    return {ranked: [], weights, geoColumn, error: "No sunlit reference time exists for this target."};
  }
  if (weights.solar) for (const candidate of numericCandidates) {
    candidate.sun = solarMatch(targetWindows, candidate.row.solar);
  }
  const candidates = numericCandidates.filter(({chem, terrain, geology, sun}) =>
    chem && terrain && (!weights.geology || Number.isFinite(geology)) && (!weights.solar || sun));
  if (!candidates.length) return {ranked: [], weights, geoColumn, error: "No Earth candidates meet the selected requirements."};

  const scale = indices.map((_, i) => {
    const sorted = numericCandidates.flatMap(c => {
      const v = i < chemIndices.length ? c.chem?.[i] : c.terrain?.[i - chemIndices.length];
      return Number.isFinite(v) ? [v] : [];
    }).sort((a, b) => a - b);
    const iqr = percentile(sorted, 0.75) - percentile(sorted, 0.25);
    return iqr > 1e-12 ? iqr : 1;
  });
  const ranked = candidates.map(candidate => {
    const standardized = [...candidate.chem, ...candidate.terrain]
      .map((value, i) => Math.abs(value - targetVector[i]) / scale[i]);
    const rms = values => values.length ? Math.sqrt(values.reduce((sum, v) => sum + v * v, 0) / values.length) : 0;
    const bounded = value => value / (1 + value);
    const solar = weights.solar ? candidate.sun.distance : null;
    const distances = {
      chemistry: weights.chemistry ? bounded(rms(standardized.slice(0, chemIndices.length))) : null,
      terrain: weights.terrain ? bounded(rms(standardized.slice(chemIndices.length))) : null,
      geology: weights.geology ? candidate.geology : null,
      solar
    };
    const score = groups.reduce((sum, key) => sum + (distances[key] ?? 0) * weights[key], 0);
    return {...candidate, score, distances, featureDistances: indices.map((index, i) => [index, standardized[i]])};
  });
  ranked.sort((a, b) => a.score - b.score || a.row.id.localeCompare(b.row.id));
  const eligibleByRegion = {};
  const sites = new Set();
  const rankedSites = ranked.filter(({row}) => {
    if (settings.pool && Boolean(row.terrain_url) !== (settings.pool === "terrain")) return false;
    if (sites.has(row.site_id)) return false;
    sites.add(row.site_id);
    eligibleByRegion[row.region] = (eligibleByRegion[row.region] || 0) + 1;
    return true;
  });
  return {ranked: settings.region ? rankedSites.filter(item => item.row.region === settings.region) : rankedSites,
          weights, geoColumn, eligibleByRegion,
          error: !rankedSites.length && settings.pool === "terrain" && weights.chemistry ?
            "Terrain survey windows have no lab assays. Use Terrain only or choose lab sample locations." : null};
}

if (typeof module !== "undefined") module.exports = {rankAnalogs, geologyColumn, daylightScenarios, solarMatch};
