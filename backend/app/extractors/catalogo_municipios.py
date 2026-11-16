import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.core.config import BACKEND_DIR, settings

_ARTICULO_ENTRE_PARENTESIS_RE = re.compile(
    r"^(?P<nombre>.+?)\((?P<articulo>l'|la|el|els|les)\)$", re.I
)


@dataclass(frozen=True, slots=True)
class MunicipioCat:
    cod_ine: str
    nombre: str
    cod_provincia: str


def clave_texto(texto: str | None) -> str:
    if not texto:
        return ""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]", "", sin_tildes)


class CatalogoMunicipios:
    def __init__(self, csv_path: Path | str | None = None) -> None:
        ruta = Path(csv_path) if csv_path is not None else settings.MUNICIPIOS_CAT_PATH
        if not ruta.is_absolute() and not ruta.exists():
            ruta = BACKEND_DIR / ruta
        if not ruta.is_file():
            raise FileNotFoundError(f"No se encontró el catálogo de municipios en: {ruta}")

        self.municipios: list[MunicipioCat] = []
        with ruta.open(encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                self.municipios.append(
                    MunicipioCat(fila["cod_ine"], fila["nombre"], fila["cod_provincia"])
                )

        self._por_clave: dict[str, MunicipioCat] = {
            clave_texto(m.nombre): m for m in self.municipios
        }

    @staticmethod
    def _normalizar_articulo(texto: str) -> str:
        coincidencia = _ARTICULO_ENTRE_PARENTESIS_RE.match(texto.strip())
        if coincidencia is None:
            return texto
        articulo = coincidencia.group("articulo").casefold()
        nombre = coincidencia.group("nombre")
        return f"{articulo}{nombre}" if articulo.endswith("'") else f"{articulo} {nombre}"

    def resolver(self, texto: str | None) -> MunicipioCat | None:
        if not texto or not texto.strip():
            return None
        clave = clave_texto(self._normalizar_articulo(texto))
        if not clave:
            return None
        exacto = self._por_clave.get(clave)
        if exacto is not None:
            return exacto
        candidatos = [m for k, m in self._por_clave.items() if k.startswith(clave)]
        if len(candidatos) == 1:
            return candidatos[0]
        return None

    def provincia_de(self, texto: str | None) -> str | None:
        municipio = self.resolver(texto)
        return municipio.cod_provincia if municipio else None
