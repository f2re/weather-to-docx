"use strict";

window.addEventListener("DOMContentLoaded", () => {
  const days = document.getElementById("forecastDays");
  days.max = "7";
  days.value = String(Math.min(7, Math.max(1, Number(days.value) || 7)));
  document.getElementById("pageSize").value = "A4";
  document.getElementById("parameterProfile").value = "operational";

  const oldButton = document.getElementById("createJob");
  const button = oldButton.cloneNode(true);
  oldButton.replaceWith(button);
  button.addEventListener("click", createProfessionalJob);

  document.getElementById("ensembleSources").addEventListener(
    "change",
    limitEnsembleSelection,
    true,
  );
  document.querySelectorAll('input[name="documentMode"]').forEach((input) => {
    input.addEventListener("change", applyDocumentMode);
  });
  ["forecastDays", "includeMeteograms"].forEach((id) => {
    document.getElementById(id).addEventListener("change", renderDocumentPlan);
    document.getElementById(id).addEventListener("input", renderDocumentPlan);
  });
  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-source], [data-location]")) {
      window.setTimeout(renderDocumentPlan, 0);
    }
  });

  applyDocumentMode();
  renderMeteogramRuntimeStatus();
  window.setInterval(() => {
    renderMeteogramRuntimeStatus();
    renderDocumentPlan();
    decorateJobs();
  }, 1500);
});

function currentDocumentMode() {
  return document.querySelector('input[name="documentMode"]:checked')?.value
    || "expert";
}

function applyDocumentMode() {
  const mode = currentDocumentMode();
  const checkbox = document.getElementById("includeMeteograms");
  if (mode === "brief") {
    checkbox.checked = false;
    checkbox.disabled = true;
  } else {
    checkbox.disabled = state.diagnostics?.meteogram_ready !== true;
    checkbox.checked = true;
  }
  renderDocumentPlan();
}

function limitEnsembleSelection(event) {
  const checkbox = event.target.closest("[data-source]");
  if (!checkbox?.checked) return;
  for (const source of state.sources) {
    if (sourceKind(source) === "ensemble" && source.source_id !== checkbox.dataset.source) {
      state.selectedSources.delete(source.source_id);
    }
  }
  window.setTimeout(renderDocumentPlan, 0);
}

function renderMeteogramRuntimeStatus() {
  const diagnostics = typeof state !== "undefined" ? state.diagnostics : null;
  if (!diagnostics) return;
  const container = document.getElementById("diagnostics");
  if (!container) return;

  let row = container.querySelector("[data-meteogram-runtime]");
  if (!row) {
    row = document.createElement("div");
    row.className = "metric";
    row.dataset.meteogramRuntime = "true";
    row.innerHTML = "<span>Метеограммы</span><strong></strong>";
    container.prepend(row);
  }
  const ready = diagnostics.meteogram_ready === true;
  const generator = String(diagnostics.document_generator || "не определён")
    .split(".")
    .pop();
  row.querySelector("strong").textContent = ready
    ? `готовы · ${diagnostics.version}`
    : `недоступны · ${generator}`;
  row.classList.toggle("error", !ready);

  const checkbox = document.getElementById("includeMeteograms");
  if (!checkbox || currentDocumentMode() === "brief") return;
  checkbox.disabled = !ready;
  checkbox.title = ready
    ? "Графики будут встроены и проверены"
    : "Сервер использует старую версию компонентов. Выполните scripts/update.sh";
}

function selectedSourceCounts() {
  const selected = state.sources.filter((item) => state.selectedSources.has(item.source_id));
  return {
    deterministic: selected.filter((item) => sourceKind(item) !== "ensemble").length,
    ensemble: Math.min(1, selected.filter((item) => sourceKind(item) === "ensemble").length),
  };
}

function renderDocumentPlan() {
  const element = document.getElementById("documentPlan");
  if (!element || typeof state === "undefined") return;
  const days = Math.min(7, Math.max(1, Number(document.getElementById("forecastDays").value) || 7));
  const mode = currentDocumentMode();
  const count = selectedSourceCounts();
  const summaryPages = days <= 3 ? 1 : 2;
  let pages = summaryPages;
  const sections = [
    "важные риски",
    "сводка по дням",
    "прогноз по времени",
  ];
  if (mode === "expert") {
    pages += count.deterministic + count.ensemble;
    sections.push(`${count.deterministic} метеограмм основных моделей`);
    if (count.ensemble) sections.push("график вариантов ансамбля");
  } else if (mode === "full") {
    pages += count.deterministic * 2 + count.ensemble * 2;
    sections.push("метеограммы и отдельные таблицы по моделям");
  } else if (count.ensemble) {
    sections.push("таблица вариантов ансамбля");
  }
  element.innerHTML = `
    <div class="plan-pages"><strong>Ориентировочно ${pages} стр.</strong><span>${modeName(mode)}</span></div>
    <div class="plan-strip">
      <span>1</span><b>Риски и сводка</b>
      <span>${summaryPages}</span><b>Прогноз по времени</b>
      ${mode === "brief" ? "" : `<span>${pages}</span><b>Графики моделей</b>`}
    </div>
    <p>${sections.map(escapeHtml).join(" · ")}</p>`;
}

function modeName(mode) {
  return {
    brief: "Краткий",
    expert: "С графиками",
    full: "Подробный",
  }[mode] || mode;
}

async function createProfessionalJob() {
  if (typeof reliabilityState !== "undefined" && !reliabilityState.workerOnline) {
    reportError(new Error(
      "Обработчик заданий не отвечает. Проверьте службу weather-to-docx-worker.",
    ));
    return;
  }

  const mode = currentDocumentMode();
  const includeMeteograms = mode !== "brief"
    && document.getElementById("includeMeteograms").checked;
  if (includeMeteograms && state.diagnostics?.meteogram_ready !== true) {
    reportError(new Error(
      "Генератор метеограмм не готов. Выполните ./scripts/update.sh и обновите страницу.",
    ));
    return;
  }

  const locations = state.locations.filter((item) => state.selectedLocations.has(item.id));
  const selected = state.sources.filter((item) => state.selectedSources.has(item.source_id));
  const deterministic = selected.filter((item) => sourceKind(item) !== "ensemble");
  const ensembles = selected.filter((item) => sourceKind(item) === "ensemble").slice(0, 1);
  const sources = [...deterministic, ...ensembles];
  if (!locations.length) return reportError(new Error("Выберите хотя бы одну точку."));
  if (!sources.length) return reportError(new Error("Выберите хотя бы одну модель."));

  const days = Math.min(7, Math.max(1, Number(document.getElementById("forecastDays").value) || 7));
  document.getElementById("forecastDays").value = String(days);
  const thresholds = document.getElementById("precipitationThresholds").value
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
      title: document.getElementById("documentTitle").value.trim()
        || "Метеорологический прогноз",
      document_mode: mode,
      summary_interval_hours: 6,
      extended_summary_interval_hours: 12,
      summary_switch_hour: 72,
      ensemble_interval_hours: 12,
      ensemble_extended_interval_hours: 24,
      ensemble_switch_hour: 72,
      include_detailed_table: mode === "full",
      include_all_parameters: mode === "full",
      include_ensemble_section: true,
      include_meteograms: includeMeteograms,
      meteogram_smoothing: "pchip",
      meteogram_dpi: 180,
      parameter_profile: mode === "full" ? "extended" : "operational",
      page_size: mode === "full" ? "A3" : "A4",
      language: "ru",
      organisation: null,
      prepared_by: null,
    },
  };

  const button = document.getElementById("createJob");
  busy(button, true, "Постановка в очередь…");
  try {
    await api("/api/v1/jobs", {method: "POST", body: JSON.stringify(payload)});
    await loadJobs();
    decorateJobs();
    toast(`Создан документ: ${modeName(mode).toLowerCase()}.`);
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Сформировать прогноз");
  }
}

function decorateJobs() {
  if (typeof state === "undefined") return;
  const articles = [...document.querySelectorAll("#jobsList .job")];
  state.jobs.forEach((job, index) => {
    const article = articles[index];
    if (!article || article.querySelector(".job-audit")) return;
    const artifacts = job.result?.artifacts || [];
    const docxIndex = artifacts.findIndex((artifact) => artifact.kind === "docx");
    const previewIndex = artifacts.findIndex((artifact) => artifact.kind === "preview");
    if (docxIndex < 0) return;
    const metadata = artifacts[docxIndex].metadata || {};
    const visual = {
      passed: "визуальная проверка пройдена",
      failed: "визуальная проверка выявила проблему",
      "not-available": "визуальная проверка недоступна на сервере",
      "not-requested": "выполнена структурная проверка",
    }[metadata.visual_check] || "выполнена структурная проверка";
    const block = document.createElement("div");
    block.className = `job-audit ${metadata.visual_check === "failed" ? "failed" : ""}`;
    block.innerHTML = `
      ${previewIndex >= 0 ? `<a class="meteogram-preview" href="/api/v1/jobs/${encodeURIComponent(job.id)}/artifacts/${previewIndex}" target="_blank"><img src="/api/v1/jobs/${encodeURIComponent(job.id)}/artifacts/${previewIndex}" alt="Миниатюра метеограммы"></a>` : ""}
      <div><strong>DOCX проверен</strong>
      <span>метеограмм: ${metadata.meteograms ?? 0}</span>
      <span>страниц: ${metadata.rendered_pages ?? metadata.structured_pages ?? "—"}</span>
      <span>${escapeHtml(visual)}</span>
      <span>русские даты: ${metadata.russian_weekdays ? "да" : "не проверены"}</span></div>`;
    article.append(block);
  });
}
