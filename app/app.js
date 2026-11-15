"use strict";
const data = JSON.parse(document.querySelector("#app-data").textContent);
const byId = id => document.getElementById(id);
const form = byId("controls");
const targetSelect = byId("target");
const solarToggle = byId("use-solar");
const groupLabels = {chemistry: "Chemistry", terrain: "Terrain", geology: "Mapped geology", solar: "Sunlight"};
const countries = {AUS: "Australia", JPN: "Japan"};
const featureDefinitions = [...chemistry, ...terrain];
const formatScore = value => value.toFixed(3);
const coordinates = row => `${row.latitude.toFixed(4)}°, ${row.longitude.toFixed(4)}°`;
const displayTime = stamp => stamp.replace("T", " ").replace(":00Z", "Z");
let body = "mars";
let result = {ranked: []};
let shortlist = [];
let selected = 0;
let zoom = false;
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
    "Geology uses the map-unit rubric." : "No comparable geology score for this target. Active weights will be normalized.";
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
  byId("results-status").textContent = result.error ||
    `Top ${shortlist.length} of ${result.ranked.length.toLocaleString("en-US")} eligible Earth sites · ${activeTarget.name}`;
  renderResults();
  renderSelected();
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
  renderSelected();
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

function renderSelected() {
  const match = shortlist[selected];
  byId("candidate-detail").hidden = !match;
  byId("map-focus").disabled = !match;
  byId("map-overview").setAttribute("aria-pressed", !zoom);
  byId("map-focus").setAttribute("aria-pressed", zoom);
  byId("earth-link").hidden = !match;
  byId("download-kml").hidden = !match;
  byId("coordinates").textContent = "";
  byId("map-status").textContent = match ? `Selected · ${match.row.id}` : "No candidates to map.";
  if (match) {
    const {row, distances} = match;
    byId("coordinates").textContent = `${countries[row.region] || row.region} · ${coordinates(row)}`;
    byId("earth-link").href = `https://earth.google.com/web/search/${encodeURIComponent(`${row.latitude},${row.longitude}`)}`;
    byId("detail-subtitle").textContent = `${row.id} · ${row.material}`;
    byId("breakdown").className = "breakdown";
    byId("breakdown").replaceChildren(...groupCards(match));
    const lines = match.featureDistances.map(([index, distance]) => detailLine(
      featureDefinitions[index][0], formattedFeature(index, activeTarget.values[index]),
      formattedFeature(index, row.values[index]), `${formatScore(distance)} scaled`
    ));
    lines.push(detailLine("Mapped geology", activeTarget.geology_description || "Unavailable",
      row.geology_description || "Unavailable", distances.geology === null ? "—" : formatScore(distances.geology)));
    if (distances.solar !== null) {
      const targetSun = activeTarget.solar[activeSettings.targetTime];
      const earthSun = row.solar[activeSettings.earthTime];
      const time = (value, stamp) => `${value.toFixed(3)} · ${displayTime(stamp)}`;
      lines.push(detailLine("Horizontal solar projection", time(targetSun, data[activeBody].times[activeSettings.targetTime]),
        time(earthSun, data.earth.times[activeSettings.earthTime]), formatScore(distances.solar)));
    }
    byId("feature-details").replaceChildren(...lines);
    const sources = [el("span", `Chemistry source · ${row.source_id}`)];
    if (row.geology_url) sources.push(sourceLink("Earth geology source", row.geology_url));
    if (activeTarget.geology_url) sources.push(sourceLink("Target geology source", activeTarget.geology_url));
    if (data.radar[row.site_id]) sources.push(sourceLink("CSA RADARSAT-1 scene", data.radar[row.site_id].source));
    byId("candidate-sources").replaceChildren(...sources);
  }
  drawMap();
}

function drawMap() {
  const canvas = byId("map-canvas");
  const {width, height} = byId("map").getBoundingClientRect();
  if (!width || !height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const center = zoom && shortlist.length ? shortlist[selected].row : {latitude: 0, longitude: 132};
  const visibleLat = zoom ? 11 : 104;
  const horizontalDegrees = Math.min(360, visibleLat * width / height);
  const scale = Math.min(height / visibleLat, width / horizontalDegrees);
  const project = (lon, lat) => {
    const delta = ((lon - center.longitude + 540) % 360) - 180;
    return [width / 2 + delta * scale, height / 2 - (lat - center.latitude) * scale];
  };
  ctx.fillStyle = "#101927";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#253449";
  ctx.lineWidth = 1;
  ctx.beginPath();
  const gridStep = zoom ? 2 : 15;
  for (let lon = -180; lon < 180; lon += gridStep) {
    const [x] = project(lon, 0);
    ctx.moveTo(x, 0);ctx.lineTo(x, height);
  }
  for (let lat = -90; lat <= 90; lat += gridStep) {
    const y = project(0, lat)[1];
    ctx.moveTo(0, y);ctx.lineTo(width, y);
  }
  ctx.stroke();
  ctx.fillStyle = "#283546";
  ctx.strokeStyle = "#52657b";
  for (const geometry of data.land) {
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    for (const polygon of polygons) {
      // Overview is centered on East Asia and Australia. Omit paths crossing its back meridian.
      const projected = polygon.map(ring => ring.map(([lon, lat]) => project(lon, lat)));
      if (projected[0].some(([x], i, ring) => i && Math.abs(x - ring[i-1][0]) > 180 * scale)) continue;
      ctx.beginPath();
      for (const ring of projected) {
        ring.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
        ctx.closePath();
      }
      ctx.fill("evenodd");
      ctx.stroke();
    }
  }
  const pins = [];
  shortlist.forEach(({row}, index) => {
    const [x, y] = project(row.longitude, row.latitude);
    if (x < 0 || x > width || y < 0 || y > height) return;
    const pin = el("button", String(index + 1), "pin");
    pin.type = "button";
    pin.style.left = `${x}px`;
    pin.style.top = `${y}px`;
    pin.setAttribute("aria-label", `Rank ${index + 1}, ${row.id}`);
    pin.setAttribute("aria-pressed", index === selected);
    pin.addEventListener("click", () => {
      selectCandidate(index);
      byId("map-focus").focus();
    });
    pins.push(pin);
  });
  byId("map-pins").replaceChildren(...pins);
}

for (const key of ["earth", "mars", "moon"]) byId(`${key}-count`).textContent = data[key].rows.length.toLocaleString("en-US");
chemistry.forEach(([name], index) => {
  const label = el("label", undefined, "checkbox");
  const check = el("input");
  check.type = "checkbox";
  check.value = index;
  check.checked = index > 0 && index < 5;
  label.append(check, document.createTextNode(name));
  byId("chem-options").append(label);
});
selectOptions(byId("earth-time"), data.earth.times, (_, i) => i, displayTime, "1");
document.querySelectorAll("[data-body]").forEach(button =>
  button.addEventListener("click", () => setBody(button.dataset.body)));
targetSelect.addEventListener("change", () => {updateSettings(); rank();});
solarToggle.addEventListener("change", () => {
  const chemistryWeight = form.elements.chemistry;
  const terrainWeight = form.elements.terrain;
  const standardWeight = solarToggle.checked ? "45" : "40";
  if (chemistryWeight.value === standardWeight && terrainWeight.value === standardWeight) {
    chemistryWeight.value = terrainWeight.value = solarToggle.checked ? "40" : "45";
  }
  updateSettings();
});
form.addEventListener("submit", event => { event.preventDefault(); rank(); });
byId("map-overview").addEventListener("click", () => { zoom = false; renderSelected(); });
byId("map-focus").addEventListener("click", () => { zoom = true; renderSelected(); });
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
new ResizeObserver(drawMap).observe(byId("map"));
setBody(body);
