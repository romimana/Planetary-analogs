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
  const indices = [...chemIndices, ...(weights.terrain ? [6, 7, 8, 9, 10, 11] : [])];
  const vector = row => {
    const raw = indices.map(index => row.values[index]);
    if (raw.some((v, i) => !Number.isFinite(v) || (i < chemIndices.length && v <= 0))) return null;
    return [...logRatios(raw.slice(0, chemIndices.length)), ...raw.slice(chemIndices.length)];
  };
  const targetVector = vector(target);
  if (!targetVector) return {ranked: [], weights, geoColumn, error: "The target lacks a selected feature."};
  const numericCandidates = data.earth.rows.flatMap(row => {
    const values = vector(row);
    return values ? [{row, values, geology: data.rubric[row.geology_unit]?.[geoColumn]}] : [];
  });
  const targetSun = target.solar[settings.targetTime];
  const candidates = numericCandidates.filter(({row, geology}) =>
    (!weights.geology || Number.isFinite(geology)) &&
    (!weights.solar || (Number.isFinite(row.solar[settings.earthTime]) && Number.isFinite(targetSun))));
  if (!candidates.length) return {ranked: [], weights, geoColumn, error: "No Earth candidates meet the selected requirements."};

  const scale = indices.map((_, i) => {
    const sorted = numericCandidates.map(c => c.values[i]).sort((a, b) => a - b);
    const iqr = percentile(sorted, 0.75) - percentile(sorted, 0.25);
    return iqr > 1e-12 ? iqr : 1;
  });
  const ranked = candidates.map(candidate => {
    const standardized = candidate.values.map((value, i) => Math.abs(value - targetVector[i]) / scale[i]);
    const rms = values => values.length ? Math.sqrt(values.reduce((sum, v) => sum + v * v, 0) / values.length) : 0;
    const bounded = value => value / (1 + value);
    const solar = weights.solar ? Math.abs(candidate.row.solar[settings.earthTime] - targetSun) : null;
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
    if (sites.has(row.site_id)) return false;
    sites.add(row.site_id);
    eligibleByRegion[row.region] = (eligibleByRegion[row.region] || 0) + 1;
    return true;
  });
  return {ranked: settings.region ? rankedSites.filter(item => item.row.region === settings.region) : rankedSites,
          weights, geoColumn, eligibleByRegion};
}

if (typeof module !== "undefined") module.exports = {rankAnalogs, geologyColumn};
