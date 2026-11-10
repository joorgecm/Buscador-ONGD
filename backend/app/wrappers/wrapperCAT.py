from pathlib import Path

from lxml import etree

from app.core.config import BACKEND_DIR, settings
from app.schemas.wrapper_cat import EntidadCATOrigen

CAMPOS_ORIGEN_CAT: tuple[str, ...] = (
    "n_mero_registre",
    "nom_de_l_entitat",
    "naturalesa",
    "cif_entitat",
    "adre_a",
    "codi_postal",
    "municipi",
    "tel_fon",
    "tel_fon_m_bil",
    "correu_electr_nic",
    "web",
)


def _normalizar_texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    texto = valor.strip()
    if texto == "":
        return None
    return texto


def _contiene_texto(valor_campo: str | None, filtro: str) -> bool:
    if valor_campo is None:
        return False
    return filtro.strip().casefold() in valor_campo.casefold()


class WrapperCAT:
    def __init__(self, xml_path: Path | str | None = None) -> None:
        ruta = Path(xml_path) if xml_path is not None else settings.CAT_XML_PATH
        if not ruta.is_absolute() and not ruta.exists():
            ruta = BACKEND_DIR / ruta
        self.xml_path: Path = ruta

    def _leer_elementos(self) -> list[etree._Element]:
        if not self.xml_path.is_file():
            raise FileNotFoundError(
                f"No se encontró el archivo XML de Catalunya en: {self.xml_path}"
            )
        arbol = etree.parse(str(self.xml_path), etree.XMLParser(remove_blank_text=True))
        return arbol.getroot().findall("entitat")

    def obtener_entidades(
        self,
        *,
        n_mero_registre: str | None = None,
        nombre: str | None = None,
        municipio: str | None = None,
        codigo_postal: str | None = None,
        naturaleza: str | None = None,
    ) -> list[EntidadCATOrigen]:
        resultados: list[EntidadCATOrigen] = []

        for posicion, elemento in enumerate(self._leer_elementos(), start=1):
            datos_extraidos = {
                campo: _normalizar_texto(elemento.findtext(campo)) for campo in CAMPOS_ORIGEN_CAT
            }
            entidad = EntidadCATOrigen(fila=posicion, **datos_extraidos)

            if not self._cumple_filtros(
                entidad,
                n_mero_registre=n_mero_registre,
                nombre=nombre,
                municipio=municipio,
                codigo_postal=codigo_postal,
                naturaleza=naturaleza,
            ):
                continue

            resultados.append(entidad)

        return resultados

    @staticmethod
    def _cumple_filtros(
        entidad: EntidadCATOrigen,
        *,
        n_mero_registre: str | None,
        nombre: str | None,
        municipio: str | None,
        codigo_postal: str | None,
        naturaleza: str | None,
    ) -> bool:
        if n_mero_registre is not None and (
            entidad.n_mero_registre is None
            or entidad.n_mero_registre.strip() != n_mero_registre.strip()
        ):
            return False
        if codigo_postal is not None and (
            entidad.codi_postal is None or entidad.codi_postal.strip() != codigo_postal.strip()
        ):
            return False
        if nombre is not None and not _contiene_texto(entidad.nom_de_l_entitat, nombre):
            return False
        if municipio is not None and not _contiene_texto(entidad.municipi, municipio):
            return False
        if naturaleza is not None and not _contiene_texto(entidad.naturalesa, naturaleza):
            return False
        return True
