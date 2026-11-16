"""Extractores por fuente: Comunitat Valenciana (CSV), Catalunya (XML) y Canarias (JSON)."""

from app.extractors.canarias import ExtractorCAN, extraer_canarias
from app.extractors.common import (
    EntidadExtraida,
    ErrorExtraccion,
    Fuente,
    Reparacion,
    ResultadoExtraccion,
    TipoError,
)
from app.extractors.extractorCAT import ExtractorCAT
from app.extractors.extractorCV import ExtractorCV

__all__ = [
    "EntidadExtraida",
    "ErrorExtraccion",
    "ExtractorCAN",
    "ExtractorCAT",
    "ExtractorCV",
    "Fuente",
    "Reparacion",
    "ResultadoExtraccion",
    "TipoError",
    "extraer_canarias",
]
