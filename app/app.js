"use strict";
const data = JSON.parse(document.querySelector("#app-data").textContent);
const byId = id => document.getElementById(id);
const form = byId("controls");
const targetSelect = byId("target");
const solarToggle = byId("use-solar");
const groupLabels = {chemistry: "Chemistry", terrain: "Terrain", geology: "Mapped geology", solar: "Sunlight"};
const countries = {AUS: "Australia", JPN: "Japan", USA: "United States", IRL: "Ireland"};
const featureDefinitions = [...chemistry, ...terrain];
const formatScore = value => value.toFixed(3);
const coordinates = row => `${row.latitude.toFixed(4)}°, ${row.longitude.toFixed(4)}°`;
const displayTime = stamp => stamp.replace("T", " ").replace(":00Z", "Z");
let body = "mars";
let result = {ranked: []};
let shortlist = [];
let selected = 0;
let zoom = false;
const map = L.map("map", {minZoom: 1, maxZoom: 19, zoomControl: true}).setView([15, 100], 2);
map.attributionControl.setPrefix(false);
L.geoJSON(data.land, {interactive: false, style: {color: "#52657b", weight: 1, fillColor: "#2b3a4e", fillOpacity: .9}}).addTo(map);
map.attributionControl.addAttribution("Natural Earth");
const markers = L.layerGroup().addTo(map);
map.createPane("detailTiles").style.zIndex = 450;
const detailTiles = /^https?:/.test(location.protocol) ? L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  pane: "detailTiles", maxNativeZoom: 19, maxZoom: 19,
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}) : null;
const presets = {mixed: [35, 40, 25, 10], chemistry: [55, 20, 25, 10], terrain: [20, 55, 25, 10]};
let activeSettings;
let activeTarget;
let activeBody;

function el(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function selectOptions(select, rows, value, label, preferred) {
  select.replaceChildren(...rows.map((r, i) => {
    const option = el("option", label(r));
    option.value = value(r, i);
    return option;
  }));
  if (preferred !== undefined) select.value = preferred;
}

function currentTarget() {
  return data[body].rows.find(row => row.id === targetSelect.value);
}

function updateSettings() {
  const target = currentTarget();
  const supported = geologyColumn(body, target.geology_unit) !== null;
  const geography = target.geology_description || "Map unit unavailable";
  byId("target-context").textContent = `${geography} · ${target.location_role}`;
  form.elements.geology.disabled = !supported;
  byId("geology-note").textContent = supported ?
    "Geology compares regional map units. Review the original map labels in each result." :
    "No comparable geology score for this target. Active weights will be normalized.";
  byId("solar-options").hidden = !solarToggle.checked;
  form.elements.solar.disabled = !solarToggle.checked;
}

function setBody(next) {
  body = next;
  document.querySelectorAll("[data-body]").forEach(button =>
    button.setAttribute("aria-pressed", button.dataset.body === body));
  const preferred = body === "mars" ? "gusev:11" : "apollo12:soil16:line 12";
  selectOptions(targetSelect, data[body].rows, row => row.id,
    row => `${row.area} · ${row.name} · ${row.id}`, preferred);
  selectOptions(byId("target-time"), data[body].times, (_, i) => i, displayTime);
  updateSettings();
  rank();
}

function readSettings() {
  return {
    weights: Object.fromEntries(groups.map(key => [key, Number(form.elements[key].value) || 0])),
    useSolar: solarToggle.checked,
    region: byId("region").value,
    targetTime: Number(byId("target-time").value),
    earthTime: Number(byId("earth-time").value),
    chemIndices: Array.from(document.querySelectorAll("#chem-options input:checked"), x => Number(x.value))
  };
}

function rank() {
  if (!form.reportValidity()) return;
  activeSettings = readSettings();
  activeTarget = currentTarget();
  activeBody = body;
  result = rankAnalogs(data, body, activeTarget, activeSettings);
  shortlist = result.ranked.slice(0, 10);
  selected = 0;
  zoom = false;
  const coverage = Object.entries(result.eligibleByRegion || {}).map(([iso, n]) => `${countries[iso] || iso} ${n.toLocaleString("en-US")}`).join(" · ");
  byId("regional-coverage").textContent = coverage ? `Eligible by region · ${coverage}` : "";
  byId("results-status").textContent = result.error || (!shortlist.length ? "No eligible sites in this region." :
    `Top ${shortlist.length} of ${result.ranked.length.toLocaleString("en-US")} eligible Earth sites · ${activeTarget.name}`);
  renderResults();
  renderSelected();
  fitMap();
}

function renderResults() {
  const tbody = byId("results");
  tbody.replaceChildren();
  shortlist.forEach((resultRow, index) => {
    const {row, score} = resultRow;
    const line = el("tr", undefined, "result-row");
    line.classList.toggle("is-active", index === selected);
    const button = el("button", row.id, "site-button");
    button.type = "button";
    button.setAttribute("aria-pressed", index === selected);
    button.addEventListener("click", () => selectCandidate(index));
    line.append(el("td", String(index + 1).padStart(2, "0"), "rank"));
    const site = el("td");
    site.append(button);
    const position = el("td", countries[row.region] || row.region);
    position.append(el("span", coordinates(row), "site-position"));
    line.append(site, position, el("td", formatScore(score), "metric"));
    tbody.append(line);
  });
}

function selectCandidate(index) {
  selected = index;
  document.querySelectorAll(".result-row").forEach((line, i) => {
    line.classList.toggle("is-active", i === index);
    line.querySelector("button").setAttribute("aria-pressed", i === index);
  });
  if (zoom) focusMap();
  else renderSelected();
}

function groupCards(match) {
  return groups.map(key => {
    const card = el("article");
    const metric = match.distances[key];
    const weight = result.weights[key];
    card.append(el("span", groupLabels[key]), el("strong", metric === null ? "—" : formatScore(metric)));
    card.append(el("small", metric === null ? "Inactive" :
      `${Math.round(weight * 100)}% weight · +${formatScore(metric * weight)}`));
    return card;
  });
}

function sourceLink(label, href) {
  const a = el("a", `${label} ↗`);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function formattedFeature(index, value) {
  const unit = featureDefinitions[index][1];
  const shown = (index === 8 || index === 11) ? value * 100 : value;
  return `${shown.toFixed(2)} ${unit}`;
}

function detailLine(label, target, candidate, distance) {
  const tr = el("tr");
  [label, target, candidate, distance].forEach((value, i) => tr.append(el("td", value, i === 3 ? "metric" : "")));
  return tr;
}

function geologyLabel(row) {
  return row.geology_unit ? `${row.geology_description} (${row.geology_unit}) · ${row.geology_product}` : "Unavailable";
}

function renderSelected() {
  const match = shortlist[selected];
  byId("candidate-detail").hidden = !match;
  byId("map-focus").disabled = !match;
  byId("map-overview").setAttribute("aria-pressed", !zoom);
  byId("map-focus").setAttribute("aria-pressed", zoom);
  byId("earth-link").hidden = !match;
  byId("osm-link").hidden = !match;
  byId("download-kml").hidden = !match;
  byId("coordinates").textContent = "";
  byId("map-status").textContent = match ? `Selected · ${match.row.id}` : "No candidates to map.";
  if (match) {
    const {row, distances} = match;
    byId("coordinates").textContent = `${countries[row.region] || row.region} · ${coordinates(row)}`;
    byId("osm-link").href = `https://www.openstreetmap.org/?mlat=${row.latitude}&mlon=${row.longitude}#map=15/${row.latitude}/${row.longitude}`;
    byId("earth-link").href = `https://earth.google.com/web/search/${encodeURIComponent(`${row.latitude},${row.longitude}`)}`;
    byId("detail-subtitle").textContent = `${row.id} · ${row.material}`;
    byId("breakdown").className = "breakdown";
    byId("breakdown").replaceChildren(...groupCards(match));
    const lines = match.featureDistances.map(([index, distance]) => detailLine(
      featureDefinitions[index][0], formattedFeature(index, activeTarget.values[index]),
      formattedFeature(index, row.values[index]), `${formatScore(distance)} scaled`
    ));
    lines.push(detailLine("Scored map units", geologyLabel(activeTarget), geologyLabel(row),
      distances.geology === null ? "—" : formatScore(distances.geology)));
    const bedrock = data.irishBedrock.rows[row.site_id];
    if (bedrock) {
      const [, unit, stratigraphy, lithology, name, description] = bedrock;
      const codes = [unit, stratigraphy, lithology].filter(Boolean).join(" / ");
      lines.push(detailLine("Irish bedrock reference", "—", `${name} · ${description} (${codes})`, "Reference"));
    }
    if (distances.solar !== null) {
      const targetSun = activeTarget.solar[activeSettings.targetTime];
      const earthSun = row.solar[activeSettings.earthTime];
      const time = (value, stamp) => `${value.toFixed(3)} · ${displayTime(stamp)}`;
      lines.push(detailLine("Horizontal solar projection", time(targetSun, data[activeBody].times[activeSettings.targetTime]),
        time(earthSun, data.earth.times[activeSettings.earthTime]), formatScore(distances.solar)));
    }
    byId("feature-details").replaceChildren(...lines);
    const sources = [row.chemistry_source_url ?
      sourceLink(`Chemistry source · ${row.source_id}`, row.chemistry_source_url) :
      el("span", `Chemistry source · ${row.source_id}`)];
    if (row.geology_url) sources.push(sourceLink("Earth geology source", row.geology_url));
    if (activeTarget.geology_url) sources.push(sourceLink("Target geology source", activeTarget.geology_url));
    if (bedrock) sources.push(sourceLink(`Irish bedrock · polygon record ${bedrock[0]}`, data.irishBedrock.url));
    if (data.radar[row.site_id]) sources.push(sourceLink("CSA RADARSAT-1 scene", data.radar[row.site_id].source));
    byId("candidate-sources").replaceChildren(...sources);
  }
  drawMap();
}

function drawMap() {
  markers.clearLayers();
  shortlist.forEach(({row}, index) => {
    const marker = L.marker([row.latitude, row.longitude], {
      title: `Rank ${index + 1}, ${row.id}`,
      riseOnHover: true,
      zIndexOffset: index === selected ? 500 : 0,
      icon: L.divIcon({
        className: `map-pin ${index === selected ? "selected-pin" : ""}`,
        html: String(index + 1), iconSize: [25, 25], iconAnchor: [12, 12]
      })
    }).addTo(markers);
    marker.on("click", () => selectCandidate(index));
  });
}

function fitMap() {
  if (detailTiles && map.hasLayer(detailTiles)) map.removeLayer(detailTiles);
  if (shortlist.length) {
    map.fitBounds(L.latLngBounds(shortlist.map(({row}) => [row.latitude, row.longitude])),
      {padding: [35, 35], maxZoom: 7, animate: false});
  }
}

function focusMap() {
  if (!shortlist.length) return;
  zoom = true;
  const row = shortlist[selected].row;
  map.setView([row.latitude, row.longitude], 12, {animate: false});
  if (detailTiles && !map.hasLayer(detailTiles)) detailTiles.addTo(map);
  renderSelected();
}

byId("earth-count").textContent = new Set(data.earth.rows.map(row => row.site_id)).size.toLocaleString("en-US");
for (const key of ["mars", "moon"]) byId(`${key}-count`).textContent = data[key].rows.length.toLocaleString("en-US");
chemistry.forEach(([name], index) => {
  const label = el("label", undefined, "checkbox");
  const check = el("input");
  check.type = "checkbox";
  check.value = index;
  check.checked = index > 0 && index < 5;
  label.append(check, document.createTextNode(name));
  byId("chem-options").append(label);
});
byId("chem-options").addEventListener("change", rank);
selectOptions(byId("earth-time"), data.earth.times, (_, i) => i, displayTime, "1");
document.querySelectorAll("[data-body]").forEach(button =>
  button.addEventListener("click", () => setBody(button.dataset.body)));
targetSelect.addEventListener("change", () => {updateSettings(); rank();});
solarToggle.addEventListener("change", () => {
  updateSettings();
  const profile = byId("weight-profile");
  if (profile.value !== "custom") profile.dispatchEvent(new Event("change"));
});
form.addEventListener("submit", event => { event.preventDefault(); rank(); });
byId("map-overview").addEventListener("click", () => { zoom = false; renderSelected(); fitMap(); });
byId("map-focus").addEventListener("click", focusMap);
byId("download-kml").addEventListener("click", () => {
  const match = shortlist[selected];
  if (!match) return;
  const ns = "http://www.opengis.net/kml/2.2";
  const xml = document.implementation.createDocument(ns, "kml");
  const placemark = xml.createElementNS(ns, "Placemark");
  const name = xml.createElementNS(ns, "name");
  const point = xml.createElementNS(ns, "Point");
  const coordinate = xml.createElementNS(ns, "coordinates");
  name.textContent = match.row.id;
  coordinate.textContent = `${match.row.longitude},${match.row.latitude},0`;
  point.append(coordinate);
  placemark.append(name, point);
  xml.documentElement.append(placemark);
  const blob = new Blob([new XMLSerializer().serializeToString(xml)], {type: "application/vnd.google-earth.kml+xml"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "planetary-analog.kml";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
new ResizeObserver(() => map.invalidateSize()).observe(byId("map"));
const regionOptions = [...new Set(data.earth.rows.map(row => row.region))].sort((a, b) =>
  (countries[a] || a).localeCompare(countries[b] || b));
selectOptions(byId("region"), ["", ...regionOptions], x => x, x => x ? countries[x] || x : "All eligible regions");
byId("region").addEventListener("change", rank);
byId("weight-profile").addEventListener("change", event => {
  const weights = presets[event.target.value];
  if (!weights) return;
  groups.forEach((key, i) => {
    form.elements[key].value = weights[i] - (solarToggle.checked && i < 2 ? 5 : 0);
  });
  rank();
});
for (const key of groups) {
  form.elements[key].addEventListener("input", () => { byId("weight-profile").value = "custom"; });
}
setBody(body);
