"use strict";

const reliabilityState = {
  workerOnline: false,
  defaultsApplied: false,
  forecastDaysTouched: false,
  sourcesTouched: false,
  sourceDefaultsApplied: false,
  pendingLocations: [],
  pendingWarnings: [],
  pendingFilename: "",
};

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("locationForm")
    .addEventListener("submit", addCoordinatesReliably, true);
  document.getElementById("locationFile")
    .addEventListener("change", previewImportReliably, true);
  document.getElementById("confirmImport")
    .addEventListener("click", confirmImport);
  document.getElementById("cancelImport")
    .addEventListener("click", clearImportPreview);

  document.getElementById("forecastDays").addEventListener("input", () => {
    reliabilityState.forecastDaysTouched = true;
    updateHorizonSummary();
  });
  document.getElementById("pageSize").addEventListener("change", validatePageSize);
  document.getElementById("parameterProfile").addEventListener("change", validatePageSize);
  for (const id of ["deterministicSources", "ensembleSources"]) {
    document.getElementById(id).addEventListener("change", () => {
      reliabilityState.sourcesTouched = true;
      updateHorizonSummary();
    });
  }
  document.getElementById("createJob")
    .addEventListener("click", validateJobBeforeCreate, true);

  const jobs = document.getElementById("jobsList");
  new MutationObserver(decorateJobs).observe(jobs, {
    childList: true,
    subtree: true,
  });
  const locations = document.getElementById("locationsBody");
  new MutationObserver(decorateLocations).observe(locations, {
    childList: true,
    subtree: true,
  });

  refreshReliability().catch(reportError);
  window.setInterval(() => {
    if (!document.hidden) refreshReliability().catch(reportError);
  }, 5000);
});

async function addCoordinatesReliably(event) {
  event.preventDefault();
  event.stopImmediatePropagation();

  const latitude = Number(document.getElementById("locationLatitude").value);
  const longitude = Number(document.getElementById("locationLongitude").value);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    reportError(new Error("Укажите широту и долготу."));
    return;
  }
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
    reportError(new Error("Координаты находятся вне допустимого диапазона."));
    return;
  }

  const button = event.target.querySelector("button[type='submit']");
  busy(button, true, "Определение…");
  try {
    const explicitTimezone = document.getElementById("locationTimezone").value.trim();
    let timezone = explicitTimezone;
    let timezoneSource = "explicit";
    if (!timezone) {
      const resolved = await api("/api/v1/timezone/resolve", {
        method: "POST",
        body: JSON.stringify({latitude, longitude}),
      });
      timezone = resolved.timezone;
      timezoneSource = resolved.source;
    }

    const name = document.getElementById("locationName").value.trim()
      || `Координаты ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
    const saved = await saveLocation({
      id: `manual-${Date.now()}`,
      name,
      latitude,
      longitude,
      elevation_m: null,
      timezone,
      timezone_source: timezoneSource,
      group: "Вручную",
      output_name: null,
    });
    state.selectedLocations.add(saved.id);
    event.target.reset();
    document.getElementById("timezoneHint").textContent =
      `Определён часовой пояс ${saved.timezone}.`;
    await loadLocations();
    toast(`Добавлена точка «${saved.name}», ${saved.timezone}.`);
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Добавить");
  }
}

async function previewImportReliably(event) {
  event.preventDefault();
  event.stopImmediatePropagation();
  const input = event.target;
  const file = input.files?.[0];
  if (!file) return;

  clearImportPreview();
  const preview = document.getElementById("importPreview");
  preview.hidden = false;
  document.getElementById("importPreviewSummary").textContent =
    `Проверка ${file.name}…`;
  document.getElementById("importPreviewBody").innerHTML =
    '<tr><td colspan="4" class="empty">Разбор файла и определение часовых поясов…</td></tr>';

  try {
    const content = await file.text();
    const parsed = await api("/api/v1/geocoding/parse-file", {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content,
        max_locations: 1000,
      }),
    });
    reliabilityState.pendingLocations = parsed.locations || [];
    reliabilityState.pendingWarnings = parsed.warnings || [];
    reliabilityState.pendingFilename = file.name;
    renderImportPreview();
  } catch (error) {
    clearImportPreview();
    reportError(error);
  } finally {
    input.value = "";
  }
}

function renderImportPreview() {
  const locations = reliabilityState.pendingLocations;
  const warnings = reliabilityState.pendingWarnings;
  const preview = document.getElementById("importPreview");
  preview.hidden = false;
  document.getElementById("importPreviewSummary").textContent =
    `${locations.length} точек · ${warnings.length} предупреждений`;

  const warningBox = document.getElementById("importWarnings");
  warningBox.innerHTML = warnings.length
    ? `<details open><summary>Требуют внимания: ${warnings.length}</summary><ul>${warnings
      .slice(0, 50)
      .map((item) => `<li>${escapeHtml(item)}</li>`)
      .join("")}</ul>${warnings.length > 50 ? '<p>Показаны первые 50 предупреждений.</p>' : ""}</details>`
    : '<div class="import-ok">Все строки распознаны без предупреждений.</div>';

  const rows = locations.slice(0, 100).map((location, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><strong>${escapeHtml(location.name)}</strong></td>
      <td>${Number(location.latitude).toFixed(5)}, ${Number(location.longitude).toFixed(5)}</td>
      <td>${escapeHtml(location.timezone)}<small class="location-timezone">${escapeHtml(timezoneSourceLabel(location.timezone_source))}</small></td>
    </tr>`).join("");
  document.getElementById("importPreviewBody").innerHTML = rows
    || '<tr><td colspan="4" class="empty">Нет пригодных точек.</td></tr>';
  document.getElementById("confirmImport").disabled = !locations.length;
  if (locations.length > 100) {
    document.getElementById("importPreviewSummary").textContent +=
      " · показаны первые 100";
  }
}

async function confirmImport() {
  if (!reliabilityState.pendingLocations.length) return;
  const button = document.getElementById("confirmImport");
  busy(button, true, "Добавление…");
  try {
    const stamp = Date.now();
    const existing = new Set(state.locations.map((item) => item.id));
    const used = new Set();
    const locations = reliabilityState.pendingLocations.map((location, index) => {
      let id = location.id;
      if (existing.has(id) || used.has(id)) {
        id = `import-${stamp}-${index + 1}`;
      }
      used.add(id);
      return {...location, id};
    });
    const imported = await api("/api/v1/locations/import", {
      method: "POST",
      body: JSON.stringify({locations, replace_existing: false}),
    });
    imported.forEach((item) => state.selectedLocations.add(item.id));
    const warningCount = reliabilityState.pendingWarnings.length;
    clearImportPreview();
    await loadLocations();
    toast(
      warningCount
        ? `Добавлено ${imported.length} точек. Предупреждений при разборе: ${warningCount}.`
        : `Добавлено точек: ${imported.length}.`,
    );
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Добавить проверенные точки");
  }
}

function clearImportPreview() {
  reliabilityState.pendingLocations = [];
  reliabilityState.pendingWarnings = [];
  reliabilityState.pendingFilename = "";
  const preview = document.getElementById("importPreview");
  if (preview) preview.hidden = true;
  const body = document.getElementById("importPreviewBody");
  if (body) body.innerHTML = "";
  const warnings = document.getElementById("importWarnings");
  if (warnings) warnings.innerHTML = "";
}

async function refreshReliability() {
  const diagnostics = await api("/api/v1/diagnostics");
  reliabilityState.workerOnline = Boolean(diagnostics.worker?.online);
  state.diagnostics = diagnostics;

  if (!reliabilityState.defaultsApplied && !reliabilityState.forecastDaysTouched) {
    document.getElementById("forecastDays").value =
      diagnostics.default_forecast_days || 7;
    reliabilityState.defaultsApplied = true;
  }
  if (
    !reliabilityState.sourceDefaultsApplied
    && !reliabilityState.sourcesTouched
    && Array.isArray(state.sources)
    && state.sources.length
  ) {
    const available = new Set(state.sources.map((item) => item.source_id));
    state.selectedSources = new Set(
      (diagnostics.default_sources || []).filter((id) => available.has(id)),
    );
    reliabilityState.sourceDefaultsApplied = true;
    renderSources();
  }

  const status = document.getElementById("reliabilityStatus");
  const workerText = diagnostics.worker?.online
    ? `Обработчик заданий работает · отклик ${diagnostics.worker.age_seconds ?? 0} с`
    : "Обработчик заданий не отвечает — новые задания будут ждать запуска";
  const queue = diagnostics.queue || {};
  status.innerHTML = `
    <div class="reliability-line ${diagnostics.worker?.online ? "ok" : "error"}">
      <strong>${escapeHtml(workerText)}</strong>
    </div>
    <div class="reliability-line">
      <span>Очередь</span>
      <span>${Number(queue.queued || 0)} ожидают · ${Number(queue.running || 0)} выполняются</span>
    </div>
    <div class="reliability-line">
      <span>Часовые пояса</span>
      <span>${diagnostics.timezonefinder ? "локальный справочник доступен" : "справочник не установлен"}</span>
    </div>`;

  const createButton = document.getElementById("createJob");
  if (!reliabilityState.workerOnline) {
    createButton.disabled = true;
    createButton.title = "Запустите службу обработки заданий weather-to-docx-worker";
  } else if (createButton.textContent === "Сформировать документы") {
    createButton.disabled = false;
    createButton.title = "";
  }
  updateHorizonSummary();
  decorateLocations();
  decorateJobs();
}

function validateJobBeforeCreate(event) {
  if (!reliabilityState.workerOnline) {
    event.preventDefault();
    event.stopImmediatePropagation();
    reportError(new Error(
      "Обработчик заданий не отвечает. Запустите службу weather-to-docx-worker, затем обновите страницу.",
    ));
    return;
  }
  const pageSize = document.getElementById("pageSize").value;
  const profile = document.getElementById("parameterProfile").value;
  if (pageSize === "A4" && profile !== "operational") {
    event.preventDefault();
    event.stopImmediatePropagation();
    reportError(new Error(
      "Расширенная таблица не помещается в A4. Выберите формат A3."
    ));
  }
}

function updateHorizonSummary() {
  if (typeof state === "undefined" || !state.sources) return;
  const requested = Math.max(
    1,
    Math.min(35, Number(document.getElementById("forecastDays").value) || 7),
  );
  const selected = state.sources.filter((item) =>
    state.selectedSources.has(item.source_id),
  );
  if (!selected.length) {
    document.getElementById("horizonSummary").textContent = "";
    return;
  }
  const limited = selected
    .filter((item) => item.horizon_days < requested)
    .map((item) => `${item.model}: ${item.horizon_days} сут.`);
  document.getElementById("horizonSummary").textContent = limited.length
    ? `Ограничения моделей: ${limited.join(" · ")}`
    : `Все выбранные модели покрывают ${requested} сут.`;
}

function validatePageSize() {
  const pageSize = document.getElementById("pageSize").value;
  const profile = document.getElementById("parameterProfile").value;
  if (pageSize === "A4" && profile !== "operational") {
    document.getElementById("horizonSummary").textContent =
      "Расширенная таблица требует формата A3.";
  } else {
    updateHorizonSummary();
  }
}

function decorateLocations() {
  if (typeof state === "undefined" || !Array.isArray(state.locations)) return;
  const rows = [...document.querySelectorAll("#locationsBody tr")];
  rows.forEach((row, index) => {
    const location = state.locations[index];
    if (!location || row.cells.length < 3) return;
    const cell = row.cells[2];
    if (cell.querySelector(".location-timezone")) return;
    const timezone = document.createElement("span");
    timezone.className = "location-timezone";
    timezone.textContent = `${location.timezone} · ${timezoneSourceLabel(location.timezone_source)}`;
    cell.appendChild(timezone);
  });
}

function decorateJobs() {
  if (typeof state === "undefined" || !Array.isArray(state.jobs)) return;
  const cards = [...document.querySelectorAll("#jobsList .job")];
  cards.forEach((card, index) => {
    const job = state.jobs[index];
    if (!job || card.querySelector(".job-reliability")) return;
    const details = document.createElement("div");
    details.className = "job-reliability";
    const total = Number(job.progress_total || 0);
    const current = Math.min(Number(job.progress_current || 0), total || Infinity);
    const progress = total ? ` · ${current}/${total}` : "";
    const attempts = job.attempt_count ? ` · попытка ${job.attempt_count}` : "";
    const errors = [job.error, ...(job.result?.errors || [])].filter(Boolean);
    details.innerHTML = `
      <div>${escapeHtml(job.progress_message || "")}${escapeHtml(progress)}${escapeHtml(attempts)}</div>
      ${errors.length ? `<details><summary>Проблемы: ${errors.length}</summary><pre>${escapeHtml(errors.join("\n"))}</pre></details>` : ""}`;
    card.appendChild(details);
  });
}

function timezoneSourceLabel(value) {
  return {
    explicit: "задан вручную",
    coordinates: "определён по координатам",
    geocoder: "получен от геокодера",
    system_default: "резервная настройка — проверить",
  }[value] || "источник не указан";
}
