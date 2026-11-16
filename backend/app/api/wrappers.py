"""Endpoints REST de búsqueda sobre los Wrappers de las fuentes de datos."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from lxml import etree

from app.schemas.wrapper_can import EntidadCANOrigen
from app.schemas.wrapper_cat import EntidadCATOrigen
from app.schemas.wrapper_cv import EntidadCVOrigen
from app.wrappers.wrapperCAN import WrapperCAN
from app.wrappers.wrapperCAT import WrapperCAT
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


@router.get(
    "/cat",
    response_model=list[EntidadCATOrigen],
    summary="API de búsqueda del Wrapper de Catalunya",
    description=(
        "Accede a la fuente de datos XML de Catalunya mediante `WrapperCAT` "
        "y devuelve los registros en formato JSON siguiendo el esquema de origen, "
        "permitiendo filtrado opcional por sus atributos principales."
    ),
)
def buscar_entidades_cat(
    n_mero_registre: Annotated[
        str | None,
        Query(description="Filtrar por número de registro exacto."),
    ] = None,
    nombre: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el nombre de la entidad."),
    ] = None,
    municipio: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el municipio."),
    ] = None,
    codigo_postal: Annotated[
        str | None,
        Query(description="Filtrar por código postal exacto."),
    ] = None,
    naturaleza: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en la naturaleza jurídica."),
    ] = None,
) -> list[EntidadCATOrigen]:
    """Devuelve las entidades leídas desde el archivo XML de Catalunya."""
    wrapper = WrapperCAT()
    try:
        return wrapper.obtener_entidades(
            n_mero_registre=n_mero_registre,
            nombre=nombre,
            municipio=municipio,
            codigo_postal=codigo_postal,
            naturaleza=naturaleza,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/can",
    response_model=list[EntidadCANOrigen],
    summary="API de búsqueda del Wrapper de Canarias",
    description=(
        "Accede a la fuente de datos JSON de Canarias mediante `WrapperCAN` "
        "y devuelve los registros en formato JSON siguiendo el esquema de origen, "
        "permitiendo filtrado opcional por sus atributos principales."
    ),
)
def buscar_entidades_can(
    numero_registro: Annotated[
        str | None,
        Query(description="Filtrar por número de registro exacto."),
    ] = None,
    nif: Annotated[
        str | None,
        Query(description="Filtrar por NIF exacto."),
    ] = None,
    denominacion: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en la denominación."),
    ] = None,
    provincia: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el nombre de la provincia."),
    ] = None,
    municipio: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el municipio."),
    ] = None,
    isla: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en la isla."),
    ] = None,
    area: Annotated[
        str | None,
        Query(description="Filtrar por coincidencia parcial en el área de actuación."),
    ] = None,
) -> list[EntidadCANOrigen]:
    """Devuelve las entidades leídas desde el archivo JSON de Canarias."""
    wrapper = WrapperCAN()
    try:
        return wrapper.obtener_entidades(
            numero_registro=numero_registro,
            nif=nif,
            denominacion=denominacion,
            provincia=provincia,
            municipio=municipio,
            isla=isla,
            area=area,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

