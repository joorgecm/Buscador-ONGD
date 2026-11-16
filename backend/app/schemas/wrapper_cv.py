"""Esquemas Pydantic para el Wrapper de la Comunitat Valenciana (CSV -> JSON)."""

from pydantic import BaseModel, Field


class EntidadCVOrigen(BaseModel):
    """Registro crudo leído del CSV de la Comunitat Valenciana según los campos del mapping."""

    fila: int = Field(
        ...,
        ge=2,
        description="Número de línea física en el archivo CSV original (empezando en 2).",
    )
    WKT: str | None = Field(
        default=None,
        description="Geometría en texto WKT (ej. 'POINT (x y)'), respaldo para coordenadas.",
    )
    id: str | None = Field(
        default=None,
        description="Identificador original del registro en el CSV de la CV.",
    )
    tipo_centro: str | None = Field(
        default=None,
        description="Tipología del centro social/inclusivo (usada en ámbito y descripción).",
    )
    nombre: str | None = Field(
        default=None,
        description="Nombre oficial del centro o entidad.",
    )
    domici: str | None = Field(
        default=None,
        description="Dirección postal en origen (sin código postal).",
    )
    cod_ine_mun: str | None = Field(
        default=None,
        description="Código INE del municipio (los 2 primeros dígitos indican la provincia).",
    )
    provincia: str | None = Field(
        default=None,
        description="Nombre oficial de la provincia en origen.",
    )
    municipio: str | None = Field(
        default=None,
        description="Nombre oficial del municipio/localidad en origen.",
    )
    sector: str | None = Field(
        default=None,
        description="Sector de actuación principal del centro.",
    )
    clasificacion: str | None = Field(
        default=None,
        description="Clasificación del centro en origen (respaldo ante ausencia de sector).",
    )
    email: str | None = Field(
        default=None,
        description="Correo electrónico de contacto en origen.",
    )
    telefono: str | None = Field(
        default=None,
        description="Teléfono de contacto en origen.",
    )
    x_25830: str | None = Field(
        default=None,
        description="Coordenada X en proyección UTM ETRS89 huso 30N (EPSG:25830), en metros.",
    )
    y_25830: str | None = Field(
        default=None,
        description="Coordenada Y en proyección UTM ETRS89 huso 30N (EPSG:25830), en metros.",
    )

