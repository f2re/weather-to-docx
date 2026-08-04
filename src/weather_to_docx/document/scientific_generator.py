from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from weather_to_docx.document.generator import DocumentGenerator
from weather_to_docx.document.styles import (
    DARK_BLUE,
    LIGHT_BLUE,
    MID_BLUE,
    WHITE,
    configure_document,
    prevent_row_split,
    set_cell_shading,
    set_cell_text,
    set_cell_width,
    set_repeat_header_count,
    set_table_fixed_layout,
)
from weather_to_docx.document.weather_rules import weather_presentation
from weather_to_docx.domain.models import (
    DocumentOptions,
    ForecastPoint,
    ForecastSeries,
    LeadTimeReference,
    Location,
    SourceKind,
    TimezoneSource,
)


class ScientificDocumentGenerator(DocumentGenerator):
    """Композиция DOCX: модели сначала, один ансамблевый раздел в конце."""

    def generate(
        self,
        *,
        location: Location,
        series: list[ForecastSeries],
        options: DocumentOptions,
        output_path: Path,
    ) -> Path:
        if not series:
            raise ValueError("Для документа не передан ни один прогностический ряд")
        if any(item.location.id != location.id for item in series):
            raise ValueError(
                "В документ нельзя объединять прогнозы для разных координат"
            )
        if options.page_size == "A4" and options.parameter_profile != "operational":
            raise ValueError(
                "Формат A4 поддерживает только оперативный профиль. "
                "Для расширенного или полного отчёта используйте A3."
            )

        deterministic = [item for item in series if not _is_ensemble(item)]
        ensembles = [item for item in series if _is_ensemble(item)]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        configure_document(document, options.page_size)
        self._configure_properties(document, location, options)
        self._add_header(document, location, series, options)

        section_count = 0
        for forecast in deterministic:
            if section_count:
                document.add_page_break()
            self._add_deterministic_section(document, forecast, options)
            section_count += 1

        if ensembles and options.include_ensemble_section:
            if section_count:
                document.add_page_break()
            self._add_ensemble_section(document, ensembles, options)

        self._add_footer(document, location)
        document.save(output_path)
        return output_path

    def _add_header(
        self,
        document: Document,
        location: Location,
        series: list[ForecastSeries],
        options: DocumentOptions,
    ) -> None:
        deterministic_count = sum(not _is_ensemble(item) for item in series)
        ensemble_count = sum(_is_ensemble(item) for item in series)

        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(options.title)
        run.bold = True
        run.font.name = "Liberation Sans"
        run.font.size = Pt(18)

        subtitle = document.add_paragraph()
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = subtitle.add_run(location.name)
        run.bold = True
        run.font.name = "Liberation Sans"
        run.font.size = Pt(13)

        if options.organisation:
            organisation = document.add_paragraph(options.organisation)
            organisation.alignment = WD_ALIGN_PARAGRAPH.CENTER

        table = document.add_table(rows=4, cols=4)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"
        set_table_fixed_layout(table)
        values = [
            (
                "Координаты",
                f"{location.latitude:.5f}, {location.longitude:.5f}",
            ),
            (
                "Высота",
                f"{location.elevation_m:.0f} м"
                if location.elevation_m is not None
                else "не задана",
            ),
            (
                "Часовой пояс",
                f"{location.timezone} — "
                f"{_timezone_source_text(location.timezone_source)}",
            ),
            (
                "Сформировано",
                datetime.now(UTC).strftime("%d.%m.%Y %H:%M UTC"),
            ),
            ("Детерминированных моделей", str(deterministic_count)),
            ("Ансамблевых систем", str(ensemble_count)),
            (
                "Источники",
                ", ".join(item.source.source_id for item in series),
            ),
            (
                "Документ",
                f"{options.page_size}; профиль {options.parameter_profile}",
            ),
        ]
        for index, (label, value) in enumerate(values):
            row = index // 2
            column = (index % 2) * 2
            set_cell_text(
                table.cell(row, column),
                label,
                bold=True,
                align=WD_ALIGN_PARAGRAPH.LEFT,
            )
            set_cell_shading(table.cell(row, column), MID_BLUE)
            set_cell_text(
                table.cell(row, column + 1),
                value,
                align=WD_ALIGN_PARAGRAPH.LEFT,
            )

        warning = document.add_paragraph()
        warning.paragraph_format.space_before = Pt(5)
        warning.paragraph_format.space_after = Pt(7)
        warning_run = warning.add_run(
            "Прогноз является расчётной информацией. Для критически важных "
            "решений учитывайте наблюдения, официальные предупреждения и "
            "неопределённость моделей."
        )
        warning_run.bold = True
        warning_run.font.size = Pt(8.5)

    def _add_deterministic_section(
        self,
        document: Document,
        forecast: ForecastSeries,
        options: DocumentOptions,
    ) -> None:
        source = forecast.source
        heading = document.add_heading(level=1)
        heading.add_run(f"{source.provider} — {source.model}")
        metadata = document.add_table(rows=4, cols=4)
        metadata.style = "Table Grid"
        metadata.alignment = WD_TABLE_ALIGNMENT.LEFT
        set_table_fixed_layout(metadata)
        cycle = (
            source.cycle_time_utc.astimezone(UTC).strftime(
                "%d.%m.%Y %H:%M UTC"
            )
            if source.cycle_time_utc
            else "не указан поставщиком"
        )
        pairs = [
            ("Источник", source.source_id),
            ("Тип", "детерминированный прогноз"),
            ("Цикл", cycle),
            (
                "Получено",
                source.retrieved_at_utc.astimezone(UTC).strftime(
                    "%d.%m.%Y %H:%M UTC"
                ),
            ),
            (
                "Горизонт",
                f"{source.horizon_hours} ч"
                if source.horizon_hours is not None
                else "—",
            ),
            (
                "Шаг",
                f"{source.native_time_step_hours:g} ч"
                if source.native_time_step_hours
                else "переменный",
            ),
            (
                "Отсчёт срока",
                _lead_reference_text(source.lead_time_reference),
            ),
            ("Продукт", source.product),
        ]
        for index, (label, value) in enumerate(pairs):
            row = index // 2
            column = (index % 2) * 2
            set_cell_text(
                metadata.cell(row, column),
                label,
                bold=True,
                align=WD_ALIGN_PARAGRAPH.LEFT,
            )
            set_cell_shading(metadata.cell(row, column), MID_BLUE)
            set_cell_text(
                metadata.cell(row, column + 1),
                value,
                align=WD_ALIGN_PARAGRAPH.LEFT,
            )

        document.add_heading("1. Наглядный прогноз", level=2)
        self._add_deterministic_summary(document, forecast, options)
        if options.include_detailed_table:
            document.add_heading(
                "2. Подробный метеорологический отчёт по срокам",
                level=2,
            )
            self._add_deterministic_details(document, forecast, options)
        self._add_source_notes(document, forecast)

    def _add_deterministic_summary(
        self,
        document: Document,
        forecast: ForecastSeries,
        options: DocumentOptions,
    ) -> None:
        headers = (
            "Дата и время",
            "Погода",
            "Температура",
            "Ощущается",
            "Осадки",
            "Ветер",
            "Порывы",
            "Давление",
            "Облачность",
        )
        widths = (30, 34, 20, 20, 24, 36, 22, 24, 24)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_fixed_layout(table)
        for cell, text, width in zip(
            table.rows[0].cells,
            headers,
            widths,
            strict=True,
        ):
            set_cell_text(cell, text, size=8, bold=True)
            set_cell_shading(cell, DARK_BLUE)
            self._set_text_color(cell, WHITE)
            set_cell_width(cell, width)
        set_repeat_header_count(table, 1)

        previous_date = None
        for point in self._summary_points(forecast.points, options):
            row = table.add_row()
            prevent_row_split(row)
            current_date = point.valid_time_local.date()
            fill = LIGHT_BLUE if current_date != previous_date else WHITE
            previous_date = current_date
            for cell, width in zip(row.cells, widths, strict=True):
                set_cell_width(cell, width)
                set_cell_shading(cell, fill)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            presentation = weather_presentation(point)
            set_cell_text(
                row.cells[0],
                point.valid_time_local.strftime("%d.%m.%Y\n%H:%M"),
                size=7.5,
            )
            self._set_icon_cell(
                row.cells[1],
                presentation.icon_key,
                presentation.description,
            )
            set_cell_text(
                row.cells[2],
                self._value(point, "temperature_2m", with_unit=True),
                size=8,
                bold=True,
            )
            set_cell_text(
                row.cells[3],
                self._value(point, "apparent_temperature", with_unit=True),
                size=8,
            )
            set_cell_text(
                row.cells[4],
                self._value(point, "precipitation", with_unit=True),
                size=8,
            )
            set_cell_text(row.cells[5], self._wind_text(point), size=7.5)
            set_cell_text(
                row.cells[6],
                self._value(point, "wind_gusts_10m", with_unit=True),
                size=8,
            )
            set_cell_text(
                row.cells[7],
                self._value(point, "pressure_msl", with_unit=True),
                size=8,
            )
            set_cell_text(
                row.cells[8],
                self._value(point, "cloud_cover", with_unit=True),
                size=8,
            )
            self._apply_hazard_shading(row.cells, point)

    def _add_deterministic_details(
        self,
        document: Document,
        forecast: ForecastSeries,
        options: DocumentOptions,
    ) -> None:
        if options.page_size == "A4":
            self._add_compact_a4_details(document, forecast)
            return

        include_extra = (
            options.parameter_profile != "operational"
            and self._has_additional_parameters(forecast)
        )
        headers = [
            "Дата и время",
            "Срок",
            "Погода",
            "T / Td / RH",
            "Давление",
            "Ветер / порывы",
            "Осадки",
            "Снег",
            "Облачность / видимость",
            "Конвекция",
            "Радиация",
            "Почва / испарение",
        ]
        widths = [28, 16, 25, 34, 25, 34, 32, 23, 40, 25, 31, 44]
        if include_extra:
            headers.append("Дополнительные поля")
            widths.append(54)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_fixed_layout(table)
        for cell, text, width in zip(
            table.rows[0].cells,
            headers,
            widths,
            strict=True,
        ):
            set_cell_text(cell, text, size=6.5, bold=True)
            set_cell_shading(cell, DARK_BLUE)
            self._set_text_color(cell, WHITE)
            set_cell_width(cell, width)
        set_repeat_header_count(table, 1)

        previous_date = None
        for point in forecast.points:
            row = table.add_row()
            prevent_row_split(row)
            current_date = point.valid_time_local.date()
            fill = LIGHT_BLUE if current_date != previous_date else WHITE
            previous_date = current_date
            for cell, width in zip(row.cells, widths, strict=True):
                set_cell_width(cell, width)
                set_cell_shading(cell, fill)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            presentation = weather_presentation(point)
            cells = [
                point.valid_time_local.strftime("%d.%m.%Y\n%H:%M"),
                _lead_text(forecast, point),
                presentation.description,
                (
                    f"T {self._value(point, 'temperature_2m')}\n"
                    f"Td {self._value(point, 'dew_point_2m')}\n"
                    f"RH {self._value(point, 'relative_humidity_2m')} %"
                ),
                self._pressure_text(point),
                (
                    f"{self._wind_text(point)}\n"
                    "порывы "
                    f"{self._value(point, 'wind_gusts_10m', with_unit=True)}"
                ),
                self._precipitation_text(point),
                self._snow_text(point),
                (
                    f"{self._cloud_text(point)}\n"
                    f"вид {self._visibility_text(point)}"
                ),
                self._convection_text(point),
                self._radiation_text(point),
                (
                    f"{self._soil_temperature_text(point)}\n"
                    f"{self._surface_exchange_text(point)}"
                ),
            ]
            if include_extra:
                cells.append(self._additional_parameters_text(point))
            for cell, text in zip(row.cells, cells, strict=True):
                set_cell_text(
                    cell,
                    text,
                    size=5.9 if include_extra else 6.2,
                )
            self._apply_hazard_shading(row.cells, point)

    def _add_compact_a4_details(
        self,
        document: Document,
        forecast: ForecastSeries,
    ) -> None:
        headers = (
            "Дата и время",
            "Срок",
            "Погода и T/Td/RH",
            "Ветер",
            "Осадки и снег",
            "Облачность и видимость",
            "Давление и конвекция",
        )
        widths = (30, 20, 47, 42, 41, 50, 47)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_fixed_layout(table)
        for cell, text, width in zip(
            table.rows[0].cells,
            headers,
            widths,
            strict=True,
        ):
            set_cell_text(cell, text, size=7, bold=True)
            set_cell_shading(cell, DARK_BLUE)
            self._set_text_color(cell, WHITE)
            set_cell_width(cell, width)
        set_repeat_header_count(table, 1)

        previous_date = None
        for point in forecast.points:
            row = table.add_row()
            prevent_row_split(row)
            current_date = point.valid_time_local.date()
            fill = LIGHT_BLUE if current_date != previous_date else WHITE
            previous_date = current_date
            for cell, width in zip(row.cells, widths, strict=True):
                set_cell_width(cell, width)
                set_cell_shading(cell, fill)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            presentation = weather_presentation(point)
            values = (
                point.valid_time_local.strftime("%d.%m.%Y\n%H:%M"),
                _lead_text(forecast, point),
                (
                    f"{presentation.description}\n"
                    f"T {self._value(point, 'temperature_2m')} °C; "
                    f"Td {self._value(point, 'dew_point_2m')} °C; "
                    f"RH {self._value(point, 'relative_humidity_2m')} %"
                ),
                (
                    f"{self._wind_text(point)}\n"
                    "порывы "
                    f"{self._value(point, 'wind_gusts_10m', with_unit=True)}"
                ),
                (
                    f"{self._precipitation_text(point)}\n"
                    f"{self._snow_text(point)}"
                ),
                (
                    f"{self._cloud_text(point)}\n"
                    f"вид {self._visibility_text(point)}"
                ),
                (
                    f"{self._pressure_text(point)}\n"
                    f"{self._convection_text(point)}"
                ),
            )
            for cell, text in zip(row.cells, values, strict=True):
                set_cell_text(cell, text, size=6.6)
            self._apply_hazard_shading(row.cells, point)

    def _add_ensemble_section(
        self,
        document: Document,
        forecasts: list[ForecastSeries],
        options: DocumentOptions,
    ) -> None:
        heading = document.add_heading(level=1)
        heading.add_run("Ансамблевая оценка неопределённости")
        intro = document.add_paragraph()
        intro.add_run(
            "Этот раздел не является ещё одним детерминированным сценарием. "
            "Каждая строка описывает распределение равновероятных членов "
            "конкретной ансамблевой системы; разные системы не объединяются."
        ).bold = True
        explanations = (
            (
                "Температура и давление: центр — среднее, σ — стандартное "
                "отклонение членов относительно среднего."
            ),
            (
                "Осадки, ветер, порывы и CAPE: центр — медиана q50; "
                "q10–q90 — центральные 80 % членов."
            ),
            (
                "P(осадки) — сырая некалиброванная доля M/N членов выше "
                "порога. В каждой ячейке указаны собственные M, N и интервал."
            ),
            (
                "Срок +N ч показывается от цикла только при известном цикле. "
                "Для Open-Meteo используется подпись «от начала выдачи»."
            ),
            (
                "Неполный набор членов помечается вопросительным знаком. "
                "Калибровка, Brier Skill Score и CRPSS без архива не создаются."
            ),
        )
        for text in explanations:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.add_run(f"• {text}").font.size = Pt(8)

        if options.page_size == "A4":
            self._add_compact_a4_ensemble_table(document, forecasts, options)
        else:
            self._add_a3_ensemble_table(document, forecasts, options)

        document.add_paragraph()
        for forecast in forecasts:
            source = forecast.source
            parts = [source.model]
            if source.ensemble_member_count:
                parts.append(f"N={source.ensemble_member_count}")
            if source.ensemble_expected_member_count:
                parts.append(
                    f"ожидалось {source.ensemble_expected_member_count}"
                )
            parts.append(_lead_reference_text(source.lead_time_reference))
            if source.attribution:
                parts.append(source.attribution)
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.add_run("• " + "; ".join(parts)).font.size = Pt(7.5)

    def _add_a3_ensemble_table(
        self,
        document: Document,
        forecasts: list[ForecastSeries],
        options: DocumentOptions,
    ) -> None:
        headers = (
            "Дата и время",
            "Срок / отсчёт",
            "Ансамбль",
            "Члены",
            "T: среднее ± σ; q10–q90",
            "Осадки: q50; q10–q90",
            "Сырые вероятности осадков",
            "Ветер: q50; q10–q90",
            "Порывы",
            "Pmsl: среднее ± σ",
            "CAPE: q50; q10–q90",
        )
        widths = (28, 24, 34, 22, 38, 36, 52, 36, 28, 34, 34)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_fixed_layout(table)
        for cell, text, width in zip(
            table.rows[0].cells,
            headers,
            widths,
            strict=True,
        ):
            set_cell_text(cell, text, size=6.5, bold=True)
            set_cell_shading(cell, DARK_BLUE)
            self._set_text_color(cell, WHITE)
            set_cell_width(cell, width)
        set_repeat_header_count(table, 1)

        previous_time = None
        for forecast, point in _ensemble_rows(forecasts, options):
            row = table.add_row()
            prevent_row_split(row)
            fill = (
                LIGHT_BLUE
                if point.valid_time_utc != previous_time
                else WHITE
            )
            previous_time = point.valid_time_utc
            for cell, width in zip(row.cells, widths, strict=True):
                set_cell_width(cell, width)
                set_cell_shading(cell, fill)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            values = (
                point.valid_time_local.strftime("%d.%m.%Y\n%H:%M"),
                _lead_text(forecast, point),
                forecast.source.model,
                _member_text(forecast, point),
                _mean_spread_range(point, "temperature_2m", "°C"),
                _median_range(point, "precipitation", "мм"),
                _probabilities_text(point),
                _median_range(point, "wind_speed_10m", "м/с"),
                _gust_text(point),
                _mean_spread_range(point, "pressure_msl", "гПа"),
                _median_range(point, "cape", "Дж/кг"),
            )
            for cell, text in zip(row.cells, values, strict=True):
                set_cell_text(cell, text, size=6.0)

    def _add_compact_a4_ensemble_table(
        self,
        document: Document,
        forecasts: list[ForecastSeries],
        options: DocumentOptions,
    ) -> None:
        headers = (
            "Дата и срок",
            "Ансамбль / члены",
            "Температура",
            "Осадки и вероятность",
            "Ветер и порывы",
            "Давление и CAPE",
        )
        widths = (42, 42, 43, 64, 53, 53)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_fixed_layout(table)
        for cell, text, width in zip(
            table.rows[0].cells,
            headers,
            widths,
            strict=True,
        ):
            set_cell_text(cell, text, size=7, bold=True)
            set_cell_shading(cell, DARK_BLUE)
            self._set_text_color(cell, WHITE)
            set_cell_width(cell, width)
        set_repeat_header_count(table, 1)

        previous_time = None
        for forecast, point in _ensemble_rows(forecasts, options):
            row = table.add_row()
            prevent_row_split(row)
            fill = (
                LIGHT_BLUE
                if point.valid_time_utc != previous_time
                else WHITE
            )
            previous_time = point.valid_time_utc
            for cell, width in zip(row.cells, widths, strict=True):
                set_cell_width(cell, width)
                set_cell_shading(cell, fill)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            values = (
                (
                    f"{point.valid_time_local:%d.%m.%Y %H:%M}\n"
                    f"{_lead_text(forecast, point)}"
                ),
                f"{forecast.source.model}\n{_member_text(forecast, point)}",
                _mean_spread_range(point, "temperature_2m", "°C"),
                (
                    f"{_median_range(point, 'precipitation', 'мм')}\n"
                    f"{_probabilities_text(point)}"
                ),
                (
                    f"{_median_range(point, 'wind_speed_10m', 'м/с')}\n"
                    f"{_gust_text(point)}"
                ),
                (
                    f"{_mean_spread_range(point, 'pressure_msl', 'гПа')}\n"
                    f"CAPE {_median_range(point, 'cape', 'Дж/кг')}"
                ),
            )
            for cell, text in zip(row.cells, values, strict=True):
                set_cell_text(cell, text, size=6.4)

    @staticmethod
    def _add_source_notes(
        document: Document,
        forecast: ForecastSeries,
    ) -> None:
        notes = list(forecast.warnings)
        source = forecast.source
        if source.grid_distance_km is not None:
            notes.append(
                "Расстояние до ближайшего модельного узла: "
                f"{source.grid_distance_km:.1f} км."
            )
        if source.attribution:
            notes.append(f"Атрибуция: {source.attribution}.")
        if source.licence:
            notes.append(f"Условия использования: {source.licence}.")
        for text in notes:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            paragraph.add_run(f"• {text}").font.size = Pt(7.5)


def _is_ensemble(forecast: ForecastSeries) -> bool:
    return (
        forecast.source.source_kind == SourceKind.ENSEMBLE
        or forecast.source.ensemble_member_count is not None
        or "ensemble" in forecast.source.source_id.lower()
        or any(
            token in forecast.source.source_id.lower()
            for token in ("gefs", "geps", "eps")
        )
    )


def _ensemble_points(
    points: list[ForecastPoint],
    options: DocumentOptions,
) -> list[ForecastPoint]:
    selected: list[ForecastPoint] = []
    for index, point in enumerate(points):
        lead = point.lead_hours
        interval = (
            options.ensemble_interval_hours
            if lead is None or lead <= options.ensemble_switch_hour
            else options.ensemble_extended_interval_hours
        )
        if (
            index == 0
            or index == len(points) - 1
            or lead is None
            or lead % interval == 0
        ):
            selected.append(point)
    return selected


def _ensemble_rows(
    forecasts: list[ForecastSeries],
    options: DocumentOptions,
) -> list[tuple[ForecastSeries, ForecastPoint]]:
    rows: list[tuple[ForecastSeries, ForecastPoint]] = []
    for forecast in forecasts:
        for point in _ensemble_points(forecast.points, options):
            rows.append((forecast, point))
    rows.sort(
        key=lambda item: (
            item[1].valid_time_utc,
            item[0].source.model,
        )
    )
    return rows


def _lead_text(forecast: ForecastSeries, point: ForecastPoint) -> str:
    if point.lead_hours is None:
        return "—"
    reference = forecast.source.lead_time_reference
    if reference == LeadTimeReference.CYCLE:
        return f"+{point.lead_hours} ч\nот цикла"
    if reference == LeadTimeReference.RESPONSE_START:
        return f"+{point.lead_hours} ч\nот начала выдачи"
    return f"+{point.lead_hours} ч\nточка отсчёта неизвестна"


def _lead_reference_text(reference: LeadTimeReference) -> str:
    return {
        LeadTimeReference.CYCLE: "от времени цикла модели",
        LeadTimeReference.RESPONSE_START: "от первого срока полученной выдачи",
        LeadTimeReference.UNKNOWN: "точка отсчёта неизвестна",
    }[reference]


def _timezone_source_text(source: TimezoneSource) -> str:
    return {
        TimezoneSource.EXPLICIT: "задан оператором",
        TimezoneSource.COORDINATES: "определён по координатам",
        TimezoneSource.GEOCODER: "получен от геокодера",
        TimezoneSource.SYSTEM_DEFAULT: "резервное значение — проверить",
    }[source]


def _number(point: ForecastPoint, code: str) -> float | None:
    value = point.raw(code)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _format(value: float | None, precision: int = 1) -> str:
    return "—" if value is None else f"{value:.{precision}f}"


def _mean_spread_range(point: ForecastPoint, code: str, unit: str) -> str:
    mean = _number(point, f"{code}_mean")
    spread = _number(point, f"{code}_spread")
    p10 = _number(point, f"{code}_p10")
    p90 = _number(point, f"{code}_p90")
    if mean is None:
        return "—"
    return (
        f"{_format(mean)} ± {_format(spread)} {unit}\n"
        f"[{_format(p10)}; {_format(p90)}]"
    )


def _median_range(point: ForecastPoint, code: str, unit: str) -> str:
    median = _number(point, f"{code}_median")
    p10 = _number(point, f"{code}_p10")
    p90 = _number(point, f"{code}_p90")
    if median is None:
        return "—"
    return (
        f"{_format(median)} {unit}\n"
        f"[{_format(p10)}; {_format(p90)}]"
    )


def _gust_text(point: ForecastPoint) -> str:
    median = _number(point, "wind_gusts_10m_median")
    p90 = _number(point, "wind_gusts_10m_p90")
    if median is None and p90 is None:
        return "—"
    return f"порывы q50 {_format(median)}; q90 {_format(p90)} м/с"


def _member_text(forecast: ForecastSeries, point: ForecastPoint) -> str:
    count = _number(point, "ensemble_member_count")
    coverage = _number(point, "ensemble_member_coverage")
    expected = forecast.source.ensemble_expected_member_count
    count_text = _format(count, 0)
    if expected:
        count_text += f"/{expected}"
    suffix = "?" if coverage is not None and coverage < 99.9 else ""
    return (
        f"N {count_text}{suffix}\n"
        f"полнота {_format(coverage, 0)} %"
    )


def _probabilities_text(point: ForecastPoint) -> str:
    rows: list[str] = []
    for code, measurement in sorted(point.values.items()):
        if not code.startswith("precipitation_probability_ge_"):
            continue
        threshold = (
            code.removeprefix("precipitation_probability_ge_")
            .removesuffix("mm")
            .replace("p", ".")
        )
        try:
            value = (
                float(measurement.value)
                if measurement.value is not None
                else None
            )
        except (TypeError, ValueError):
            value = None
        interval = (
            f" за {measurement.accumulation_hours:g} ч"
            if measurement.accumulation_hours is not None
            else " за интервал источника"
        )
        fraction = (
            f" ({measurement.event_count}/{measurement.sample_count})"
            if measurement.event_count is not None
            and measurement.sample_count is not None
            else ""
        )
        rows.append(
            f"≥{threshold} мм{interval}: {_format(value, 0)} %{fraction}"
        )
    return "\n".join(rows) if rows else "—"
