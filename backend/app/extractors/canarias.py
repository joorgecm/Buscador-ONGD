"""Extractor para la fuente de datos de Canarias (JSON).

Este módulo es responsable de:
1. Leer el archivo JSON original o la muestra representativa.
2. Limpiar, validar y reparar los campos según el mapeo semántico.
3. Clasificar cada entidad en uno de los 12 ámbitos del modelo común.
4. Detectar posibles anomalías o duplicados mediante `numero_registro` / `nif`.
5. Obtener el código postal y coordenadas (mediante `ScraperGeo` en `app.scraper`).
6. Devolver una instancia de `ResultadoExtraccion` con `Fuente.CAN`.

Notas de diseño (según especificación del profesor):
- `E.cod_entidad`: Identificador autogenerado por PostgreSQL (IDENTITY). No se mapea.
- `L.codigo`: Autogenerado por PostgreSQL (IDENTITY). Solo se extrae `nombre_localidad`.
- `codigo_postal`: No viene en el dataset; se obtiene mediante scraper (Selenium / APIs).
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR, settings
from app.extractors.common import (
    EntidadExtraida,
    Fuente,
    ResultadoExtraccion,
    TipoError,
)
from app.models.ambito import Ambito
from app.scraper.geocoder import GeoScraper, ScraperGeo

# Ruta por defecto a los datos de Canarias
DEFAULT_DATA_PATH = settings.CAN_JSON_PATH

PROVINCIAS_CAN: dict[str, str] = {
    "35": "Las Palmas",
    "38": "Santa Cruz de Tenerife",
}

LAT_MIN_CAN, LAT_MAX_CAN = 27.5, 29.6
LON_MIN_CAN, LON_MAX_CAN = -18.3, -13.3
LAT_MIN_ESP, LAT_MAX_ESP = 27.5, 43.9
LON_MIN_ESP, LON_MAX_ESP = -18.3, 4.5

_CP_RE = re.compile(r"^\d{5}$")
_PREFIJO_VIA_RE = re.compile(
    r"^(?:c/|(?:"
    r"calle|cl\.?|avda\.?|avenida|ctra\.?|carretera|carre\.?|paseo|plaza|pza\.?|"
    r"urb\.?|urbanizaci[oó]n|camino|cmno\.?|rambla|rbla\.?|pasaje|psaje\.?|"
    r"traves[ií]a|trva\.?|parque|pque\.?|barranco|branc\.?|cuesta|custa\.?|"
    r"muelle|muell\.?|subida|sbida\.?|senda|loma|lugar"
    r")(?=\s|$))",
    re.IGNORECASE,
)
_TIPOS_VIA_BUSQUEDA: dict[str, str] = {
    "avda": "Avenida",
    "branc": "Barranco",
    "carre": "Carretera",
    "cmno": "Camino",
    "ctra": "Carretera",
    "custa": "Cuesta",
    "disem": "",
    "muell": "Muelle",
    "pque": "Parque",
    "psaje": "Pasaje",
    "rbla": "Rambla",
    "sbida": "Subida",
    "trva": "Travesía",
    "urb": "Urbanización",
}


def _texto(fila: dict[str, Any], clave: str) -> str:
    val = fila.get(clave)
    return str(val).strip() if val is not None else ""


def _es_centinela(valor: str) -> bool:
    return valor.strip().upper() in ("", "_U")


def _normalizar_clave(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.upper().split())


def _mapear_ambito(
    denominacion: str,
    area_nombre: str,
    subarea_nombre: str,
) -> Ambito | None:
    """Clasifica una entidad en uno de los 12 ámbitos globales.

    Reglas de mapeo semántico:
    - SALUD_MENTAL:
        Si denominacion contiene 'salud mental' o 'enfermedad mental' (prioritario,
        incluso sobre Discapacidad o Varios).
    """
    denom_norm = _normalizar_clave(denominacion)
    area_norm = _normalizar_clave(area_nombre)
    sub_norm = _normalizar_clave(subarea_nombre)

    if "SALUD MENTAL" in denom_norm or "ENFERMEDAD MENTAL" in denom_norm:
        return Ambito.SALUD_MENTAL

    """
    - MAYORES:
        Si area_nombre == 'Tercera Edad'.
    """
    if area_norm == "TERCERA EDAD":
        return Ambito.MAYORES

    """
    - DISCAPACIDAD:
        Si area_nombre in ('Discapacidad', 'Centros Ocupacionales') y denominacion
        no indica salud mental.
    """
    if area_norm in ("DISCAPACIDAD", "CENTROS OCUPACIONALES"):
        return Ambito.DISCAPACIDAD

    """
    - INFANCIA_Y_JUVENTUD:
        Si area_nombre == 'Menores Y Juventud'.
    """
    if area_norm == "MENORES Y JUVENTUD":
        return Ambito.INFANCIA_Y_JUVENTUD

    """
    - MUJER:
        Si area_nombre == 'Mujer'.
    """
    if area_norm == "MUJER":
        return Ambito.MUJER

    """
    - MIGRACION:
        Si area_nombre == 'Varios' y subarea_nombre == 'Migración'.
    """
    if area_norm == "VARIOS" and "MIGRACI" in sub_norm:
        return Ambito.MIGRACION

    """
    - INCLUSION_SOCIAL:
        Si area_nombre == 'Exclusión Social', o
        (area_nombre == 'Varios' y subarea contiene 'Comedores Sociales',
        'Inserción Social' o 'Igualdad LGTBI'), o
        (area_nombre == 'Voluntariado' y subarea contiene 'Servicios Sociales' o 'Solidaridad'), o
        (area_nombre == 'Varios' y subarea_nombre in ('_U', 'Otros')).
    """
    if (
        area_norm == "EXCLUSION SOCIAL"
        or (
            area_norm == "VARIOS"
            and any(k in sub_norm for k in ["COMEDORES SOCIALES", "INSERCI", "LGTBI"])
        )
        or (
            area_norm == "VOLUNTARIADO"
            and any(k in sub_norm for k in ["SERVICIOS SOCIALES", "SOLIDARIDAD"])
        )
        or (area_norm == "VARIOS" and sub_norm in ("_U", "OTROS"))
    ):
        return Ambito.INCLUSION_SOCIAL

    """
    - EDUCACION_Y_FORMACION:
        Si area_nombre == 'Voluntariado' y subarea contiene 'Educación'.
    """
    if area_norm == "VOLUNTARIADO" and "EDUCACI" in sub_norm:
        return Ambito.EDUCACION_Y_FORMACION

    """
    - EMPLEO_E_INSERCION_LABORAL:
        Si area_nombre == 'Varios' y subarea contiene
        'Asociaciones De Trabajadores Empresarios Sindicatos Colegios Profesionales'.
    """
    if area_norm == "VARIOS" and "TRABAJADORES EMPRESARIOS" in sub_norm:
        return Ambito.EMPLEO_E_INSERCION_LABORAL

    """
    - SALUD_Y_ATENCION_SOCIOSANITARIA:
        Si area_nombre == 'Drogodependencia', o
        (area_nombre == 'Varios' y subarea contiene 'Asociaciones De Enfermos',
        'SociO-Sanitaria' o 'Terapias Y Salud'), o
        (area_nombre == 'Voluntariado' y subarea contiene 'Asuntos Sanitarios').
    """
    if (
        area_norm == "DROGODEPENDENCIA"
        or (
            area_norm == "VARIOS"
            and any(
                k in sub_norm
                for k in ["ASOCIACIONES DE ENFERMOS", "SOCIO-SANITARIA", "TERAPIAS Y SALUD"]
            )
        )
        or (area_norm == "VOLUNTARIADO" and "SANITARIOS" in sub_norm)
    ):
        return Ambito.SALUD_Y_ATENCION_SOCIOSANITARIA

    """
    - VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA:
        Si area_nombre == 'Voluntariado' (medio ambiente, protección civil, general o '_U'), o
        (subarea_nombre contiene 'Asociaciones De Vecinos').
    """
    if area_norm == "VOLUNTARIADO" or "ASOCIACIONES DE VECINOS" in sub_norm:
        return Ambito.VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA

    """
    - CULTURA_Y_DESARROLLO_COMUNITARIO:
        Si area_nombre == 'Varios' y subarea contiene 'Asociaciones Culturales Deportivas' o
        'Ciencia Tecnología Investigación... Patrimonio Histórico'.
    """
    if area_norm == "VARIOS" and (
        "CULTURALES DEPORTIVAS" in sub_norm
        or "CIENCIA TECNOLOG" in sub_norm
        or "PATRIMONIO" in sub_norm
    ):
        return Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO

    """
    Retorna:
        El valor correspondiente de `Ambito` o `None` si no encaja en ninguna regla.
    """
    return None


def _construir_direccion(
    tipo_via: str,
    nombre_via: str,
    numero: str,
    complemento: str,
) -> tuple[str | None, str | None]:
    """Construye y normaliza la dirección completa a partir de los 4 componentes de origen.

    Reglas de transformación:
    - Omitir valores centinela '_U'.
    - Si numero == '0' -> formatear como 'S/N' (Sin Número).
    - Si numero es válido (distinto de '_U' y '0') -> formatear como 'Nº <numero>'.
    - Concatenar en orden: tipo de vía, nombre de vía, número y complemento (si está informado).

    Retorna:
        Una tupla `(direccion_final, regla_aplicada)` o `(None, None)` si no hay datos.
    """
    partes: list[str] = []
    regla: str | None = None

    if not _es_centinela(tipo_via):
        partes.append(tipo_via.strip())

    if not _es_centinela(nombre_via):
        partes.append(nombre_via.strip())

    num_limpio = numero.strip() if numero else ""
    if num_limpio.upper().rstrip(".") in ("0", "S/N", "SN"):
        partes.append("S/N")
        if num_limpio != "S/N":
            regla = f"Conversión de número '{num_limpio}' a 'S/N'"
    elif not _es_centinela(num_limpio):
        partes.append(f"Nº {num_limpio}")

    if not _es_centinela(complemento):
        partes.append(complemento.strip())

    if not partes:
        return None, None

    return " ".join(partes), regla


def _extraer_numero_busqueda(numero: str) -> str:
    """Extrae el número principal de portal para consultas de geocodificación."""
    num = numero.strip()
    if _es_centinela(num) or num.upper().rstrip(".") in ("0", "S/N", "SN"):
        return ""
    match = re.match(r"^0*(\d+)", num)
    if match:
        limpio = match.group(1)
        return "" if limpio == "0" else limpio
    return ""


def _construir_direccion_busqueda(
    tipo_via: str,
    nombre_via: str,
    numero: str,
) -> str | None:
    """Construye una dirección limpia para `ScraperGeo` sin complementos ni prefijos repetidos."""
    if _es_centinela(nombre_via):
        return None

    via_limpia = nombre_via.strip(" -,")
    if not via_limpia:
        return None

    tipo_limpio = "" if _es_centinela(tipo_via) else tipo_via.strip()
    if tipo_limpio:
        if _PREFIJO_VIA_RE.match(via_limpia):
            tipo_limpio = ""
        else:
            tipo_limpio = _TIPOS_VIA_BUSQUEDA.get(tipo_limpio.lower(), tipo_limpio)

    base = " ".join(p for p in (tipo_limpio, via_limpia) if p)
    num_busqueda = _extraer_numero_busqueda(numero)
    if num_busqueda and not re.search(rf"\b0*{re.escape(num_busqueda)}\b$", base):
        base = f"{base} {num_busqueda}"

    return base or None


def _limpiar_contacto(
    telefono_1: str,
    telefono_2: str,
) -> tuple[str | None, bool]:
    """Limpia prefijos internacionales y combina teléfonos disponibles.

    Reglas de transformación:
    - Omitir teléfonos con valor '_U' o vacíos.
    - Eliminar prefijo '(34)' o '+34' de cada número y evitar duplicados.
    - Formatear con prefijo 'Tel: ' y unir múltiples con ' / '
      (ej. 'Tel: 922437523 / 655221013').

    Retorna:
        Una tupla `(contacto_limpio, hubo_limpieza)` donde `hubo_limpieza` indica
        si se eliminó algún prefijo '(34)' o '+34' para registrar una `Reparacion`.
    """
    telefonos_limpios: list[str] = []
    hubo_limpieza = False

    for tel in (telefono_1, telefono_2):
        if _es_centinela(tel):
            continue
        tel_limpio = tel.strip()
        if "(34)" in tel_limpio or tel_limpio.startswith("+34"):
            tel_limpio = tel_limpio.replace("(34)", "").removeprefix("+34").strip()
            hubo_limpieza = True
        if tel_limpio and tel_limpio not in telefonos_limpios:
            telefonos_limpios.append(tel_limpio)

    if not telefonos_limpios:
        return None, False

    return f"Tel: {' / '.join(telefonos_limpios)}", hubo_limpieza


def _normalizar_url(pagina_web: str) -> tuple[str | None, bool]:
    """Normaliza la URL de la página web de la entidad.

    Reglas de transformación:
    - Si pagina_web in ('_U', '', None) -> retornar None.
    - Limpiar espacios y corregir erratas ('hhtps://', 'www. ', 'www' sin punto).
    - Descartar textos libres o correos electrónicos que no sean dominios web válidos.
    - Si no comienza por 'http://' ni 'https://', anteponer 'https://'.

    Retorna:
        Una tupla `(url_normalizada, hubo_reparacion)`.
    """
    if _es_centinela(pagina_web):
        return None, False

    url = pagina_web.strip()
    hubo_reparacion = False

    # Corregir espacio tras 'www.' (ej. 'www. raizdelpueblo.org')
    if url.lower().startswith("www. "):
        url = "www." + url[5:].strip()
        hubo_reparacion = True

    # Descartar si contiene espacios, '@' de email o carece de punto de dominio
    if " " in url or "@" in url or "." not in url:
        return None, False

    # Corregir errata 'hhtps://' / 'hhtp://'
    if url.lower().startswith("hhtps://"):
        url = "https://" + url[8:]
        hubo_reparacion = True
    elif url.lower().startswith("hhtp://"):
        url = "http://" + url[7:]
        hubo_reparacion = True

    # Corregir 'www' pegado al dominio sin punto (ej. 'wwwadepsi.org' -> 'www.adepsi.org')
    sin_esquema = url.removeprefix("https://").removeprefix("http://")
    if (
        sin_esquema.lower().startswith("www")
        and len(sin_esquema) > 3
        and sin_esquema[3].isalpha()
    ):
        prefijo_esquema = url[: len(url) - len(sin_esquema)]
        url = f"{prefijo_esquema}www.{sin_esquema[3:]}"
        hubo_reparacion = True

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
        hubo_reparacion = True

    return url, hubo_reparacion


def _es_codigo_provincia_valido(cod: str) -> bool:
    return len(cod) == 2 and cod.isdigit() and 1 <= int(cod) <= 52


def _resolver_provincia_y_localidad(
    provincia_id: str,
    provincia_nombre: str,
    municipio_id: str,
    municipio_nombre: str,
) -> tuple[str, str, str | None, bool, bool]:
    """Resuelve códigos y nombres de provincia y el nombre de la localidad (municipio).

    Nota sobre claves:
    - `L.codigo` NO se extrae aquí porque la base de datos lo genera automáticamente (IDENTITY).
    - Solo necesitamos `nombre_localidad` limpio, `codigo_provincia` y `nombre_provincia`.

    Retorna:
        Tupla `(cod_provincia, nombre_provincia, nombre_localidad, hubo_deduccion, inconsistente)`.
    """
    hubo_deduccion = False
    inconsistente = False

    mun_id_limpio = "" if _es_centinela(municipio_id) else municipio_id.strip()
    if mun_id_limpio.isdigit() and 0 < len(mun_id_limpio) < 5:
        mun_id_limpio = mun_id_limpio.zfill(5)
    cod_mun_prov = (
        mun_id_limpio[:2]
        if len(mun_id_limpio) == 5 and _es_codigo_provincia_valido(mun_id_limpio[:2])
        else ""
    )

    prov_id_limpio = "" if _es_centinela(provincia_id) else provincia_id.strip()
    if prov_id_limpio.isdigit() and len(prov_id_limpio) == 1:
        prov_id_limpio = prov_id_limpio.zfill(2)
        hubo_deduccion = True

    prov_nombre_desconocido = (
        _es_centinela(provincia_nombre)
        or provincia_nombre.strip().casefold() == "desconocida"
    )

    # 1. Provincia (si el código de origen es desconocido/inválido como '99', deducir del INE)
    if _es_codigo_provincia_valido(prov_id_limpio):
        cod_provincia = prov_id_limpio
        if cod_mun_prov and cod_provincia != cod_mun_prov:
            inconsistente = True
        if not prov_nombre_desconocido:
            nombre_provincia = provincia_nombre.strip()
        elif cod_provincia in PROVINCIAS_CAN:
            nombre_provincia = PROVINCIAS_CAN[cod_provincia]
            hubo_deduccion = True
        else:
            nombre_provincia = ""
    elif cod_mun_prov:
        cod_provincia = cod_mun_prov
        if cod_provincia in PROVINCIAS_CAN:
            nombre_provincia = PROVINCIAS_CAN[cod_provincia]
            hubo_deduccion = True
        elif not prov_nombre_desconocido:
            nombre_provincia = provincia_nombre.strip()
            hubo_deduccion = True
        else:
            nombre_provincia = ""
    else:
        cod_provincia = prov_id_limpio
        nombre_provincia = "" if prov_nombre_desconocido else provincia_nombre.strip()
        if prov_id_limpio:
            inconsistente = True

    # 2. Localidad / Municipio
    if _es_centinela(municipio_nombre):
        if cod_provincia == "35":
            nombre_localidad: str | None = "Las Palmas de Gran Canaria"
            hubo_deduccion = True
        elif cod_provincia == "38":
            nombre_localidad = "Santa Cruz de Tenerife"
            hubo_deduccion = True
        else:
            nombre_localidad = None
    else:
        nombre_localidad = municipio_nombre.strip()
        if "(" in nombre_localidad and nombre_localidad.endswith(")"):
            base, articulo = nombre_localidad[:-1].rsplit("(", 1)
            nombre_localidad = f"{articulo.strip()} {base.strip()}"
            hubo_deduccion = True
        elif nombre_localidad == "Oliva La":
            nombre_localidad = "La Oliva"
            hubo_deduccion = True

    return cod_provincia, nombre_provincia, nombre_localidad, hubo_deduccion, inconsistente


def _coordenadas_en_rango(latitud: float, longitud: float, codigo_provincia: str) -> bool:
    """Comprueba que las coordenadas estén dentro de Canarias o de España según provincia."""
    if codigo_provincia in PROVINCIAS_CAN:
        return LAT_MIN_CAN <= latitud <= LAT_MAX_CAN and LON_MIN_CAN <= longitud <= LON_MAX_CAN
    return LAT_MIN_ESP <= latitud <= LAT_MAX_ESP and LON_MIN_ESP <= longitud <= LON_MAX_ESP


def _geocodificar_entidad(
    *,
    fila: int,
    direccion_busqueda: str | None,
    nombre_localidad: str,
    codigo_provincia: str,
    nombre_provincia: str,
    scraper_activo: GeoScraper,
    resultado: ResultadoExtraccion,
) -> tuple[str | None, float | None, float | None]:
    """Obtiene código postal y coordenadas mediante el scraper y valida sus rangos."""
    geo = scraper_activo.geocodificar(
        direccion=direccion_busqueda,
        municipio=nombre_localidad,
        provincia=nombre_provincia,
    )

    codigo_postal: str | None = None
    longitud: float | None = None
    latitud: float | None = None

    if geo.latitud is not None and geo.longitud is not None:
        if _coordenadas_en_rango(geo.latitud, geo.longitud, codigo_provincia):
            latitud = round(geo.latitud, 6)
            longitud = round(geo.longitud, 6)
        else:
            resultado.error(
                fila=fila,
                campo="coordenadas",
                tipo=TipoError.FUERA_DE_RANGO,
                motivo=(
                    f"Coordenadas fuera de rango para la provincia '{codigo_provincia}' "
                    f"(lat={geo.latitud:.4f}, lon={geo.longitud:.4f})"
                ),
            )
    else:
        resultado.error(
            fila=fila,
            campo="coordenadas",
            tipo=TipoError.NULO,
            motivo="No se pudieron obtener coordenadas para la dirección",
        )

    if geo.codigo_postal:
        cp_limpio = geo.codigo_postal.strip()
        if cp_limpio.isdigit() and len(cp_limpio) == 4:
            cp_limpio = cp_limpio.zfill(5)
        if _CP_RE.fullmatch(cp_limpio) and cp_limpio[:2] == codigo_provincia:
            codigo_postal = cp_limpio
            resultado.reparacion(
                fila=fila,
                campo="codigo_postal",
                valor_antes=None,
                valor_despues=cp_limpio,
                regla="Código postal obtenido mediante geocodificación de la dirección",
            )

    return codigo_postal, longitud, latitud


def _procesar_registros(
    datos: list[Any],
    scraper_activo: GeoScraper | None,
    resultado: ResultadoExtraccion,
) -> None:
    """Itera sobre las filas del JSON de Canarias y rellena `resultado`."""
    entidades_vistas: set[str] = set()

    for num_fila, fila in enumerate(datos, start=1):
        if not isinstance(fila, dict):
            resultado.error(
                fila=num_fila,
                campo="registro",
                tipo=TipoError.FORMATO,
                motivo="Cada elemento del JSON debe ser un objeto",
            )
            continue

        # a) Identificador y control de duplicados
        id_raw = _texto(fila, "numero_registro") or _texto(fila, "nif")
        id_registro = "" if _es_centinela(id_raw) else id_raw
        if id_registro:
            if id_registro in entidades_vistas:
                resultado.error(
                    fila=num_fila,
                    campo="numero_registro",
                    tipo=TipoError.DUPLICADO,
                    motivo=f"Entidad duplicada con identificador '{id_registro}'",
                )
                continue
            entidades_vistas.add(id_registro)

        # b) Denominación obligatoria
        denominacion = _texto(fila, "denominacion")
        if _es_centinela(denominacion):
            resultado.error(
                fila=num_fila,
                campo="nombre",
                tipo=TipoError.NULO,
                motivo="El campo denominación es nulo o no informado (_U)",
            )
            continue

        # c) Ámbito
        area_nombre = _texto(fila, "area_nombre")
        subarea_nombre = _texto(fila, "subarea_nombre")
        ambito = _mapear_ambito(denominacion, area_nombre, subarea_nombre)
        if ambito is None:
            resultado.error(
                fila=num_fila,
                campo="ambito",
                tipo=TipoError.SEMANTICO,
                motivo=(
                    f"No se pudo clasificar en ningún ámbito: "
                    f"area='{area_nombre}', subarea='{subarea_nombre}'"
                ),
            )
            continue

        # d) Provincia y Localidad (validar antes de registrar reparaciones de la fila)
        prov_id = _texto(fila, "direccion_provincia_id")
        prov_nombre = _texto(fila, "direccion_provincia_nombre")
        mun_id = _texto(fila, "direccion_municipio_id")
        mun_nombre = _texto(fila, "direccion_municipio_nombre")
        cod_prov, nom_prov, nom_loc, hubo_deduccion_geo, inconsistente = (
            _resolver_provincia_y_localidad(prov_id, prov_nombre, mun_id, mun_nombre)
        )
        if inconsistente:
            resultado.error(
                fila=num_fila,
                campo="provincia",
                tipo=TipoError.SEMANTICO,
                motivo=(
                    f"Provincia/municipio inconsistentes o no válidos: "
                    f"prov='{prov_id}', mun='{mun_id}'"
                ),
            )
            continue

        if not cod_prov or not nom_prov:
            resultado.error(
                fila=num_fila,
                campo="provincia",
                tipo=TipoError.NULO,
                motivo=(
                    f"No se pudo determinar la provincia: "
                    f"prov='{prov_id}:{prov_nombre}', mun='{mun_id}'"
                ),
            )
            continue

        if not nom_loc:
            resultado.error(
                fila=num_fila,
                campo="nombre_localidad",
                tipo=TipoError.NULO,
                motivo=f"Municipio no especificado (_U) para el código '{mun_id}'",
            )
            continue

        if hubo_deduccion_geo:
            resultado.reparacion(
                fila=num_fila,
                campo="provincia/localidad",
                valor_antes=f"prov={prov_id}:{prov_nombre}, mun={mun_id}:{mun_nombre}",
                valor_despues=f"prov={cod_prov}:{nom_prov}, loc={nom_loc}",
                regla=(
                    "Deducción de provincia/localidad por código postal/INE "
                    "o inversión de artículo"
                ),
            )

        # e) Dirección
        tipo_via = _texto(fila, "direccion_tipo_via")
        nombre_via = _texto(fila, "direccion_nombre_via")
        numero = _texto(fila, "direccion_numero")
        complemento = _texto(fila, "direccion_complemento")
        direccion, regla_dir = _construir_direccion(tipo_via, nombre_via, numero, complemento)
        if regla_dir:
            resultado.reparacion(
                fila=num_fila,
                campo="direccion",
                valor_antes=numero,
                valor_despues=direccion,
                regla=regla_dir,
            )

        # f) Contacto (teléfonos)
        tel_1 = _texto(fila, "telefono_1")
        tel_2 = _texto(fila, "telefono_2")
        contacto, hubo_limpieza_tel = _limpiar_contacto(tel_1, tel_2)
        if hubo_limpieza_tel:
            valor_antes_tel = f"{tel_1} / {tel_2}" if not _es_centinela(tel_2) else tel_1
            resultado.reparacion(
                fila=num_fila,
                campo="contacto",
                valor_antes=valor_antes_tel,
                valor_despues=contacto,
                regla="Limpieza de prefijo telefónico internacional (34) y unión con ' / '",
            )

        # g) Página web (URL)
        pagina_web_orig = _texto(fila, "pagina_web")
        url, hubo_reparacion_url = _normalizar_url(pagina_web_orig)
        if hubo_reparacion_url:
            resultado.reparacion(
                fila=num_fila,
                campo="url",
                valor_antes=pagina_web_orig,
                valor_despues=url,
                regla="Normalización de URL (esquema 'https://' y corrección de formato)",
            )
        elif not _es_centinela(pagina_web_orig) and url is None:
            resultado.reparacion(
                fila=num_fila,
                campo="url",
                valor_antes=pagina_web_orig,
                valor_despues=None,
                regla="Anulación de URL con formato inválido (texto libre o correo electrónico)",
            )

        # h) Descripción
        descripcion = None if _es_centinela(subarea_nombre) else subarea_nombre

        # i) Código postal y Coordenadas (scraper)
        codigo_postal: str | None = None
        longitud: float | None = None
        latitud: float | None = None

        if scraper_activo is not None:
            direccion_busqueda = _construir_direccion_busqueda(tipo_via, nombre_via, numero)
            codigo_postal, longitud, latitud = _geocodificar_entidad(
                fila=num_fila,
                direccion_busqueda=direccion_busqueda,
                nombre_localidad=nom_loc,
                codigo_provincia=cod_prov,
                nombre_provincia=nom_prov,
                scraper_activo=scraper_activo,
                resultado=resultado,
            )

        # j) Instanciar EntidadExtraida respetando los límites del esquema de BD
        entidad = EntidadExtraida(
            nombre=denominacion[:300],
            ambito=ambito,
            direccion=direccion[:300] if direccion else None,
            codigo_postal=codigo_postal,
            longitud=longitud,
            latitud=latitud,
            descripcion=descripcion,
            contacto=contacto[:300] if contacto else None,
            url=url[:500] if url else None,
            nombre_localidad=nom_loc[:150],
            codigo_provincia=cod_prov[:2],
            nombre_provincia=nom_prov[:100],
        )
        resultado.entidades.append(entidad)


class ExtractorCAN:
    """Extractor de Canarias: lee el archivo JSON de origen directamente."""

    def __init__(
        self,
        ruta_archivo: Path | str | None = None,
        *,
        scraper: GeoScraper | None = None,
        usar_scraper: bool = True,
    ) -> None:
        ruta = Path(ruta_archivo) if ruta_archivo is not None else DEFAULT_DATA_PATH
        if not ruta.is_absolute() and not ruta.exists():
            ruta = BACKEND_DIR / ruta
        self.ruta_archivo: Path = ruta
        self.scraper = scraper
        self.usar_scraper = usar_scraper

    def _leer_json(self, resultado: ResultadoExtraccion) -> list[Any] | None:
        """Lee el JSON de origen; si no es válido, lo informa y devuelve `None`."""
        if not self.ruta_archivo.exists():
            resultado.error(
                fila=None,
                campo="archivo",
                tipo=TipoError.FORMATO,
                motivo=f"No se encontró el archivo de datos en: {self.ruta_archivo}",
            )
            return None

        try:
            with open(self.ruta_archivo, encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            resultado.error(
                fila=None,
                campo="archivo",
                tipo=TipoError.FORMATO,
                motivo=f"Error al leer el JSON de Canarias: {exc}",
            )
            return None

        if not isinstance(datos, list):
            resultado.error(
                fila=None,
                campo="archivo",
                tipo=TipoError.FORMATO,
                motivo="El archivo JSON de Canarias debe contener una lista de entidades",
            )
            return None
        return datos

    def extraer(self) -> ResultadoExtraccion:
        resultado = ResultadoExtraccion(fuente=Fuente.CAN)
        datos = self._leer_json(resultado)
        if datos is None:
            return resultado

        scraper_propio: ScraperGeo | None = None
        scraper_activo: GeoScraper | None = self.scraper
        if scraper_activo is None and self.usar_scraper:
            scraper_propio = ScraperGeo()
            scraper_activo = scraper_propio

        try:
            _procesar_registros(datos, scraper_activo, resultado)
        finally:
            if scraper_propio is not None:
                scraper_propio.cerrar()

        return resultado


def extraer_canarias(
    ruta_archivo: Path | str | None = None,
    usar_scraper: bool = True,
    scraper: GeoScraper | None = None,
) -> ResultadoExtraccion:
    """Atajo funcional de `ExtractorCAN(ruta_archivo, ...).extraer()`."""
    return ExtractorCAN(ruta_archivo, scraper=scraper, usar_scraper=usar_scraper).extraer()
