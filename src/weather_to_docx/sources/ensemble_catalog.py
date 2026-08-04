from __future__ import annotations

from dataclasses import replace

from weather_to_docx.sources.open_meteo_ensemble import (
    OpenMeteoEcmwfAifsEnsembleSource as _OpenMeteoEcmwfAifsEnsembleSource,
)
from weather_to_docx.sources.open_meteo_ensemble import (
    OpenMeteoEcmwfIfsEnsembleSource as _OpenMeteoEcmwfIfsEnsembleSource,
)
from weather_to_docx.sources.open_meteo_ensemble import (
    OpenMeteoGemGepsSource as _OpenMeteoGemGepsSource,
)


class OpenMeteoEcmwfIfsEnsembleSource(_OpenMeteoEcmwfIfsEnsembleSource):
    """ECMWF IFS ENS: контрольный и 50 возмущённых членов."""

    expected_member_count = 51
    descriptor = replace(
        _OpenMeteoEcmwfIfsEnsembleSource.descriptor,
        notes=(
            "51-членный вероятностный ансамбль ECMWF IFS; "
            "сырые вероятности и распределение."
        ),
    )


class OpenMeteoEcmwfAifsEnsembleSource(_OpenMeteoEcmwfAifsEnsembleSource):
    """ECMWF AIFS ENS: контрольный и 50 возмущённых членов."""

    expected_member_count = 51
    descriptor = replace(
        _OpenMeteoEcmwfAifsEnsembleSource.descriptor,
        notes=(
            "51-членный ансамбль машинно-обученной модели ECMWF AIFS; "
            "сырые вероятности и распределение."
        ),
    )


class OpenMeteoGemGepsSource(_OpenMeteoGemGepsSource):
    """ECCC GEPS: контрольный и 20 возмущённых членов."""

    expected_member_count = 21
    descriptor = replace(
        _OpenMeteoGemGepsSource.descriptor,
        notes=(
            "21-членный канадский глобальный ансамбль; "
            "сырые вероятности и распределение."
        ),
    )
