"use strict";

const reliabilityState = {
  workerOnline: false,
  defaultsApplied: false,
  forecastDaysTouched: false,
};

window.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("locationForm");
  form.addEventListener("submit", addCoordinatesReliably, true);

  document.getElementById("forecastDays").addEventListener("input", () => {
    reliabilityState.forecastDaysTouched = true;
    updateHorizonSummary();
  });
  document.getElementById("pageSize").addEventListener("change", validatePageSize);
  document.getElementById("parameterProfile").addEventListener("change", validatePageSize);
  document.getElementById("deterministicSources").addEventListener("change", updateHorizonSummary);
  document.getElementById("ensembleSources").addEventListener("change", updateHorizonSummary);
  document.getElementById("createJob").addEventListener("click", requireWorker, true);

  const jobs = document.getElementById("jobsList");
  new MutationObserver(decorateJobs).observe(jobs, {childList: true, subtree: true});

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

async function refreshReliability() {
  const diagnostics = await api("/api/v1/diagnostics");
  reliabilityState.workerOnline = Boolean(diagnostics.worker?.online);

  if (!reliabilityState.defaultsApplied && !reliabilityState.forecastDaysTouched) {
    document.getElementById("forecastDays").value =
      diagnostics.default_forecast_days || 7;
    reliabilityState.defaultsApplied = true;
  }

  const status = document.getElementById("reliabilityStatus");
  const workerText = diagnostics.worker?.online
    ? `Worker в сети · отклик ${diagnostics.worker.age_seconds ?? 0} с`
    : "Worker не отвечает — новые задания будут ожидать обработки";
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
  if (!createButton.dataset.busy) {
    createButton.disabled = !reliabilityState.workerOnline;
    createButton.title = reliabilityState.workerOnline
      ? ""
      : "Запустите weather-to-docx-worker";
  }
  updateHorizonSummary();
  decorateJobs();
}

function requireWorker(event) {
  if (reliabilityState.workerOnline) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  reportError(new Error(
    "Worker не отвечает. Проверьте службу weather-to-docx-worker, затем обновите страницу.",
  ));
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
    ? `Ограничения источников: ${limited.join(" · ")}`
    : `Все выбранные источники покрывают ${requested} сут.`;
}

function validatePageSize() {
  const pageSize = document.getElementById("pageSize").value;
  const profile = document.getElementById("parameterProfile").value;
  if (pageSize === "A4" && profile !== "operational") {
    document.getElementById("horizonSummary").textContent =
      "A4 с расширенным профилем может быть слишком плотным. Для рабочего отчёта используйте A3.";
  } else {
    updateHorizonSummary();
  }
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
