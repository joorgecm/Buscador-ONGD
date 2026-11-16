import re
import unicodedata

import httpx
from pyproj import Transformer

from app.core.config import settings
from app.extractors.common import (
    EntidadExtraida,
    Fuente,
    ResultadoExtraccion,
    TipoError,
)
from app.models.ambito import Ambito
from app.schemas.wrapper_cv import EntidadCVOrigen
from app.scraper.geocoder import GeoScraper, ScraperGeo
from app.wrappers.wrapperCV import WrapperCV

PROVINCIAS_CV: dict[str, str] = {
    "03": "Alacant/Alicante",
    "12": "Castelló/Castellón",
    "46": "València/Valencia",
}

LAT_MIN_CV, LAT_MAX_CV = 37.7, 41.0
LON_MIN_CV, LON_MAX_CV = -1.7, 0.8

_WKT_POINT_RE = re.compile(
    r"POINT\s*\(\s*([+-]?\d+(?:[.,]\d+)?)\s+([+-]?\d+(?:[.,]\d+)?)\s*\)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CP_RE = re.compile(r"^\d{5}$")

_TRANSFORMER_25830_A_WGS84 = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)


def _normalizar_clave(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.upper().split())


def _mapear_ambito(sector: str | None, tipo_centro: str | None) -> Ambito | None:
    if not sector or not sector.strip():
        return None

    clave_sector = _normalizar_clave(sector)
    directos: dict[str, Ambito] = {
        "PERSONAS MAYORES": Ambito.MAYORES,
        "PERSONAS CON DISCAPACIDAD": Ambito.DISCAPACIDAD,
        "PERSONAS CON ENFERMEDAD MENTAL": Ambito.SALUD_MENTAL,
        "INFANCIA": Ambito.INFANCIA_Y_JUVENTUD,
        "MUJERES": Ambito.MUJER,
        "PERSONAS MIGRANTES": Ambito.MIGRACION,
    }
    if clave_sector in directos:
        return directos[clave_sector]

    if clave_sector.startswith("POBLACION EN GENERAL"):
        clave_tipo = _normalizar_clave(tipo_centro) if tipo_centro else ""
        if "TALLER PRELABORAL DE INSERCION SOCIAL" in clave_tipo:
            return Ambito.EMPLEO_E_INSERCION_LABORAL
        if "CLUBS DE CONVIVENCIA" in clave_tipo or "CLUB DE CONVIVENCIA" in clave_tipo:
            return Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO
        return Ambito.INCLUSION_SOCIAL

    return None


def _deducir_codigo_provincia(nombre_provincia: str | None) -> str | None:
    if not nombre_provincia or not nombre_provincia.strip():
        return None
    clave = _normalizar_clave(nombre_provincia)
    if "ALACANT" in clave or "ALICANTE" in clave:
        return "03"
    if "CASTELLO" in clave:
        return "12"
    if "VALENCIA" in clave:
        return "46"
    return None


class ExtractorCV:
    def __init__(
        self,
        *,
        wrapper_url: str | None = None,
        wrapper: WrapperCV | None = None,
        scraper: GeoScraper | None = None,
        usar_scraper: bool = True,
    ) -> None:
        self.wrapper_url = wrapper_url or settings.WRAPPER_CV_URL
        self.wrapper = wrapper
        self.scraper = scraper
        self.usar_scraper = usar_scraper

    def _obtener_registros_origen(self) -> list[EntidadCVOrigen]:
        if self.wrapper is not None:
            return self.wrapper.obtener_entidades()

        response = httpx.get(self.wrapper_url, timeout=30.0)
        response.raise_for_status()
        return [EntidadCVOrigen.model_validate(item) for item in response.json()]

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
        resultado = ResultadoExtraccion(fuente=Fuente.CV)
        registros = self._obtener_registros_origen()

        ids_vistos: set[str] = set()
        claves_vistas: set[tuple[str, str, str, str, str]] = set()

        for reg in registros:
            fila = reg.fila

            id_limpio = reg.id.strip() if reg.id else None
            if id_limpio:
                if id_limpio in ids_vistos:
                    resultado.error(
                        fila,
                        "id",
                        TipoError.DUPLICADO,
                        f"Identificador duplicado en origen: '{id_limpio}'",
                    )
                    continue
                ids_vistos.add(id_limpio)

            nombre = reg.nombre.strip() if reg.nombre else ""
            if not nombre:
                resultado.error(fila, "nombre", TipoError.NULO, "El nombre de la entidad es nulo")
                continue

            nombre_localidad = reg.municipio.strip() if reg.municipio else ""
            if not nombre_localidad:
                resultado.error(fila, "municipio", TipoError.NULO, "El municipio es nulo")
                continue

            ambito = self._resolver_ambito(reg, resultado)
            if ambito is None:
                continue

            provincia_info = self._resolver_provincia(reg, resultado)
            if provincia_info is None:
                continue
            codigo_provincia, nombre_provincia = provincia_info

            direccion = reg.domici.strip() if reg.domici and reg.domici.strip() else None
            descripcion = (
                reg.tipo_centro.strip() if reg.tipo_centro and reg.tipo_centro.strip() else None
            )

            clave_unica = (
                _normalizar_clave(nombre),
                ambito.value,
                _normalizar_clave(nombre_localidad),
                _normalizar_clave(direccion or ""),
                _normalizar_clave(descripcion or ""),
            )
            if clave_unica in claves_vistas:
                resultado.error(
                    fila,
                    "nombre",
                    TipoError.DUPLICADO,
                    f"Entidad duplicada: '{nombre}' en '{nombre_localidad}'",
                )
                continue

            coords = self._resolver_coordenadas(
                reg,
                direccion=direccion,
                municipio=nombre_localidad,
                provincia=nombre_provincia,
                scraper_activo=scraper_activo,
                resultado=resultado,
            )
            if coords is None:
                continue
            longitud, latitud, cp_scraper = coords

            codigo_postal = self._resolver_codigo_postal(
                cp_candidato=cp_scraper,
                direccion=direccion,
                municipio=nombre_localidad,
                provincia=nombre_provincia,
                latitud=latitud,
                longitud=longitud,
                codigo_provincia=codigo_provincia,
                scraper_activo=scraper_activo,
            )

            contacto = self._resolver_contacto(reg, resultado)

            claves_vistas.add(clave_unica)
            resultado.entidades.append(
                EntidadExtraida(
                    nombre=nombre[:300],
                    ambito=ambito,
                    direccion=direccion[:300] if direccion else None,
                    codigo_postal=codigo_postal,
                    longitud=longitud,
                    latitud=latitud,
                    descripcion=descripcion,
                    contacto=contacto[:300] if contacto else None,
                    url=None,
                    nombre_localidad=nombre_localidad[:150],
                    codigo_provincia=codigo_provincia,
                    nombre_provincia=nombre_provincia[:100],
                )
            )

        return resultado

    def _resolver_ambito(
        self, reg: EntidadCVOrigen, resultado: ResultadoExtraccion
    ) -> Ambito | None:
        ambito = _mapear_ambito(reg.sector, reg.tipo_centro)
        if ambito is not None:
            return ambito

        ambito_respaldo = _mapear_ambito(reg.clasificacion, reg.tipo_centro)
        if ambito_respaldo is not None and reg.clasificacion:
            resultado.reparacion(
                reg.fila,
                "sector",
                reg.sector,
                reg.clasificacion.strip(),
                "Sector recuperado a partir del campo clasificacion",
            )
            return ambito_respaldo

        if not reg.sector or not reg.sector.strip():
            resultado.error(reg.fila, "sector", TipoError.NULO, "El campo sector es nulo")
        else:
            resultado.error(
                reg.fila,
                "sector",
                TipoError.SEMANTICO,
                f"Valor de sector no reconocido: '{reg.sector.strip()}'",
            )
        return None

    def _resolver_provincia(
        self, reg: EntidadCVOrigen, resultado: ResultadoExtraccion
    ) -> tuple[str, str] | None:
        fila = reg.fila
        ine_raw = reg.cod_ine_mun.strip() if reg.cod_ine_mun else ""
        ine_norm = ine_raw

        if ine_raw.isdigit() and 0 < len(ine_raw) < 5:
            ine_norm = ine_raw.zfill(5)
            resultado.reparacion(
                fila,
                "cod_ine_mun",
                reg.cod_ine_mun,
                ine_norm,
                "Relleno con ceros a la izquierda hasta 5 dígitos",
            )

        prefijo_ine = (
            ine_norm[:2]
            if len(ine_norm) == 5 and ine_norm.isdigit() and ine_norm[:2] in PROVINCIAS_CV
            else None
        )
        cod_por_nombre = _deducir_codigo_provincia(reg.provincia)

        if prefijo_ine and cod_por_nombre:
            if prefijo_ine != cod_por_nombre:
                motivo = (
                    f"Inconsistencia entre cod_ine_mun ('{ine_norm}') "
                    f"y provincia ('{reg.provincia}')"
                )
                resultado.error(fila, "provincia", TipoError.SEMANTICO, motivo)
                return None
            return prefijo_ine, reg.provincia.strip()  # type: ignore[union-attr]

        if prefijo_ine and not cod_por_nombre:
            nombre_oficial = PROVINCIAS_CV[prefijo_ine]
            resultado.reparacion(
                fila,
                "provincia",
                reg.provincia,
                nombre_oficial,
                "Provincia deducida a partir de los 2 primeros dígitos de cod_ine_mun",
            )
            return prefijo_ine, nombre_oficial

        if cod_por_nombre and not prefijo_ine:
            resultado.reparacion(
                fila,
                "cod_ine_mun",
                reg.cod_ine_mun,
                cod_por_nombre,
                "Código de provincia deducido a partir del nombre de provincia",
            )
            return cod_por_nombre, PROVINCIAS_CV[cod_por_nombre]

        if not ine_raw and (not reg.provincia or not reg.provincia.strip()):
            resultado.error(
                fila, "provincia", TipoError.NULO, "Faltan tanto cod_ine_mun como provincia"
            )
        else:
            motivo = (
                "Provincia/código INE no válidos para la CV: "
                f"'{reg.cod_ine_mun}' / '{reg.provincia}'"
            )
            resultado.error(fila, "provincia", TipoError.SEMANTICO, motivo)
        return None

    def _parsear_par_utm(
        self, reg: EntidadCVOrigen, resultado: ResultadoExtraccion
    ) -> tuple[float, float] | None:
        fila = reg.fila
        x_raw = reg.x_25830.strip() if reg.x_25830 else ""
        y_raw = reg.y_25830.strip() if reg.y_25830 else ""

        x_val = self._parsear_numero_coord(fila, "x_25830", x_raw, resultado)
        y_val = self._parsear_numero_coord(fila, "y_25830", y_raw, resultado)

        if x_val is None or y_val is None:
            desde_wkt = self._extraer_utm_de_wkt(reg.WKT)
            if desde_wkt is not None:
                resultado.reparacion(
                    fila,
                    "coordenadas",
                    f"x={reg.x_25830}, y={reg.y_25830}",
                    f"x={desde_wkt[0]}, y={desde_wkt[1]}",
                    "Coordenadas UTM recuperadas desde el campo WKT",
                )
                x_val, y_val = desde_wkt
            else:
                return None

        # Detectar inversión accidental entre X (~600k-850k) e Y (~4.1M-4.6M)
        if x_val > 3_000_000 and 500_000 <= y_val <= 950_000:
            resultado.reparacion(
                fila,
                "coordenadas",
                f"x={x_val}, y={y_val}",
                f"x={y_val}, y={x_val}",
                "Intercambio de coordenadas UTM X e Y invertidas",
            )
            x_val, y_val = y_val, x_val

        return x_val, y_val

    @staticmethod
    def _parsear_numero_coord(
        fila: int, campo: str, texto: str, resultado: ResultadoExtraccion
    ) -> float | None:
        if not texto:
            return None
        candidato = texto
        if "," in texto and "." not in texto:
            candidato = texto.replace(",", ".")
            try:
                valor = float(candidato)
            except ValueError:
                return None
            resultado.reparacion(
                fila, campo, texto, candidato, "Reemplazo de coma decimal por punto"
            )
            return valor
        try:
            return float(candidato)
        except ValueError:
            return None

    @staticmethod
    def _extraer_utm_de_wkt(wkt: str | None) -> tuple[float, float] | None:
        if not wkt:
            return None
        match = _WKT_POINT_RE.search(wkt)
        if not match:
            return None
        try:
            x = float(match.group(1).replace(",", "."))
            y = float(match.group(2).replace(",", "."))
            return x, y
        except ValueError:
            return None

    def _resolver_coordenadas(
        self,
        reg: EntidadCVOrigen,
        *,
        direccion: str | None,
        municipio: str,
        provincia: str,
        scraper_activo: GeoScraper | None,
        resultado: ResultadoExtraccion,
    ) -> tuple[float, float, str | None] | None:
        fila = reg.fila
        par_utm = self._parsear_par_utm(reg, resultado)

        if par_utm is not None:
            lon, lat = _TRANSFORMER_25830_A_WGS84.transform(par_utm[0], par_utm[1])
            if LAT_MIN_CV <= lat <= LAT_MAX_CV and LON_MIN_CV <= lon <= LON_MAX_CV:
                return round(lon, 6), round(lat, 6), None
            motivo_fallo = (
                TipoError.FUERA_DE_RANGO,
                f"Coordenadas fuera de la Comunitat Valenciana (lat={lat:.4f}, lon={lon:.4f})",
            )
        else:
            sin_datos = not (reg.x_25830 and reg.x_25830.strip()) and not (
                reg.y_25830 and reg.y_25830.strip()
            )
            motivo_fallo = (
                TipoError.NULO if sin_datos else TipoError.FORMATO,
                f"Coordenadas UTM inválidas o ausentes: x='{reg.x_25830}', y='{reg.y_25830}'",
            )

        if scraper_activo is not None:
            geo = scraper_activo.geocodificar(
                direccion=direccion,
                municipio=municipio,
                provincia=provincia,
            )
            if (
                geo.latitud is not None
                and geo.longitud is not None
                and LAT_MIN_CV <= geo.latitud <= LAT_MAX_CV
                and LON_MIN_CV <= geo.longitud <= LON_MAX_CV
            ):
                resultado.reparacion(
                    fila,
                    "coordenadas",
                    f"x={reg.x_25830}, y={reg.y_25830}",
                    f"lat={geo.latitud:.6f}, lon={geo.longitud:.6f}",
                    "Coordenadas obtenidas mediante geocodificación de la dirección",
                )
                return round(geo.longitud, 6), round(geo.latitud, 6), geo.codigo_postal

        resultado.error(fila, "coordenadas", motivo_fallo[0], motivo_fallo[1])
        return None

    def _resolver_codigo_postal(
        self,
        *,
        cp_candidato: str | None,
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float,
        longitud: float,
        codigo_provincia: str,
        scraper_activo: GeoScraper | None,
    ) -> str | None:
        cp = cp_candidato
        if cp is None and scraper_activo is not None:
            geo = scraper_activo.geocodificar(
                direccion=direccion,
                municipio=municipio,
                provincia=provincia,
                latitud=latitud,
                longitud=longitud,
            )
            cp = geo.codigo_postal

        if cp is None or not cp.strip():
            return None

        cp_limpio = cp.strip()
        if cp_limpio.isdigit() and len(cp_limpio) == 4:
            cp_limpio = cp_limpio.zfill(5)

        if not _CP_RE.fullmatch(cp_limpio):
            return None

        if cp_limpio[:2] != codigo_provincia:
            return None

        return cp_limpio

    def _resolver_contacto(
        self, reg: EntidadCVOrigen, resultado: ResultadoExtraccion
    ) -> str | None:
        telefono = self._limpiar_telefono(reg.fila, reg.telefono, resultado)
        email = self._limpiar_email(reg.fila, reg.email, resultado)

        partes: list[str] = []
        if telefono:
            partes.append(f"Tel: {telefono}")
        if email:
            partes.append(f"Email: {email}")
        return " | ".join(partes) if partes else None

    @staticmethod
    def _limpiar_telefono(
        fila: int, telefono_raw: str | None, resultado: ResultadoExtraccion
    ) -> str | None:
        if not telefono_raw:
            return None
        limpio = telefono_raw.strip()
        if not limpio or limpio == "0":
            return None

        solo_digitos = re.sub(r"[\s.\-()]", "", limpio)
        if solo_digitos.startswith("+34"):
            solo_digitos = solo_digitos[3:]

        if solo_digitos.isdigit() and len(solo_digitos) == 9 and solo_digitos[0] in "6789":
            if solo_digitos != limpio:
                resultado.reparacion(
                    fila,
                    "telefono",
                    telefono_raw,
                    solo_digitos,
                    "Normalización de formato en número de teléfono",
                )
            return solo_digitos

        # Si hay varios teléfonos separados (ej. '964360002; 964367054'), extraer los válidos
        encontrados = re.findall(r"[6789]\d{8}", solo_digitos)
        if encontrados:
            unidos = " / ".join(dict.fromkeys(encontrados))
            resultado.reparacion(
                fila,
                "telefono",
                telefono_raw,
                unidos,
                "Extracción de teléfonos válidos de cadena múltiple",
            )
            return unidos

        resultado.reparacion(
            fila,
            "telefono",
            telefono_raw,
            None,
            "Descartado teléfono con formato no válido",
        )
        return None

    @staticmethod
    def _limpiar_email(
        fila: int, email_raw: str | None, resultado: ResultadoExtraccion
    ) -> str | None:
        if not email_raw:
            return None
        limpio = email_raw.strip()
        if not limpio or limpio.lower() == "zero@gva.es":
            return None

        if _EMAIL_RE.fullmatch(limpio):
            return limpio.lower()

        sin_espacios = "".join(limpio.split())
        if _EMAIL_RE.fullmatch(sin_espacios):
            normalizado = sin_espacios.lower()
            resultado.reparacion(
                fila,
                "email",
                email_raw,
                normalizado,
                "Eliminación de espacios internos en dirección de correo",
            )
            return normalizado

        varios = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", limpio)
        if varios:
            unidos = " / ".join(dict.fromkeys(c.lower() for c in varios))
            resultado.reparacion(
                fila,
                "email",
                email_raw,
                unidos,
                "Extracción de correos válidos de cadena con texto adicional",
            )
            return unidos

        resultado.reparacion(
            fila,
            "email",
            email_raw,
            None,
            "Descartado email con formato no válido",
        )
        return None
