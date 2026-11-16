"""Esquemas Pydantic para el Wrapper de Canarias (JSON)."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class EntidadCANOrigen(BaseModel):
    """Registro crudo leído del JSON de Canarias manteniendo los campos de origen."""

    fila: int = Field(
        ...,
        ge=1,
        description="Posición del elemento en la lista JSON original (empezando en 1).",
    )
    nif: str | None = Field(default=None, description="NIF de la entidad.")
    denominacion: str | None = Field(default=None, description="Nombre oficial de la entidad.")
    numero_registro: str | None = Field(
        default=None,
        description="Número oficial en el Registro de Entidades de Canarias.",
    )
    direccion_tipo_via: str | None = Field(default=None, description="Tipo de vía en origen.")
    direccion_nombre_via: str | None = Field(default=None, description="Nombre de la vía.")
    direccion_numero: str | None = Field(default=None, description="Número de portal.")
    direccion_complemento: str | None = Field(
        default=None,
        description="Complemento de la dirección (piso, puerta, etc.).",
    )
    direccion_provincia_id: str | None = Field(default=None, description="Código de provincia.")
    direccion_provincia_nombre: str | None = Field(
        default=None,
        description="Nombre de provincia en origen.",
    )
    direccion_municipio_id: str | None = Field(default=None, description="Código municipal.")
    direccion_municipio_nombre: str | None = Field(
        default=None,
        description="Nombre del municipio en origen.",
    )
    direccion_isla_id: str | None = Field(default=None, description="Código de isla.")
    direccion_isla_nombre: str | None = Field(default=None, description="Nombre de isla.")
    telefono_1: str | None = Field(default=None, description="Teléfono principal.")
    telefono_2: str | None = Field(default=None, description="Teléfono secundario.")
    pagina_web: str | None = Field(default=None, description="Página web en origen.")
    area_id: str | None = Field(default=None, description="Código de área de actuación.")
    area_nombre: str | None = Field(default=None, description="Nombre del área de actuación.")
    subarea_id: str | None = Field(default=None, description="Código de subárea.")
    subarea_nombre: str | None = Field(default=None, description="Nombre de la subárea.")

    @field_validator("*", mode="before")
    @classmethod
    def _normalizar_valor(cls, valor: Any, info: Any) -> Any:
        if info.field_name == "fila" or valor is None:
            return valor
        if isinstance(valor, bool):
            return str(valor)
        if isinstance(valor, (int, float)):
            return str(valor)
        if isinstance(valor, str):
            return None if valor == "" else valor
        return str(valor)

