"use strict";

// Run from the repository root after build_app.py, then rebuild to embed the report.
const fs = require("node:fs");
const {rankAnalogs} = require("./ranking.js");
const data = JSON.parse(fs.readFileSync("app/index.html", "utf8").split('id="app-data">')[1].split("</script>")[0]);
const profiles = {
  "terrain-only": [0,100,0], mixed: [35,40,25], geochemistry: [55,20,25], "terrain-oriented": [20,55,25]
};

function evaluate(body, target) {
  const runs = Object.entries(profiles).map(([name, [chemistry, terrain, geology]]) => {
    const result = rankAnalogs(data, body, target, {
      weights: {chemistry, terrain, geology, solar: 0}, chemIndices: [1,2,3,4], useSolar: false
    });
    const top = result.ranked.slice(0, 10);
    return {name, regions: [...new Set(top.map(({row}) => row.region))], first: top[0]?.row.id,
      firstRegion: top[0]?.row.region};
  });
  const coverage = Math.min(...runs.map(run => run.regions.length));
  const union = new Set(runs.flatMap(run => run.regions)).size;
  const firstRegions = new Set(runs.map(run => run.firstRegion).filter(Boolean)).size;
  const firstSites = new Set(runs.map(run => run.first).filter(Boolean)).size;
  return {id: target.id, area: target.area, name: target.name, coverage, union, firstRegions, firstSites, runs};
}

const reports = {};
for (const body of ["mars","moon"]) {
  const candidates = data[body].rows.filter(target => target.comparison_status !== "chemistry_hold")
    .map(target => evaluate(body, target))
    .filter(row => row.coverage >= 2 && row.firstRegions >= 2)
    .sort((a,b) => b.coverage-a.coverage || b.firstRegions-a.firstRegions ||
      b.union-a.union || b.firstSites-a.firstSites || a.id.localeCompare(b.id));
  const seen = new Set();
  reports[body] = candidates.filter(row => {
    if (seen.has(row.area)) return false;
    seen.add(row.area);
    return true;
  }).slice(0,3);
  console.log(body, reports[body].map(({name, area, coverage, union, firstRegions}) =>
    ({name, area, coverage, union, firstRegions})));
}
fs.writeFileSync("data/recommended-samples.json", JSON.stringify(reports, null, 2) + "\n");
