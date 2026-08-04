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
  button.addEventListener("click", createCompactJob);

  document.getElementById("ensembleSources").addEventListener(
    "change",
    limitEnsembleSelection,
    true,
  );
});

function limitEnsembleSelection(event) {
  const checkbox = event.target.closest("[data-source]");
  if (!checkbox?.checked) return;
  for (const source of state.sources) {
    if (sourceKind(source) === "ensemble" && source.source_id !== checkbox.dataset.source) {
      state.selectedSources.delete(source.source_id);
    }
  }
}

async function createCompactJob() {
  if (typeof reliabilityState !== "undefined" && !reliabilityState.workerOnline) {
    reportError(new Error(
      "Обработчик заданий не отвечает. Проверьте службу weather-to-docx-worker.",
    ));
    return;
  }

  const locations = state.locations.filter(
    (item) => state.selectedLocations.has(item.id),
  );
  const selected = state.sources.filter(
    (item) => state.selectedSources.has(item.source_id),
  );
  const deterministic = selected.filter(
    (item) => sourceKind(item) !== "ensemble",
  );
  const ensembles = selected.filter(
    (item) => sourceKind(item) === "ensemble",
  ).slice(0, 1);
  const sources = [...deterministic, ...ensembles];

  if (!locations.length) {
    reportError(new Error("Выберите хотя бы одну точку."));
    return;
  }
  if (!sources.length) {
    reportError(new Error("Выберите хотя бы одну модель."));
    return;
  }

  const days = Math.min(
    7,
    Math.max(1, Number(document.getElementById("forecastDays").value) || 7),
  );
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
        ? {
          precipitation_thresholds_mm: thresholds.length
            ? thresholds
            : [0.1, 1, 5],
        }
        : {},
    })),
    document: {
      title: document.getElementById("documentTitle").value.trim()
        || "Метеорологический прогноз",
      summary_interval_hours: 6,
      extended_summary_interval_hours: 12,
      summary_switch_hour: 72,
      ensemble_interval_hours: 12,
      ensemble_extended_interval_hours: 24,
      ensemble_switch_hour: 72,
      include_detailed_table: true,
      include_all_parameters: false,
      include_ensemble_section: true,
      parameter_profile: "operational",
      page_size: "A4",
      language: "ru",
      organisation: null,
      prepared_by: null,
    },
  };

  const button = document.getElementById("createJob");
  busy(button, true, "Постановка в очередь…");
  try {
    await api("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await loadJobs();
    toast("Создан компактный двухстраничный прогноз.");
  } catch (error) {
    reportError(error);
  } finally {
    busy(button, false, "Сформировать прогноз");
  }
}
