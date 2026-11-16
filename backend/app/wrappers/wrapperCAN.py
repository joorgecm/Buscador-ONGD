"""Wrapper para la fuente de datos de Canarias (JSON)."""

import json
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, settings
from app.schemas.wrapper_can import EntidadCANOrigen

CAMPOS_ORIGEN_CAN: tuple[str, ...] = (
    "nif",
    "denominacion",
    "numero_registro",
    "direccion_tipo_via",
    "direccion_nombre_via",
    "direccion_numero",
    "direccion_complemento",
    "direccion_provincia_id",
    "direccion_provincia_nombre",
    "direccion_municipio_id",
    "direccion_municipio_nombre",
    "direccion_isla_id",
    "direccion_isla_nombre",
    "telefono_1",
    "telefono_2",
    "pagina_web",
    "area_id",
    "area_nombre",
    "subarea_id",
    "subarea_nombre",
)


def _normalizar_celda(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        return None if valor == "" else valor
    return str(valor)


def _contiene_texto(valor_campo: str | None, filtro: str) -> bool:
    if valor_campo is None:
        return False
    return filtro.strip().casefold() in valor_campo.casefold()


class WrapperCAN:
    def __init__(self, json_path: Path | str | None = None) -> None:
        ruta = Path(json_path) if json_path is not None else settings.CAN_JSON_PATH
        if not ruta.is_absolute() and not ruta.exists():
            ruta = BACKEND_DIR / ruta
        self.json_path: Path = ruta

    def _leer_registros(self) -> list[dict[str, Any]]:
        if not self.json_path.is_file():
            raise FileNotFoundError(
                f"No se encontró el archivo JSON de Canarias en: {self.json_path}"
            )
        try:
            datos = json.loads(self.json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"El archivo JSON de Canarias no es válido: {exc}") from exc

        if not isinstance(datos, list):
            raise ValueError("El archivo JSON de Canarias debe contener una lista de entidades")
        return datos

    def obtener_entidades(
        self,
        *,
        numero_registro: str | None = None,
        nif: str | None = None,
        denominacion: str | None = None,
        provincia: str | None = None,
        municipio: str | None = None,
        isla: str | None = None,
        area: str | None = None,
    ) -> list[EntidadCANOrigen]:
        resultados: list[EntidadCANOrigen] = []

        for posicion, raw_item in enumerate(self._leer_registros(), start=1):
            if not isinstance(raw_item, dict):
                continue

            datos_extraidos = {
                campo: _normalizar_celda(raw_item.get(campo)) for campo in CAMPOS_ORIGEN_CAN
            }
            entidad = EntidadCANOrigen(fila=posicion, **datos_extraidos)

            if not self._cumple_filtros(
                entidad,
                numero_registro=numero_registro,
                nif=nif,
                denominacion=denominacion,
                provincia=provincia,
                municipio=municipio,
                isla=isla,
                area=area,
            ):
                continue

            resultados.append(entidad)

        return resultados

    @staticmethod
    def _cumple_filtros(
        entidad: EntidadCANOrigen,
        *,
        numero_registro: str | None,
        nif: str | None,
        denominacion: str | None,
        provincia: str | None,
        municipio: str | None,
        isla: str | None,
        area: str | None,
    ) -> bool:
        if numero_registro is not None and (
            entidad.numero_registro is None
            or entidad.numero_registro.strip() != numero_registro.strip()
        ):
            return False
        if nif is not None and (
            entidad.nif is None or entidad.nif.strip().casefold() != nif.strip().casefold()
        ):
            return False
        if denominacion is not None and not _contiene_texto(entidad.denominacion, denominacion):
            return False
        if provincia is not None and not _contiene_texto(
            entidad.direccion_provincia_nombre, provincia
        ):
            return False
        if municipio is not None and not _contiene_texto(
            entidad.direccion_municipio_nombre, municipio
        ):
            return False
        if isla is not None and not _contiene_texto(entidad.direccion_isla_nombre, isla):
            return False
        if area is not None and not _contiene_texto(entidad.area_nombre, area):
            return False
        return True

