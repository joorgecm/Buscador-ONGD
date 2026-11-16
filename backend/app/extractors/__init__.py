"""Extractores por fuente: Comunitat Valenciana (CSV), Catalunya (XML) y Canarias (JSON)."""

from app.extractors.canarias import extraer_canarias
from app.extractors.common import (
    EntidadExtraida,
    ErrorExtraccion,
    Fuente,
    Reparacion,
    ResultadoExtraccion,
    TipoError,
)

__all__ = [
    "EntidadExtraida",
    "ErrorExtraccion",
    "Fuente",
    "Reparacion",
    "ResultadoExtraccion",
    "TipoError",
    "extraer_canarias",
]
