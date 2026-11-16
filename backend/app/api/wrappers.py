"""Endpoints REST de búsqueda sobre los Wrappers de las fuentes de datos."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.schemas.wrapper_cv import EntidadCVOrigen
from app.wrappers.wrapperCV import WrapperCV

router = APIRouter(prefix="/wrappers", tags=["Wrappers"])


@router.get(
    "/cv",
    response_model=list[EntidadCVOrigen],
    summary="API de búsqueda del Wrapper de la Comunitat Valenciana",
    description=(
        "Accede a la fuente de datos CSV de la Comunitat Valenciana mediante `WrapperCV` "
        "y devuelve los registros en formato JSON siguiendo el esquema de origen, "
        "permitiendo filtrado opcional por sus atributos principales."
    ),
)
def buscar_entidades_cv(
    id: Annotated[
        str | None,
        Query(description="Filtrar por identificador exacto en el CSV."),
    ] = None,
    nombre: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el nombre del centro."),
    ] = None,
    provincia: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el nombre de la provincia."),
    ] = None,
    municipio: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el municipio."),
    ] = None,
    cod_ine_mun: Annotated[
        str | None,
        Query(description="Filtrar por código INE exacto del municipio."),
    ] = None,
    sector: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el sector de actuación."),
    ] = None,
    tipo_centro: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el tipo de centro."),
    ] = None,
) -> list[EntidadCVOrigen]:
    """Devuelve las entidades leídas desde el archivo CSV de la Comunitat Valenciana."""
    wrapper = WrapperCV()
    try:
        return wrapper.obtener_entidades(
            id=id,
            nombre=nombre,
            provincia=provincia,
            municipio=municipio,
            cod_ine_mun=cod_ine_mun,
            sector=sector,
            tipo_centro=tipo_centro,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

