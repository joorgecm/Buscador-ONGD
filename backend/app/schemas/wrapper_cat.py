"""Esquemas Pydantic para el Wrapper de Catalunya (XML -> JSON)."""

from pydantic import BaseModel, Field


class EntidadCATOrigen(BaseModel):
    """Registro crudo leído del XML del Registre d'ONGD según los campos del mapping.

    Los textos conservan la pérdida de espacios y puntos del origen; el extractor los repara.
    """

    fila: int = Field(
        ...,
        ge=1,
        description="Posición del elemento <entitat> en el XML original (empezando en 1).",
    )
    n_mero_registre: str | None = Field(
        default=None,
        description="Número de registro de la entidad (solo para detectar duplicados).",
    )
    nom_de_l_entitat: str | None = Field(
        default=None,
        description="Nombre de la entidad, sin espacios entre palabras en origen.",
    )
    naturalesa: str | None = Field(
        default=None,
        description="Naturaleza jurídica (Associació, Fundació, Cooperativa...).",
    )
    cif_entitat: str | None = Field(
        default=None,
        description="CIF de la entidad (solo para detectar duplicados, no se carga).",
    )
    adre_a: str | None = Field(
        default=None,
        description="Dirección postal, sin espacios entre palabras en origen.",
    )
    codi_postal: str | None = Field(
        default=None,
        description="Código postal de 5 dígitos.",
    )
    municipi: str | None = Field(
        default=None,
        description="Municipio, sin espacios entre palabras en origen.",
    )
    tel_fon: str | None = Field(
        default=None,
        description="Teléfono fijo.",
    )
    tel_fon_m_bil: str | None = Field(
        default=None,
        description="Teléfono móvil; puede contener varios números separados por salto de línea.",
    )
    correu_electr_nic: str | None = Field(
        default=None,
        description="Correo electrónico, con los puntos eliminados en origen.",
    )
    web: str | None = Field(
        default=None,
        description="Página web, con los puntos eliminados en origen.",
    )
