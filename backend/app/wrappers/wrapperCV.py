import csv
import io
from pathlib import Path

from app.core.config import BACKEND_DIR, settings
from app.schemas.wrapper_cv import EntidadCVOrigen

COLUMNAS_ORIGEN_CV: tuple[str, ...] = (
    "WKT",
    "id",
    "tipo_centro",
    "nombre",
    "domici",
    "cod_ine_mun",
    "provincia",
    "municipio",
    "sector",
    "clasificacion",
    "email",
    "telefono",
    "x_25830",
    "y_25830",
)


def _normalizar_celda(valor: str | None) -> str | None:
    if valor is None or valor == "":
        return None
    return valor


def _contiene_texto(valor_campo: str | None, filtro: str) -> bool:
    if valor_campo is None:
        return False
    return filtro.strip().casefold() in valor_campo.casefold()


class WrapperCV:
    def __init__(self, csv_path: Path | str | None = None) -> None:
        ruta = Path(csv_path) if csv_path is not None else settings.CV_CSV_PATH
        if not ruta.is_absolute() and not ruta.exists():
            ruta = BACKEND_DIR / ruta
        self.csv_path: Path = ruta

    def _leer_contenido(self) -> str:
        if not self.csv_path.is_file():
            raise FileNotFoundError(
                f"No se encontró el archivo CSV de la Comunitat Valenciana en: {self.csv_path}"
            )
        try:
            return self.csv_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return self.csv_path.read_text(encoding="cp1252")

    @staticmethod
    def _detectar_delimitador(contenido: str) -> str:
        primera_linea = contenido.splitlines()[0] if contenido else ""
        if "," not in primera_linea and ";" in primera_linea:
            return ";"
        return ","

    def obtener_entidades(
        self,
        *,
        id: str | None = None,
        nombre: str | None = None,
        provincia: str | None = None,
        municipio: str | None = None,
        cod_ine_mun: str | None = None,
        sector: str | None = None,
        tipo_centro: str | None = None,
    ) -> list[EntidadCVOrigen]:
        contenido = self._leer_contenido()
        if not contenido.strip():
            return []

        delimitador = self._detectar_delimitador(contenido)
        reader = csv.DictReader(io.StringIO(contenido), delimiter=delimitador, quotechar='"')

        if reader.fieldnames is None:
            return []

        reader.fieldnames = [col.strip() for col in reader.fieldnames]
        resultados: list[EntidadCVOrigen] = []

        for raw_row in reader:
            fila_actual = reader.line_num

            valores_reales = [
                v for k, v in raw_row.items() if k is not None and v is not None and v.strip() != ""
            ]
            if not valores_reales:
                continue

            datos_extraidos = {
                columna: _normalizar_celda(raw_row.get(columna)) for columna in COLUMNAS_ORIGEN_CV
            }
            entidad = EntidadCVOrigen(fila=fila_actual, **datos_extraidos)

            if not self._cumple_filtros(
                entidad,
                id=id,
                nombre=nombre,
                provincia=provincia,
                municipio=municipio,
                cod_ine_mun=cod_ine_mun,
                sector=sector,
                tipo_centro=tipo_centro,
            ):
                continue

            resultados.append(entidad)

        return resultados

    @staticmethod
    def _cumple_filtros(
        entidad: EntidadCVOrigen,
        *,
        id: str | None,
        nombre: str | None,
        provincia: str | None,
        municipio: str | None,
        cod_ine_mun: str | None,
        sector: str | None,
        tipo_centro: str | None,
    ) -> bool:
        if id is not None and (entidad.id is None or entidad.id.strip() != id.strip()):
            return False
        if cod_ine_mun is not None and (
            entidad.cod_ine_mun is None or entidad.cod_ine_mun.strip() != cod_ine_mun.strip()
        ):
            return False
        if nombre is not None and not _contiene_texto(entidad.nombre, nombre):
            return False
        if provincia is not None and not _contiene_texto(entidad.provincia, provincia):
            return False
        if municipio is not None and not _contiene_texto(entidad.municipio, municipio):
            return False
        if sector is not None and not _contiene_texto(entidad.sector, sector):
            return False
        if tipo_centro is not None and not _contiene_texto(entidad.tipo_centro, tipo_centro):
            return False
        return True
