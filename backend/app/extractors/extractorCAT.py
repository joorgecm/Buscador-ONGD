import re
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.extractors.catalogo_municipios import CatalogoMunicipios, clave_texto
from app.extractors.common import (
    EntidadExtraida,
    Fuente,
    ResultadoExtraccion,
    TipoError,
)
from app.extractors.extractorCV import ExtractorCV
from app.extractors.reparacion_texto import ReparadorTexto
from app.llm.clasificador_ambito import ClasificadorAmbito
from app.models.ambito import Ambito
from app.schemas.wrapper_cat import EntidadCATOrigen
from app.scraper.geocoder import GeoScraper, ScraperGeo
from app.wrappers.wrapperCAT import WrapperCAT

PROVINCIAS_CAT: dict[str, str] = {
    "08": "Barcelona",
    "17": "Girona",
    "25": "Lleida",
    "43": "Tarragona",
}

LAT_MIN_CAT, LAT_MAX_CAT = 40.4, 42.95
LON_MIN_CAT, LON_MAX_CAT = 0.1, 3.4

_CP_RE = re.compile(r"^\d{5}$")
_SEPARADOR_TELEFONOS_RE = re.compile(r"[\n;,/]+")


@dataclass(slots=True)
class _Candidata:
    fila: int
    nombre: str
    naturaleza: str | None
    direccion: str | None
    codigo_postal: str | None
    nombre_localidad: str
    codigo_provincia: str
    contacto: str | None
    url: str | None


class ExtractorCAT:
    def __init__(
        self,
        *,
        wrapper_url: str | None = None,
        wrapper: WrapperCAT | None = None,
        scraper: GeoScraper | None = None,
        usar_scraper: bool = True,
        catalogo: CatalogoMunicipios | None = None,
        clasificador: ClasificadorAmbito | None = None,
    ) -> None:
        self.wrapper_url = wrapper_url or settings.WRAPPER_CAT_URL
        self.wrapper = wrapper
        self.scraper = scraper
        self.usar_scraper = usar_scraper
        self.catalogo = catalogo
        self.clasificador = clasificador

    def _obtener_registros_origen(self) -> list[EntidadCATOrigen]:
        if self.wrapper is not None:
            return self.wrapper.obtener_entidades()

        response = httpx.get(self.wrapper_url, timeout=30.0)
        response.raise_for_status()
        return [EntidadCATOrigen.model_validate(item) for item in response.json()]

    def extraer(self) -> ResultadoExtraccion:
        scraper_propio: ScraperGeo | None = None
        scraper_activo: GeoScraper | None = self.scraper
        if scraper_activo is None and self.usar_scraper:
            scraper_propio = ScraperGeo()
            scraper_activo = scraper_propio

        try:
            return self._ejecutar_extraccion(scraper_activo)
        finally:
            if scraper_propio is not None:
                scraper_propio.cerrar()

    def _ejecutar_extraccion(self, scraper_activo: GeoScraper | None) -> ResultadoExtraccion:
        resultado = ResultadoExtraccion(fuente=Fuente.CAT)
        registros = self._obtener_registros_origen()

        catalogo = self.catalogo or CatalogoMunicipios()
        reparador = ReparadorTexto(
            [t for r in registros for t in (r.nom_de_l_entitat, r.adre_a) if t], catalogo
        )

        candidatas = self._preparar_candidatas(registros, catalogo, reparador, resultado)
        ambitos = self._clasificar(candidatas, resultado)

        for candidata, ambito in zip(candidatas, ambitos, strict=True):
            self._completar_y_agregar(candidata, ambito, scraper_activo, resultado)

        return resultado

    def _preparar_candidatas(
        self,
        registros: list[EntidadCATOrigen],
        catalogo: CatalogoMunicipios,
        reparador: ReparadorTexto,
        resultado: ResultadoExtraccion,
    ) -> list[_Candidata]:
        registros_vistos: set[str] = set()
        cifs_vistos: set[str] = set()
        claves_vistas: set[tuple[str, str, str]] = set()
        candidatas: list[_Candidata] = []

        for reg in registros:
            fila = reg.fila

            numero = reg.n_mero_registre.strip() if reg.n_mero_registre else None
            if numero:
                if numero in registros_vistos:
                    resultado.error(
                        fila,
                        "n_mero_registre",
                        TipoError.DUPLICADO,
                        f"Número de registro duplicado en origen: '{numero}'",
                    )
                    continue
                registros_vistos.add(numero)

            cif = reg.cif_entitat.strip().upper() if reg.cif_entitat else None
            if cif:
                if cif in cifs_vistos:
                    resultado.error(
                        fila,
                        "cif_entitat",
                        TipoError.DUPLICADO,
                        f"CIF duplicado en origen: '{cif}'",
                    )
                    continue
                cifs_vistos.add(cif)

            nombre = self._reparar_campo(
                fila,
                "nom_de_l_entitat",
                reg.nom_de_l_entitat,
                reparador.reparar_texto(reg.nom_de_l_entitat, es_nombre=True),
                resultado,
            )
            if not nombre:
                resultado.error(
                    fila, "nom_de_l_entitat", TipoError.NULO, "El nombre de la entidad es nulo"
                )
                continue

            localidad = self._resolver_localidad(reg, catalogo, resultado)
            if localidad is None:
                continue
            nombre_localidad, codigo_provincia, codigo_postal = localidad

            direccion = self._reparar_campo(
                fila,
                "adre_a",
                reg.adre_a,
                reparador.reparar_texto(reg.adre_a),
                resultado,
            )

            clave_unica = (
                clave_texto(nombre),
                clave_texto(nombre_localidad),
                clave_texto(direccion),
            )
            if clave_unica in claves_vistas:
                resultado.error(
                    fila,
                    "nom_de_l_entitat",
                    TipoError.DUPLICADO,
                    f"Entidad duplicada: '{nombre}' en '{nombre_localidad}'",
                )
                continue
            claves_vistas.add(clave_unica)

            contacto = self._resolver_contacto(reg, reparador, resultado)
            url = self._resolver_url(reg, reparador, resultado)

            candidatas.append(
                _Candidata(
                    fila=fila,
                    nombre=nombre,
                    naturaleza=reg.naturalesa,
                    direccion=direccion,
                    codigo_postal=codigo_postal,
                    nombre_localidad=nombre_localidad,
                    codigo_provincia=codigo_provincia,
                    contacto=contacto,
                    url=url,
                )
            )

        return candidatas

    @staticmethod
    def _reparar_campo(
        fila: int,
        campo: str,
        original: str | None,
        reparado: str | None,
        resultado: ResultadoExtraccion,
    ) -> str | None:
        if original is None:
            return None
        if reparado is not None and reparado != original:
            resultado.reparacion(
                fila,
                campo,
                original,
                reparado,
                "Reposición heurística de espacios y puntos eliminados en origen",
            )
        return reparado

    def _resolver_localidad(
        self,
        reg: EntidadCATOrigen,
        catalogo: CatalogoMunicipios,
        resultado: ResultadoExtraccion,
    ) -> tuple[str, str, str | None] | None:
        fila = reg.fila
        municipio_raw = reg.municipi.strip() if reg.municipi else ""
        if not municipio_raw:
            resultado.error(fila, "municipi", TipoError.NULO, "El municipio es nulo")
            return None

        cp_raw = reg.codi_postal.strip() if reg.codi_postal else ""
        codigo_cp = self._provincia_de_cp(cp_raw)
        municipio = catalogo.resolver(municipio_raw)

        if municipio is None:
            if codigo_cp is None:
                resultado.error(
                    fila,
                    "municipi",
                    TipoError.SEMANTICO,
                    f"Municipio '{municipio_raw}' no pertenece a Catalunya y el código postal "
                    f"'{cp_raw}' no es catalán",
                )
                return None
            resultado.reparacion(
                fila,
                "municipi",
                municipio_raw,
                municipio_raw,
                "Municipio no encontrado en el catálogo; provincia deducida del código postal",
            )
            return municipio_raw, codigo_cp, cp_raw

        if municipio.nombre != municipio_raw:
            resultado.reparacion(
                fila,
                "municipi",
                municipio_raw,
                municipio.nombre,
                "Nombre oficial del municipio a partir del catálogo",
            )

        if not cp_raw:
            return municipio.nombre, municipio.cod_provincia, None

        if not _CP_RE.fullmatch(cp_raw):
            resultado.error(
                fila,
                "codi_postal",
                TipoError.FORMATO,
                f"Código postal con formato no válido: '{cp_raw}'",
            )
            return municipio.nombre, municipio.cod_provincia, None

        if cp_raw[:2] != municipio.cod_provincia:
            resultado.error(
                fila,
                "codi_postal",
                TipoError.SEMANTICO,
                f"El código postal '{cp_raw}' no corresponde a la provincia "
                f"{PROVINCIAS_CAT[municipio.cod_provincia]} de '{municipio.nombre}'",
            )
            return municipio.nombre, municipio.cod_provincia, None

        return municipio.nombre, municipio.cod_provincia, cp_raw

    @staticmethod
    def _provincia_de_cp(cp: str) -> str | None:
        if _CP_RE.fullmatch(cp) and cp[:2] in PROVINCIAS_CAT:
            return cp[:2]
        return None

    def _clasificar(
        self, candidatas: list[_Candidata], resultado: ResultadoExtraccion
    ) -> list[Ambito]:
        if not candidatas:
            return []
        clasificador = self.clasificador or ClasificadorAmbito()
        respuestas = clasificador.clasificar([(c.nombre, c.naturaleza) for c in candidatas])
        for candidata, respuesta in zip(candidatas, respuestas, strict=True):
            if respuesta.por_defecto:
                resultado.reparacion(
                    candidata.fila,
                    "ambito",
                    None,
                    respuesta.ambito.value,
                    f"Ámbito por defecto: {respuesta.motivo}",
                )
        return [r.ambito for r in respuestas]

    def _completar_y_agregar(
        self,
        candidata: _Candidata,
        ambito: Ambito,
        scraper_activo: GeoScraper | None,
        resultado: ResultadoExtraccion,
    ) -> None:
        fila = candidata.fila
        nombre_provincia = PROVINCIAS_CAT[candidata.codigo_provincia]
        longitud: float | None = None
        latitud: float | None = None
        codigo_postal = candidata.codigo_postal

        if scraper_activo is not None:
            geo = scraper_activo.geocodificar(
                direccion=candidata.direccion,
                municipio=candidata.nombre_localidad,
                provincia=nombre_provincia,
            )
            if geo.latitud is not None and geo.longitud is not None:
                if LAT_MIN_CAT <= geo.latitud <= LAT_MAX_CAT and (
                    LON_MIN_CAT <= geo.longitud <= LON_MAX_CAT
                ):
                    latitud = round(geo.latitud, 6)
                    longitud = round(geo.longitud, 6)
                else:
                    resultado.error(
                        fila,
                        "coordenadas",
                        TipoError.FUERA_DE_RANGO,
                        f"Coordenadas fuera de Catalunya (lat={geo.latitud:.4f}, "
                        f"lon={geo.longitud:.4f})",
                    )
            if codigo_postal is None and geo.codigo_postal:
                cp_geo = geo.codigo_postal.strip()
                if _CP_RE.fullmatch(cp_geo) and cp_geo[:2] == candidata.codigo_provincia:
                    codigo_postal = cp_geo
                    resultado.reparacion(
                        fila,
                        "codi_postal",
                        None,
                        cp_geo,
                        "Código postal obtenido mediante geocodificación de la dirección",
                    )

        if (
            latitud is None
            and longitud is None
            and not any(e.fila == fila and e.campo == "coordenadas" for e in resultado.errores)
        ):
            resultado.error(
                fila,
                "coordenadas",
                TipoError.NULO,
                "No se pudieron obtener coordenadas para la dirección",
            )

        resultado.entidades.append(
            EntidadExtraida(
                nombre=candidata.nombre[:300],
                ambito=ambito,
                direccion=candidata.direccion[:300] if candidata.direccion else None,
                codigo_postal=codigo_postal,
                longitud=longitud,
                latitud=latitud,
                descripcion=candidata.naturaleza,
                contacto=candidata.contacto[:300] if candidata.contacto else None,
                url=candidata.url[:300] if candidata.url else None,
                nombre_localidad=candidata.nombre_localidad[:150],
                codigo_provincia=candidata.codigo_provincia,
                nombre_provincia=nombre_provincia,
            )
        )

    def _resolver_contacto(
        self,
        reg: EntidadCATOrigen,
        reparador: ReparadorTexto,
        resultado: ResultadoExtraccion,
    ) -> str | None:
        telefonos: list[str] = []
        for bruto in (reg.tel_fon, reg.tel_fon_m_bil):
            for trozo in _SEPARADOR_TELEFONOS_RE.split(bruto or ""):
                limpio = ExtractorCV._limpiar_telefono(reg.fila, trozo, resultado)
                if limpio:
                    telefonos.extend(limpio.split(" / "))
        telefonos = list(dict.fromkeys(telefonos))

        email = self._resolver_email(reg, reparador, resultado)

        partes: list[str] = []
        if telefonos:
            partes.append(f"Tel: {' / '.join(telefonos)}")
        if email:
            partes.append(f"Email: {email}")
        return " | ".join(partes) if partes else None

    @staticmethod
    def _resolver_email(
        reg: EntidadCATOrigen,
        reparador: ReparadorTexto,
        resultado: ResultadoExtraccion,
    ) -> str | None:
        bruto = reg.correu_electr_nic
        if not bruto:
            return None
        reparado = reparador.reparar_email(bruto)
        if reparado is None or not reparador.email_valido(reparado):
            resultado.error(
                reg.fila,
                "correu_electr_nic",
                TipoError.FORMATO,
                f"Correo electrónico no reparable: '{bruto}'",
            )
            return None
        if reparado != bruto:
            resultado.reparacion(
                reg.fila,
                "correu_electr_nic",
                bruto,
                reparado,
                "Reposición de puntos eliminados y separación de correos",
            )
        return reparado

    @staticmethod
    def _resolver_url(
        reg: EntidadCATOrigen,
        reparador: ReparadorTexto,
        resultado: ResultadoExtraccion,
    ) -> str | None:
        bruto = reg.web
        if not bruto:
            return None
        reparado = reparador.reparar_url(bruto)
        if reparado is None:
            resultado.error(
                reg.fila, "web", TipoError.FORMATO, f"Dirección web no reparable: '{bruto}'"
            )
            return None
        if reparado != bruto:
            resultado.reparacion(
                reg.fila,
                "web",
                bruto,
                reparado,
                "Reposición de puntos eliminados y normalización del esquema",
            )
        return reparado
