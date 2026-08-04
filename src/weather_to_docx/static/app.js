"use strict";

const state = {
  diagnostics: null,
  locations: [],
  sources: [],
  jobs: [],
  selectedLocations: new Set(),
  selectedSources: new Set(),
  suggestions: [],
  toastTimer: null,
};

const statusNames = {
  queued: "В очереди",
  running: "Выполняется",
  completed: "Готово",
  partial: "Готово с предупреждениями",
  failed: "Ошибка",
  cancelled: "Отменено",
};

window.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshAll();
  window.setInterval(() => {
    if (!document.hidden) loadJobs().catch(reportError);
  }, 5000);
});

function bindEvents() {
  byId("refreshAll").addEventListener("click", refreshAll);
  byId("refreshJobs").addEventListener("click", () => loadJobs().catch(reportError));
  byId("findCity").addEventListener("click", findCity);
  byId("cityQuery").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      findCity();
    }
  });
  byId("citySuggestions").addEventListener("click", chooseSuggestion);
  byId("locationForm").addEventListener("submit", addCoordinates);
  byId("locationsBody").addEventListener("change", selectLocation);
  byId("locationsBody").addEventListener("click", deleteLocation);
  byId("selectAllLocations").addEventListener("click", () => {
    state.selectedLocations = new Set(state.locations.map((item) => item.id));
    renderLocations();
  });
  byId("clearLocationSelection").addEventListener("click", () => {
    state.selectedLocations.clear();
    renderLocations();
  });
  byId("exportLocations").addEventListener("click", exportLocations);
  byId("locationFile").addEventListener("change", importFile);
  byId("deterministicSources").addEventListener("change", selectSource);
  byId("ensembleSources").addEventListener("change", selectSource);
  byId("recommendedSources").addEventListener("click", selectRecommendedSources);
  byId("createJob").addEventListener("click", createJob);
  byId("jobsList").addEventListener("click", jobAction);
}

async function refreshAll() {
  setHealth("Проверка…", "");
  try {
    await Promise.all([
      loadDiagnostics(),
      loadLocations(),
      loadSources(),
      loadJobs(),
    ]);
    setHealth("Система готова", "ok");
  } catch (error) {
    setHealth("Есть проблема", "error");
    reportError(error);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  const body = type.includes("json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object"
      ? body.detail || JSON.stringify(body)
      : body;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return body;
}

async function loadDiagnostics() {
  state.diagnostics = await api("/api/v1/diagnostics");
  const d = state.diagnostics;
  byId("dadataHint").textContent = d.dadata_configured
    ? "DaData подключена: доступны города и адреса."
    : "DaData не настроена: вводите координаты или добавьте WTD_DADATA_TOKEN.";
  const rows = [
    ["Версия", d.version],
    ["Модели", `${d.deterministic_source_count} дет. / ${d.ensemble_source_count} ансамбл.`],
    ["DaData", d.dadata_configured ? "подключена" : "не настроена"],
    ["Telegram", d.telegram_enabled ? "включён" : "выключен"],
    ["ecCodes", d.eccodes_python ? "доступен" : "не установлен"],
  ];
  byId("diagnostics").innerHTML = rows
    .map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
  byId("forecastDays").value ||= d.default_forecast_days || 7;
}

async function loadLocations() {
  state.locations = await api("/api/v1/locations?limit=10000");
  const ids = new Set(state.locations.map((item) => item.id));
  state.selectedLocations = new Set(
    [...state.selectedLocations].filter((id) => ids.has(id)),
  );
  renderLocations();
}

function renderLocations() {
  const body = byId("locationsBody");
  if (!state.locations.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">Добавьте город, координаты или файл.</td></tr>';
  } else {
    body.innerHTML = state.locations.map((location) => `
      <tr>
        <td><input type="checkbox" data-location="${escapeAttribute(location.id)}" ${state.selectedLocations.has(location.id) ? "checked" : ""}></td>
        <td><span class="location-title">${escapeHtml(location.name)}</span><span class="location-id">${escapeHtml(location.id)}</span></td>
        <td>${format(location.latitude, 5)}, ${format(location.longitude, 5)}</td>
        <td>${escapeHtml(location.group || "—")}</td>
        <td><button class="button ghost" type="button" data-delete="${escapeAttribute(location.id)}">Удалить</button></td>
      </tr>`).join("");
  }
  byId("locationCount").textContent = `${state.selectedLocations.size} выбрано`;
  updateSummary();
}

async function findCity() {
  const query = byId("cityQuery").value.trim();
  if (query.length < 2) {
    return reportError(new Error("Введите минимум два символа."));
  }
  const button = byId("findCity");
  busy(button, true, "Поиск…");
  try {
    state.suggestions = await api("/api/v1/geocoding/suggest", {
      method: "POST",
      body: JSON.stringify({query, count: 5}),
    });
    renderSuggestions();
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Найти");
  }
}

function renderSuggestions() {
  byId("citySuggestions").innerHTML = state.suggestions.length
    ? state.suggestions.map((item, index) => `
      <button class="suggestion" type="button" data-suggestion="${index}">
        <strong>${escapeHtml(item.name)}</strong>
        <small>${escapeHtml(item.address)} · ${format(item.latitude, 5)}, ${format(item.longitude, 5)}</small>
      </button>`).join("")
    : '<span class="muted">Совпадений не найдено.</span>';
}

async function chooseSuggestion(event) {
  const button = event.target.closest("[data-suggestion]");
  if (!button) return;
  const candidate = state.suggestions[Number(button.dataset.suggestion)];
  if (!candidate) return;
  try {
    const location = await saveLocation(candidate.location);
    state.selectedLocations.add(location.id);
    byId("cityQuery").value = "";
    state.suggestions = [];
    renderSuggestions();
    await loadLocations();
    toast(`Добавлена точка «${location.name}».`);
  } catch (error) {
    reportError(error);
  }
}

async function addCoordinates(event) {
  event.preventDefault();
  const lat = Number(byId("locationLatitude").value);
  const lon = Number(byId("locationLongitude").value);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    return reportError(new Error("Укажите широту и долготу."));
  }
  const name = byId("locationName").value.trim()
    || `Координаты ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  const location = {
    id: `manual-${Date.now()}`,
    name,
    latitude: lat,
    longitude: lon,
    elevation_m: null,
    timezone: "Europe/Moscow",
    group: "Вручную",
    output_name: null,
  };
  try {
    const saved = await saveLocation(location);
    state.selectedLocations.add(saved.id);
    event.target.reset();
    await loadLocations();
  } catch (error) {
    reportError(error);
  }
}

async function saveLocation(location) {
  return api("/api/v1/locations", {
    method: "POST",
    body: JSON.stringify(location),
  });
}

function selectLocation(event) {
  const checkbox = event.target.closest("[data-location]");
  if (!checkbox) return;
  if (checkbox.checked) state.selectedLocations.add(checkbox.dataset.location);
  else state.selectedLocations.delete(checkbox.dataset.location);
  renderLocations();
}

async function deleteLocation(event) {
  const button = event.target.closest("[data-delete]");
  if (!button || !window.confirm("Удалить точку из справочника?")) return;
  try {
    await api(`/api/v1/locations/${encodeURIComponent(button.dataset.delete)}`, {
      method: "DELETE",
    });
    state.selectedLocations.delete(button.dataset.delete);
    await loadLocations();
  } catch (error) {
    reportError(error);
  }
}

function exportLocations() {
  download(
    "weather-to-docx-locations.json",
    JSON.stringify({locations: state.locations}, null, 2),
    "application/json",
  );
}

async function importFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  toast(`Импорт ${file.name}`);
  try {
    const text = await file.text();
    let items = [];
    if (file.name.toLowerCase().endsWith(".json")) {
      const parsed = JSON.parse(text);
      items = Array.isArray(parsed) ? parsed : parsed.locations || [];
    } else if (file.name.toLowerCase().endsWith(".csv")) {
      items = parseCsv(text);
    } else {
      items = text.split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line && !line.startsWith("#"));
    }
    const locations = [];
    for (const [index, item] of items.slice(0, 1000).entries()) {
      if (typeof item === "object" && item.latitude != null && item.longitude != null) {
        locations.push(normalizeImportedLocation(item, index));
        continue;
      }
      const textItem = typeof item === "string"
        ? item
        : item.address || item.city || item.name || "";
      const coords = parseCoordinates(textItem);
      if (coords) {
        locations.push(normalizeImportedLocation({
          name: textItem,
          latitude: coords[0],
          longitude: coords[1],
        }, index));
      } else if (textItem) {
        const candidate = await api("/api/v1/geocoding/resolve", {
          method: "POST",
          body: JSON.stringify({query: textItem, automatic: true}),
        });
        locations.push({
          ...candidate.location,
          id: `import-${Date.now()}-${index}`,
        });
      }
    }
    if (!locations.length) {
      throw new Error("Файл не содержит распознаваемых точек.");
    }
    const imported = await api("/api/v1/locations/import", {
      method: "POST",
      body: JSON.stringify({locations, replace_existing: false}),
    });
    imported.forEach((item) => state.selectedLocations.add(item.id));
    await loadLocations();
    toast(`Импортировано точек: ${imported.length}.`);
  } catch (error) {
    reportError(error);
  } finally {
    event.target.value = "";
  }
}

function parseCsv(text) {
  const lines = text.replace(/^sep=.\r?\n/i, "").split(/\r?\n/).filter(Boolean);
  if (!lines.length) return [];
  const delimiter = lines[0].includes(";")
    ? ";"
    : lines[0].includes("\t") ? "\t" : ",";
  const headers = lines[0].split(delimiter)
    .map((item) => item.trim().toLowerCase());
  return lines.slice(1).map((line) => {
    const values = line.split(delimiter).map((item) => item.trim());
    const row = Object.fromEntries(
      headers.map((key, index) => [key, values[index] || ""]),
    );
    const lat = row.latitude || row.lat || row["широта"];
    const lon = row.longitude || row.lon || row.lng || row["долгота"];
    if (lat && lon) {
      return {
        name: row.name || row["название"] || row.city || row["город"],
        latitude: lat.replace(",", "."),
        longitude: lon.replace(",", "."),
      };
    }
    return row.address || row["адрес"] || row.city || row["город"]
      || row.name || row["название"];
  }).filter(Boolean);
}

function normalizeImportedLocation(item, index) {
  return {
    id: item.id || `import-${Date.now()}-${index}`,
    name: item.name || `Точка ${index + 1}`,
    latitude: Number(String(item.latitude).replace(",", ".")),
    longitude: Number(String(item.longitude).replace(",", ".")),
    elevation_m: item.elevation_m ?? null,
    timezone: item.timezone || "Europe/Moscow",
    group: item.group || "Импорт",
    output_name: item.output_name || null,
  };
}

function parseCoordinates(text) {
  const match = String(text).trim().match(
    /^([+-]?\d{1,2}(?:[.,]\d+)?)\s*[,;\s]\s*([+-]?\d{1,3}(?:[.,]\d+)?)$/,
  );
  if (!match) return null;
  const lat = Number(match[1].replace(",", "."));
  const lon = Number(match[2].replace(",", "."));
  return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
    ? [lat, lon]
    : null;
}

async function loadSources() {
  state.sources = await api("/api/v1/sources");
  const available = new Set(state.sources.map((item) => item.source_id));
  state.selectedSources = new Set(
    [...state.selectedSources].filter((id) => available.has(id)),
  );
  if (!state.selectedSources.size) selectRecommendedSources(false);
  renderSources();
}

function selectRecommendedSources(render = true) {
  const recommended = state.diagnostics?.default_sources || [
    "open_meteo_gfs",
    "open_meteo_ecmwf_ifs",
    "open_meteo_dwd_icon_global",
    "open_meteo_gefs_0p25",
  ];
  const available = new Set(state.sources.map((item) => item.source_id));
  state.selectedSources = new Set(
    recommended.filter((id) => available.has(id)),
  );
  if (render) renderSources();
}

function renderSources() {
  const deterministic = state.sources.filter(
    (item) => sourceKind(item) !== "ensemble" && item.source_id !== "demo",
  );
  const ensembles = state.sources.filter(
    (item) => sourceKind(item) === "ensemble",
  );
  byId("deterministicSources").innerHTML = deterministic.length
    ? deterministic.map(modelCard).join("")
    : '<div class="empty">Нет источников.</div>';
  byId("ensembleSources").innerHTML = ensembles.length
    ? ensembles.map(modelCard).join("")
    : '<div class="empty">Нет ансамблей.</div>';
  updateSummary();
}

function modelCard(source) {
  const selected = state.selectedSources.has(source.source_id);
  return `<label class="model ${selected ? "selected" : ""}">
    <input type="checkbox" data-source="${escapeAttribute(source.source_id)}" ${selected ? "checked" : ""}>
    <span><strong>${escapeHtml(source.model)}</strong><small>${escapeHtml(source.notes || source.provider)} · до ${source.horizon_days} сут.</small></span>
  </label>`;
}

function sourceKind(source) {
  if (typeof source.source_kind === "string") return source.source_kind;
  if (/ensemble|gefs|geps|eps/i.test(`${source.source_id} ${source.model}`)) {
    return "ensemble";
  }
  return "deterministic";
}

function selectSource(event) {
  const checkbox = event.target.closest("[data-source]");
  if (!checkbox) return;
  if (checkbox.checked) state.selectedSources.add(checkbox.dataset.source);
  else state.selectedSources.delete(checkbox.dataset.source);
  renderSources();
}

async function createJob() {
  const locations = state.locations.filter(
    (item) => state.selectedLocations.has(item.id),
  );
  const sources = state.sources.filter(
    (item) => state.selectedSources.has(item.source_id),
  );
  if (!locations.length) {
    return reportError(new Error("Выберите хотя бы одну точку."));
  }
  if (!sources.length) {
    return reportError(new Error("Выберите хотя бы одну модель."));
  }
  const days = Math.max(
    1,
    Math.min(35, Number(byId("forecastDays").value) || 7),
  );
  const thresholds = byId("precipitationThresholds").value
    .split(/[;,\s]+/)
    .map(Number)
    .filter((value) => Number.isFinite(value) && value >= 0);
  const payload = {
    batch_name: `forecast_${new Date().toISOString().slice(0, 10)}`,
    locations,
    sources: sources.map((source) => ({
      source_id: source.source_id,
      forecast_days: Math.min(days, source.horizon_days),
      options: sourceKind(source) === "ensemble"
        ? {precipitation_thresholds_mm: thresholds.length ? thresholds : [0.1, 1, 5]}
        : {},
    })),
    document: {
      title: byId("documentTitle").value.trim() || "Метеорологический прогноз",
      summary_interval_hours: 3,
      extended_summary_interval_hours: 6,
      summary_switch_hour: 120,
      ensemble_interval_hours: 6,
      ensemble_extended_interval_hours: 12,
      ensemble_switch_hour: 120,
      include_detailed_table: true,
      include_all_parameters: byId("parameterProfile").value !== "operational",
      include_ensemble_section: true,
      parameter_profile: byId("parameterProfile").value,
      page_size: byId("pageSize").value,
      language: "ru",
      organisation: null,
      prepared_by: null,
    },
  };
  const button = byId("createJob");
  busy(button, true, "Постановка в очередь…");
  try {
    await api("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadJobs();
    toast("Задание создано.");
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Сформировать документы");
  }
}

async function loadJobs() {
  state.jobs = await api("/api/v1/jobs?limit=50");
  renderJobs();
}

function renderJobs() {
  byId("jobsList").innerHTML = state.jobs.length
    ? state.jobs.map((job) => {
      const artifacts = (job.result?.artifacts || []).map((artifact, index) => `
        <a class="artifact" href="/api/v1/jobs/${encodeURIComponent(job.id)}/artifacts/${index}">
          ${escapeHtml(artifact.kind.toUpperCase())}${artifact.location_id ? ` · ${escapeHtml(artifact.location_id)}` : ""}
        </a>`).join("");
      const active = ["queued", "running"].includes(job.status);
      const retry = ["completed", "partial", "failed", "cancelled"].includes(job.status);
      return `<article class="job">
        <div><h3>${escapeHtml(job.request.batch_name || job.id.slice(0, 8))}</h3><p>${escapeHtml(statusNames[job.status] || job.status)} · ${job.request.locations.length} точек</p></div>
        <div class="artifacts">${artifacts || '<span class="muted">Результат ещё не готов.</span>'}</div>
        <div>${active ? `<button class="button ghost" data-cancel-job="${job.id}">Отменить</button>` : ""}${retry ? `<button class="button secondary" data-retry-job="${job.id}">Повторить</button>` : ""}</div>
      </article>`;
    }).join("")
    : '<div class="empty">Заданий пока нет.</div>';
}

async function jobAction(event) {
  const cancel = event.target.closest("[data-cancel-job]");
  const retry = event.target.closest("[data-retry-job]");
  if (!cancel && !retry) return;
  const button = cancel || retry;
  const jobId = cancel ? cancel.dataset.cancelJob : retry.dataset.retryJob;
  try {
    await api(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/${cancel ? "cancel" : "retry"}`,
      {method: "POST"},
    );
    await loadJobs();
  } catch (error) {
    reportError(error);
  }
}

function updateSummary() {
  const deterministic = state.sources.filter(
    (item) => state.selectedSources.has(item.source_id)
      && sourceKind(item) !== "ensemble",
  ).length;
  const ensembles = state.sources.filter(
    (item) => state.selectedSources.has(item.source_id)
      && sourceKind(item) === "ensemble",
  ).length;
  byId("selectionSummary").textContent = `${state.selectedLocations.size} точек · ${deterministic} моделей · ${ensembles} ансамблей`;
  byId("locationCount").textContent = `${state.selectedLocations.size} выбрано`;
}

function setHealth(text, status) {
  const badge = byId("healthBadge");
  badge.textContent = text;
  badge.className = `badge ${status}`;
}

function busy(button, active, text) {
  if (active) {
    button.dataset.label = button.textContent;
    button.textContent = text;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || text;
    button.disabled = false;
  }
}

function reportError(error) {
  console.error(error);
  toast(error instanceof Error ? error.message : String(error), true);
}

function toast(text, error = false) {
  const element = byId("toast");
  element.textContent = text;
  element.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    element.className = "toast";
  }, error ? 7000 : 3500);
}

function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function byId(id) {
  return document.getElementById(id);
}

function format(value, digits) {
  return Number(value).toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
