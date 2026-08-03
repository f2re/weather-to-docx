"use strict";

const state = {
  diagnostics: null,
  locations: [],
  sources: [],
  jobs: [],
  selectedLocations: new Set(),
  selectedSources: new Set(),
  sourceDays: new Map(),
  toastTimer: null,
};

const recommendedSourceIds = new Set([
  "open_meteo_gfs",
  "open_meteo_ecmwf_ifs",
  "open_meteo_dwd_icon_global",
  "open_meteo_gefs_0p25",
]);

const statusLabels = {
  queued: "В очереди",
  running: "Выполняется",
  completed: "Завершено",
  partial: "Частично завершено",
  failed: "Ошибка",
  cancelled: "Отменено",
};

const statusClasses = {
  queued: "status-neutral",
  running: "status-warning",
  completed: "status-success",
  partial: "status-warning",
  failed: "status-danger",
  cancelled: "status-neutral",
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  restorePreferences();
  refreshAll();
  window.setInterval(() => {
    if (!document.hidden) {
      loadJobs().catch(reportError);
    }
  }, 5000);
});

function bindEvents() {
  document.querySelector("#refreshAll").addEventListener("click", refreshAll);
  document.querySelector("#refreshJobs").addEventListener("click", () => loadJobs().catch(reportError));
  document.querySelector("#locationForm").addEventListener("submit", saveLocation);
  document.querySelector("#cancelLocationEdit").addEventListener("click", resetLocationForm);
  document.querySelector("#locationName").addEventListener("blur", suggestLocationId);
  document.querySelector("#locationsBody").addEventListener("click", handleLocationAction);
  document.querySelector("#locationsBody").addEventListener("change", handleLocationSelection);
  document.querySelector("#selectAllLocations").addEventListener("click", toggleAllLocations);
  document.querySelector("#exportLocations").addEventListener("click", exportLocations);
  document.querySelector("#importLocationsFile").addEventListener("change", importLocations);
  document.querySelector("#sourcesList").addEventListener("change", handleSourceChange);
  document.querySelector("#recommendedSources").addEventListener("click", selectRecommendedSources);
  document.querySelector("#clearSources").addEventListener("click", clearSources);
  document.querySelector("#createJob").addEventListener("click", createJob);
  document.querySelector("#jobsList").addEventListener("click", handleJobAction);

  for (const element of document.querySelectorAll("#generationForm input, #generationForm select")) {
    element.addEventListener("change", () => {
      savePreferences();
      updateSelectionSummary();
    });
  }
}

async function refreshAll() {
  setHealth("Проверка системы…", "status-neutral");
  try {
    await Promise.all([
      loadDiagnostics(),
      loadLocations(),
      loadSources(),
      loadJobs(),
    ]);
    setHealth("Система доступна", "status-success");
  } catch (error) {
    setHealth("Есть проблема", "status-danger");
    reportError(error);
  }
}

async function api(path, options = {}) {
  const request = {
    headers: {
      Accept: "application/json",
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      ...(options.headers || {}),
    },
    ...options,
  };
  const response = await fetch(path, request);
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = typeof body === "object" && body !== null
      ? body.detail || JSON.stringify(body)
      : body;
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return body;
}

async function loadDiagnostics() {
  state.diagnostics = await api("/api/v1/diagnostics");
  renderDiagnostics();
}

function renderDiagnostics() {
  const data = state.diagnostics;
  const cards = [
    {
      label: "Версия",
      value: data.version,
      note: data.eccodes_python ? "ecCodes доступен" : "Прямой GRIB требует ecCodes",
    },
    {
      label: "Источники",
      value: String(data.source_count),
      note: "Детерминированные модели и ансамбли",
    },
    {
      label: "Координаты",
      value: String(data.location_count),
      note: "Сохранено в SQLite",
    },
    {
      label: "Хранилище документов",
      value: data.documents_writable ? "Доступно" : "Нет записи",
      note: data.documents_dir,
    },
  ];
  document.querySelector("#diagnostics").innerHTML = cards
    .map((card) => `
      <article class="metric-card">
        <span>${escapeHtml(card.label)}</span>
        <strong>${escapeHtml(card.value)}</strong>
        <small>${escapeHtml(card.note)}</small>
      </article>
    `)
    .join("");
}

async function loadLocations() {
  state.locations = await api("/api/v1/locations?limit=10000");
  const available = new Set(state.locations.map((location) => location.id));
  state.selectedLocations = new Set(
    [...state.selectedLocations].filter((id) => available.has(id)),
  );
  renderLocations();
  updateSelectionSummary();
}

function renderLocations() {
  const body = document.querySelector("#locationsBody");
  if (!state.locations.length) {
    body.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">
          Справочник пуст. Добавьте первую точку или импортируйте JSON.
        </td>
      </tr>
    `;
    return;
  }

  body.innerHTML = state.locations
    .map((location) => {
      const selected = state.selectedLocations.has(location.id);
      const elevation = location.elevation_m == null ? "" : ` · ${formatNumber(location.elevation_m, 0)} м`;
      return `
        <tr>
          <td>
            <input
              class="row-selector"
              type="checkbox"
              data-location-select="${escapeAttribute(location.id)}"
              ${selected ? "checked" : ""}
              aria-label="Выбрать ${escapeAttribute(location.name)}"
            >
          </td>
          <td>
            <span class="location-name">${escapeHtml(location.name)}</span>
            <span class="location-id">${escapeHtml(location.id)}</span>
          </td>
          <td>
            ${formatNumber(location.latitude, 5)}, ${formatNumber(location.longitude, 5)}${escapeHtml(elevation)}
          </td>
          <td>${escapeHtml(location.timezone)}</td>
          <td>${escapeHtml(location.group || "—")}</td>
          <td class="actions-column">
            <button class="button button-ghost button-small" type="button" data-edit-location="${escapeAttribute(location.id)}">Изменить</button>
            <button class="button button-danger button-small" type="button" data-delete-location="${escapeAttribute(location.id)}">Удалить</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function saveLocation(event) {
  event.preventDefault();
  const editingId = value("#editingLocationId");
  const elevationText = value("#locationElevation");
  const location = {
    id: value("#locationId"),
    name: value("#locationName"),
    latitude: Number(value("#locationLatitude")),
    longitude: Number(value("#locationLongitude")),
    elevation_m: elevationText === "" ? null : Number(elevationText),
    timezone: value("#locationTimezone"),
    group: nullableValue("#locationGroup"),
    output_name: null,
  };

  const button = document.querySelector("#saveLocation");
  setBusy(button, true, "Сохранение…");
  try {
    if (editingId) {
      await api(`/api/v1/locations/${encodeURIComponent(editingId)}`, {
        method: "PUT",
        body: JSON.stringify(location),
      });
    } else {
      await api("/api/v1/locations", {
        method: "POST",
        body: JSON.stringify(location),
      });
    }
    state.selectedLocations.add(location.id);
    resetLocationForm();
    await Promise.all([loadLocations(), loadDiagnostics()]);
    showToast("Координата сохранена.");
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false, "Сохранить точку");
  }
}

function suggestLocationId() {
  const editingId = value("#editingLocationId");
  const idInput = document.querySelector("#locationId");
  if (editingId || idInput.value.trim()) {
    return;
  }
  const suggested = value("#locationName")
    .trim()
    .toLocaleLowerCase("ru")
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9._-]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
  idInput.value = suggested;
}

function handleLocationAction(event) {
  const editButton = event.target.closest("[data-edit-location]");
  if (editButton) {
    const location = state.locations.find(
      (item) => item.id === editButton.dataset.editLocation,
    );
    if (location) {
      fillLocationForm(location);
    }
    return;
  }

  const deleteButton = event.target.closest("[data-delete-location]");
  if (deleteButton) {
    deleteLocation(deleteButton.dataset.deleteLocation);
  }
}

function handleLocationSelection(event) {
  const selector = event.target.closest("[data-location-select]");
  if (!selector) {
    return;
  }
  if (selector.checked) {
    state.selectedLocations.add(selector.dataset.locationSelect);
  } else {
    state.selectedLocations.delete(selector.dataset.locationSelect);
  }
  updateSelectionSummary();
}

function fillLocationForm(location) {
  setValue("#editingLocationId", location.id);
  setValue("#locationId", location.id);
  setValue("#locationName", location.name);
  setValue("#locationLatitude", location.latitude);
  setValue("#locationLongitude", location.longitude);
  setValue("#locationElevation", location.elevation_m ?? "");
  setValue("#locationTimezone", location.timezone);
  setValue("#locationGroup", location.group ?? "");
  document.querySelector("#locationId").readOnly = true;
  document.querySelector("#saveLocation").textContent = "Сохранить изменения";
  document.querySelector("#cancelLocationEdit").classList.remove("hidden");
  document.querySelector("#locationName").focus();
}

function resetLocationForm() {
  document.querySelector("#locationForm").reset();
  setValue("#editingLocationId", "");
  setValue("#locationTimezone", "Europe/Moscow");
  document.querySelector("#locationId").readOnly = false;
  document.querySelector("#saveLocation").textContent = "Сохранить точку";
  document.querySelector("#cancelLocationEdit").classList.add("hidden");
}

async function deleteLocation(locationId) {
  const location = state.locations.find((item) => item.id === locationId);
  if (!window.confirm(`Удалить точку «${location?.name || locationId}»?`)) {
    return;
  }
  try {
    await api(`/api/v1/locations/${encodeURIComponent(locationId)}`, {
      method: "DELETE",
    });
    state.selectedLocations.delete(locationId);
    await Promise.all([loadLocations(), loadDiagnostics()]);
    showToast("Координата удалена.");
  } catch (error) {
    reportError(error);
  }
}

function toggleAllLocations() {
  const allSelected = state.locations.length > 0
    && state.locations.every((location) => state.selectedLocations.has(location.id));
  state.selectedLocations = allSelected
    ? new Set()
    : new Set(state.locations.map((location) => location.id));
  renderLocations();
  updateSelectionSummary();
}

function exportLocations() {
  const payload = {
    schema: "weather-to-docx/locations-v1",
    exported_at: new Date().toISOString(),
    locations: state.locations,
  };
  downloadBlob(
    `weather-to-docx-locations-${new Date().toISOString().slice(0, 10)}.json`,
    JSON.stringify(payload, null, 2),
    "application/json",
  );
}

async function importLocations(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  try {
    const parsed = JSON.parse(await file.text());
    const locations = Array.isArray(parsed) ? parsed : parsed.locations;
    if (!Array.isArray(locations) || !locations.length) {
      throw new Error("Файл не содержит непустой массив locations.");
    }
    const imported = await api("/api/v1/locations/import", {
      method: "POST",
      body: JSON.stringify({
        locations,
        replace_existing: document.querySelector("#replaceLocations").checked,
      }),
    });
    for (const location of imported) {
      state.selectedLocations.add(location.id);
    }
    await Promise.all([loadLocations(), loadDiagnostics()]);
    showToast(`Импортировано точек: ${imported.length}.`);
  } catch (error) {
    reportError(error);
  } finally {
    event.target.value = "";
  }
}

async function loadSources() {
  state.sources = await api("/api/v1/sources");
  const sourceIds = new Set(state.sources.map((source) => source.source_id));
  state.selectedSources = new Set(
    [...state.selectedSources].filter((id) => sourceIds.has(id)),
  );
  if (!state.selectedSources.size) {
    for (const id of recommendedSourceIds) {
      if (sourceIds.has(id)) {
        state.selectedSources.add(id);
      }
    }
  }
  for (const source of state.sources) {
    if (!state.sourceDays.has(source.source_id)) {
      state.sourceDays.set(
        source.source_id,
        Math.min(source.horizon_days, source.source_id.includes("gefs_0p5") ? 16 : 7),
      );
    }
  }
  renderSources();
  savePreferences();
  updateSelectionSummary();
}

function renderSources() {
  const container = document.querySelector("#sourcesList");
  if (!state.sources.length) {
    container.innerHTML = '<div class="empty-state">Источники не зарегистрированы.</div>';
    return;
  }
  const sorted = [...state.sources].sort((left, right) => {
    const kindDifference = Number(isEnsemble(left)) - Number(isEnsemble(right));
    return kindDifference || left.provider.localeCompare(right.provider, "ru");
  });
  container.innerHTML = sorted
    .map((source) => {
      const selected = state.selectedSources.has(source.source_id);
      const directUnavailable = source.source_id === "noaa_gfs_0p25"
        && state.diagnostics
        && !state.diagnostics.eccodes_python;
      const days = state.sourceDays.get(source.source_id) || Math.min(7, source.horizon_days);
      return `
        <article class="source-card ${selected ? "selected" : ""}">
          <input
            class="source-selector"
            type="checkbox"
            data-source-select="${escapeAttribute(source.source_id)}"
            ${selected ? "checked" : ""}
            aria-label="Выбрать ${escapeAttribute(source.name)}"
          >
          <div>
            <h3>${escapeHtml(source.name)}</h3>
            <p>${escapeHtml(source.notes || `${source.provider} · ${source.model}`)}</p>
            <div class="source-meta">
              <span class="source-tag">${isEnsemble(source) ? "Ансамбль" : "Детерминированная"}</span>
              <span class="source-tag">до ${source.horizon_days} сут.</span>
              <span class="source-tag">${source.exact_cycle ? "точный цикл" : "цикл не передаётся"}</span>
              ${directUnavailable ? '<span class="source-tag">нужен ecCodes</span>' : ""}
            </div>
          </div>
          <div class="source-days">
            <label for="days-${escapeAttribute(source.source_id)}">Суток</label>
            <input
              id="days-${escapeAttribute(source.source_id)}"
              data-source-days="${escapeAttribute(source.source_id)}"
              type="number"
              min="1"
              max="${source.horizon_days}"
              value="${days}"
            >
          </div>
        </article>
      `;
    })
    .join("");
}

function handleSourceChange(event) {
  const selector = event.target.closest("[data-source-select]");
  if (selector) {
    if (selector.checked) {
      state.selectedSources.add(selector.dataset.sourceSelect);
    } else {
      state.selectedSources.delete(selector.dataset.sourceSelect);
    }
    renderSources();
    savePreferences();
    updateSelectionSummary();
    return;
  }

  const daysInput = event.target.closest("[data-source-days]");
  if (daysInput) {
    const source = state.sources.find((item) => item.source_id === daysInput.dataset.sourceDays);
    const days = clamp(
      Number(daysInput.value) || 1,
      1,
      source?.horizon_days || 35,
    );
    state.sourceDays.set(daysInput.dataset.sourceDays, days);
    daysInput.value = String(days);
    savePreferences();
  }
}

function selectRecommendedSources() {
  const available = new Set(state.sources.map((source) => source.source_id));
  state.selectedSources = new Set(
    [...recommendedSourceIds].filter((id) => available.has(id)),
  );
  renderSources();
  savePreferences();
  updateSelectionSummary();
}

function clearSources() {
  state.selectedSources.clear();
  renderSources();
  savePreferences();
  updateSelectionSummary();
}

async function createJob() {
  const locations = state.locations.filter((location) => state.selectedLocations.has(location.id));
  const sources = state.sources
    .filter((source) => state.selectedSources.has(source.source_id))
    .map((source) => ({
      source_id: source.source_id,
      forecast_days: state.sourceDays.get(source.source_id) || Math.min(7, source.horizon_days),
      options: isEnsemble(source)
        ? {precipitation_threshold_mm: 0.1}
        : {},
    }));

  if (!locations.length) {
    reportError(new Error("Выберите минимум одну координату."));
    return;
  }
  if (!sources.length) {
    reportError(new Error("Выберите минимум одну прогностическую модель."));
    return;
  }

  const payload = {
    batch_name: nullableValue("#batchName"),
    locations,
    sources,
    document: {
      title: value("#documentTitle") || "Метеорологический прогноз",
      summary_interval_hours: numberValue("#summaryInterval", 3),
      extended_summary_interval_hours: numberValue("#extendedSummaryInterval", 6),
      summary_switch_hour: 120,
      include_detailed_table: checked("#includeDetailed"),
      include_all_parameters: checked("#includeAllParameters"),
      parameter_profile: checked("#includeAllParameters") ? "all" : "operational",
      page_size: value("#pageSize"),
      language: "ru",
      organisation: nullableValue("#organisation"),
      prepared_by: nullableValue("#preparedBy"),
    },
  };

  const button = document.querySelector("#createJob");
  setBusy(button, true, "Постановка в очередь…");
  try {
    const job = await api("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    savePreferences();
    await loadJobs();
    showToast(`Задание ${job.id.slice(0, 8)} поставлено в очередь.`);
    document.querySelector("#jobsHeading").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false, "Сформировать документы");
  }
}

async function loadJobs() {
  state.jobs = await api("/api/v1/jobs?limit=100");
  renderJobs();
}

function renderJobs() {
  const container = document.querySelector("#jobsList");
  if (!state.jobs.length) {
    container.innerHTML = '<div class="empty-state">Заданий пока нет.</div>';
    return;
  }

  container.innerHTML = state.jobs
    .map((job) => {
      const sources = job.request.sources
        .map((source) => `<span class="source-tag">${escapeHtml(source.source_id)} · ${source.forecast_days} сут.</span>`)
        .join("");
      const artifacts = (job.result?.artifacts || [])
        .map((artifact, index) => `
          <a
            class="artifact-link"
            href="/api/v1/jobs/${encodeURIComponent(job.id)}/artifacts/${index}"
          >
            ${artifactIcon(artifact.kind)} ${escapeHtml(artifact.kind.toUpperCase())}
            ${artifact.location_id ? ` · ${escapeHtml(artifact.location_id)}` : ""}
          </a>
        `)
        .join("");
      const errors = [
        ...(job.error ? [job.error] : []),
        ...(job.result?.errors || []),
      ];
      const isActive = ["queued", "running"].includes(job.status);
      const canRetry = ["completed", "partial", "failed", "cancelled"].includes(job.status);
      const actions = [
        isActive
          ? `<button class="button button-danger button-small" type="button" data-cancel-job="${escapeAttribute(job.id)}">Отменить</button>`
          : "",
        canRetry
          ? `<button class="button button-secondary button-small" type="button" data-retry-job="${escapeAttribute(job.id)}">Повторить</button>`
          : "",
      ].join("");

      return `
        <article class="job-card">
          <div>
            <h3>${escapeHtml(job.request.batch_name || `Задание ${job.id.slice(0, 8)}`)}</h3>
            <p>${formatDateTime(job.created_at_utc)} · ${job.request.locations.length} точек</p>
            <div class="status-chip ${statusClasses[job.status] || "status-neutral"}">
              ${escapeHtml(statusLabels[job.status] || job.status)}
            </div>
          </div>
          <div>
            <div class="job-sources">${sources}</div>
            ${artifacts ? `<div class="artifact-list">${artifacts}</div>` : ""}
            ${errors.length ? `<p class="job-error">${escapeHtml(errors.join(" · "))}</p>` : ""}
          </div>
          <div class="job-actions">${actions}</div>
        </article>
      `;
    })
    .join("");
}

async function handleJobAction(event) {
  const cancelButton = event.target.closest("[data-cancel-job]");
  const retryButton = event.target.closest("[data-retry-job]");
  const button = cancelButton || retryButton;
  if (!button) {
    return;
  }
  setBusy(button, true, "Выполнение…");
  try {
    if (cancelButton) {
      await api(`/api/v1/jobs/${encodeURIComponent(cancelButton.dataset.cancelJob)}/cancel`, {
        method: "POST",
      });
      showToast("Задание отменено.");
    } else {
      await api(`/api/v1/jobs/${encodeURIComponent(retryButton.dataset.retryJob)}/retry`, {
        method: "POST",
      });
      showToast("Создано повторное задание.");
    }
    await loadJobs();
  } catch (error) {
    reportError(error);
  } finally {
    setBusy(button, false, cancelButton ? "Отменить" : "Повторить");
  }
}

function updateSelectionSummary() {
  const locations = state.selectedLocations.size;
  const sources = state.selectedSources.size;
  const summary = document.querySelector("#selectionSummary");
  if (!locations || !sources) {
    summary.textContent = `Выбрано точек: ${locations}; моделей: ${sources}`;
    return;
  }
  const documents = locations;
  const sections = locations * sources;
  summary.textContent = `Будет создано документов: ${documents}; модельных секций: ${sections}`;
}

function restorePreferences() {
  try {
    const saved = JSON.parse(localStorage.getItem("weather-to-docx-preferences") || "{}");
    state.selectedSources = new Set(saved.selectedSources || []);
    state.sourceDays = new Map(Object.entries(saved.sourceDays || {}).map(([key, value]) => [key, Number(value)]));
    for (const [selector, valueToSet] of Object.entries(saved.form || {})) {
      const element = document.querySelector(selector);
      if (!element) {
        continue;
      }
      if (element.type === "checkbox") {
        element.checked = Boolean(valueToSet);
      } else {
        element.value = valueToSet;
      }
    }
  } catch {
    localStorage.removeItem("weather-to-docx-preferences");
  }
}

function savePreferences() {
  const formSelectors = [
    "#batchName",
    "#documentTitle",
    "#pageSize",
    "#summaryInterval",
    "#extendedSummaryInterval",
    "#organisation",
    "#preparedBy",
    "#includeDetailed",
    "#includeAllParameters",
  ];
  const form = {};
  for (const selector of formSelectors) {
    const element = document.querySelector(selector);
    form[selector] = element.type === "checkbox" ? element.checked : element.value;
  }
  const payload = {
    selectedSources: [...state.selectedSources],
    sourceDays: Object.fromEntries(state.sourceDays),
    form,
  };
  localStorage.setItem("weather-to-docx-preferences", JSON.stringify(payload));
}

function setHealth(text, className) {
  const badge = document.querySelector("#healthBadge");
  badge.textContent = text;
  badge.className = `status-chip ${className}`;
}

function setBusy(button, busy, busyLabel) {
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.textContent = busyLabel;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalLabel || busyLabel;
    button.disabled = false;
  }
}

function showToast(message, isError = false) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.className = `toast visible${isError ? " error" : ""}`;
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    toast.className = "toast";
  }, isError ? 7000 : 3500);
}

function reportError(error) {
  console.error(error);
  showToast(error instanceof Error ? error.message : String(error), true);
}

function isEnsemble(source) {
  return /ensemble|gefs|geps|eps/i.test(`${source.source_id} ${source.model}`);
}

function artifactIcon(kind) {
  if (kind === "docx") {
    return "📄";
  }
  if (kind === "zip") {
    return "🗂";
  }
  if (kind === "manifest") {
    return "🔎";
  }
  return "⬇";
}

function value(selector) {
  return document.querySelector(selector).value.trim();
}

function nullableValue(selector) {
  const result = value(selector);
  return result === "" ? null : result;
}

function numberValue(selector, fallback) {
  const result = Number(value(selector));
  return Number.isFinite(result) ? result : fallback;
}

function checked(selector) {
  return document.querySelector(selector).checked;
}

function setValue(selector, newValue) {
  document.querySelector(selector).value = newValue;
}

function clamp(number, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, number));
}

function formatNumber(number, digits) {
  return Number(number).toLocaleString("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDateTime(valueToFormat) {
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(valueToFormat));
  } catch {
    return valueToFormat;
  }
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], {type});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(valueToEscape) {
  return String(valueToEscape ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(valueToEscape) {
  return escapeHtml(valueToEscape).replaceAll("`", "&#096;");
}
