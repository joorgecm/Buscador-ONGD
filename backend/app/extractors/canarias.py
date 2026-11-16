"""Extractor para la fuente de datos de Canarias (JSON).

Este módulo es responsable de:
1. Leer el archivo JSON original o la muestra representativa.
2. Limpiar, validar y reparar los campos según el mapeo semántico.
3. Clasificar cada entidad en uno de los 12 ámbitos del modelo común.
4. Detectar posibles anomalías o duplicados mediante `numero_registro` / `nif`.
5. Obtener el código postal (mediante el scraper en app.scraper).
6. Devolver una instancia de `ResultadoExtraccion` con `Fuente.CAN`.

Notas de diseño (según especificación del profesor):
- `E.cod_entidad`: Es un identificador autogenerado por PostgreSQL (IDENTITY). No se mapea.
- `L.codigo`: Es autogenerado por PostgreSQL (IDENTITY). No se mapea; solo se extrae el nombre de la localidad.
- `codigo_postal`: No viene en el dataset; se debe obtener mediante un scraper (Selenium / APIs de geocodificación).
"""

import json
from pathlib import Path
from typing import Any

from app.extractors.common import (
    EntidadExtraida,
    Fuente,
    ResultadoExtraccion,
    TipoError,
)
from app.models.ambito import Ambito

# Ruta por defecto a los datos de Canarias
DEFAULT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "canarias_sample.json"

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
    denom_lower = denominacion.lower()
    sub_lower = subarea_nombre.lower()

    if "salud mental" in denom_lower or "enfermedad mental" in denom_lower:
        return Ambito.SALUD_MENTAL

    """    
    - MAYORES:
        Si area_nombre == 'Tercera Edad'.

    """
    if area_nombre == "Tercera Edad":
        return Ambito.MAYORES

    """
    - DISCAPACIDAD:
        Si area_nombre in ('Discapacidad', 'Centros Ocupacionales') y denominacion
        no indica salud mental.
    """
    if area_nombre in ("Discapacidad", "Centros Ocupacionales"):
        return Ambito.DISCAPACIDAD

    """
    - INFANCIA_Y_JUVENTUD:
        Si area_nombre == 'Menores Y Juventud'.
    """

    if area_nombre == "Menores Y Juventud":
        return Ambito.INFANCIA_Y_JUVENTUD

    """
    - MUJER:
        Si area_nombre == 'Mujer'.
    """

    if area_nombre == "Mujer":
        return Ambito.MUJER

    """
    - MIGRACION:
        Si area_nombre == 'Varios' y subarea_nombre == 'Migración'.
    """
    if area_nombre == "Varios" and "migraci" in sub_lower:
        return Ambito.MIGRACION

    """
    - INCLUSION_SOCIAL:
        Si area_nombre == 'Exclusión Social', o
        (area_nombre == 'Varios' y subarea contiene 'Comedores Sociales', 'Inserción Social' o 'Igualdad LGTBI'), o
        (area_nombre == 'Voluntariado' y subarea contiene 'Servicios Sociales' o 'Solidaridad'), o
        (area_nombre == 'Varios' y subarea_nombre in ('_U', 'Otros')).
    """
    if (
        area_nombre == "Exclusión Social"
        or (area_nombre == "Varios" and any(k in sub_lower for k in ["comedores sociales", "inserci", "lgtbi"]))
        or (area_nombre == "Voluntariado" and any(k in sub_lower for k in ["servicios sociales", "solidaridad"]))
        or (area_nombre == "Varios" and subarea_nombre in ("_U", "Otros"))
    ):
        return Ambito.INCLUSION_SOCIAL

    """
    - EDUCACION_Y_FORMACION:
        Si area_nombre == 'Voluntariado' y subarea contiene 'Educación'.
    """
    if area_nombre == "Voluntariado" and "educaci" in sub_lower:
        return Ambito.EDUCACION_Y_FORMACION

    """
    - EMPLEO_E_INSERCION_LABORAL:
        Si area_nombre == 'Varios' y subarea contiene 'Asociaciones De Trabajadores Empresarios Sindicatos Colegios Profesionales'.
    """
    if area_nombre == "Varios" and "trabajadores empresarios" in sub_lower:
        return Ambito.EMPLEO_E_INSERCION_LABORAL

    """
    - SALUD_Y_ATENCION_SOCIOSANITARIA:
        Si area_nombre == 'Drogodependencia', o
        (area_nombre == 'Varios' y subarea contiene 'Asociaciones De Enfermos', 'SociO-Sanitaria' o 'Terapias Y Salud'), o
        (area_nombre == 'Voluntariado' y subarea contiene 'Asuntos Sanitarios').
    """
    if (
        area_nombre == "Drogodependencia"
        or (
            area_nombre == "Varios"
            and any(k in sub_lower for k in ["asociaciones de enfermos", "socio-sanitaria", "terapias y salud"])
        )
        or (area_nombre == "Voluntariado" and "sanitarios" in sub_lower)
    ):
        return Ambito.SALUD_Y_ATENCION_SOCIOSANITARIA

    """
    - VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA:
        Si area_nombre == 'Voluntariado' (medio ambiente, protección civil, general o '_U'), o
        (subarea_nombre contiene 'Asociaciones De Vecinos').
    """
    if area_nombre == "Voluntariado" or "asociaciones de vecinos" in sub_lower:
        return Ambito.VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA

    """
    - CULTURA_Y_DESARROLLO_COMUNITARIO:
        Si area_nombre == 'Varios' y subarea contiene 'Asociaciones Culturales Deportivas' o
        'Ciencia Tecnología Investigación... Patrimonio Histórico'.
    """
    if area_nombre == "Varios" and (
        "culturales deportivas" in sub_lower
        or "ciencia tecnolog" in sub_lower
        or "patrimonio" in sub_lower
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
    - Si numero es un número válido (distinto de '_U' y '0') -> formatear como 'Nº <numero>'.
    - Concatenar en orden: tipo de vía, nombre de vía, número y complemento (si está informado).

    Retorna:
        Una tupla `(direccion_final, regla_aplicada)` o `(None, None)` si no hay datos.
    """

    partes: list[str] = []
    regla: str | None = None

    if tipo_via and tipo_via != "_U":
        partes.append(tipo_via.strip())

    if nombre_via and nombre_via != "_U":
        partes.append(nombre_via.strip())

    num_limpio = numero.strip() if numero else ""
    if num_limpio.upper().rstrip(".") in ("0", "S/N", "SN"):
        partes.append("S/N")
        if num_limpio != "S/N":
            regla = f"Conversión de número '{num_limpio}' a 'S/N'"
    elif num_limpio and num_limpio != "_U":
        partes.append(f"Nº {num_limpio}")

    if complemento and complemento != "_U":
        partes.append(complemento.strip())

    if not partes:
        return None, None

    return " ".join(partes), regla


def _limpiar_contacto(
    telefono_1: str,
    telefono_2: str,
) -> tuple[str | None, bool]:
    """Limpia prefijos internacionales y combina teléfonos disponibles.

    Reglas de transformación:
    - Omitir teléfonos con valor '_U' o vacíos.
    - Eliminar prefijo '(34)' de cada número.
    - Si hay dos teléfonos válidos, unirlos con ' / ' (ej. '922437523 / 655221013').

    Retorna:
        Una tupla `(contacto_limpio, hubo_limpieza)` donde `hubo_limpieza` indica
        si se eliminó algún prefijo '(34)' para registrar una `Reparacion`.
    """

    telefonos_limpios: list[str] = []
    hubo_limpieza = False

    for tel in (telefono_1, telefono_2):
        if not tel or tel == "_U":
            continue
        tel_limpio = tel.strip()
        if "(34)" in tel_limpio or tel_limpio.startswith("+34"):
            tel_limpio = tel_limpio.replace("(34)", "").removeprefix("+34").strip()
            hubo_limpieza = True
        if tel_limpio:
            telefonos_limpios.append(tel_limpio)

    if not telefonos_limpios:
        return None, False

    return " / ".join(telefonos_limpios), hubo_limpieza


def _normalizar_url(pagina_web: str) -> tuple[str | None, bool]:
    """Normaliza la URL de la página web de la entidad.

    Reglas de transformación:
    - Si pagina_web in ('_U', '', None) -> retornar None.
    - Limpiar espacios en blanco y corregir erratas conocidas ('hhtps://', 'www. ', 'www' sin punto).
    - Descartar textos libres o correos electrónicos que no sean dominios web válidos.
    - Si no comienza por 'http://' ni 'https://', anteponer 'https://'.

    Retorna:
        Una tupla `(url_normalizada, hubo_reparacion)`.
    """
    if not pagina_web or pagina_web == "_U":
        return None, False

    url = pagina_web.strip()
    if not url or url == "_U":
        return None, False

    hubo_reparacion = False

    # Corregir espacio tras 'www.' (ej. 'www. raizdelpueblo.org')
    if url.lower().startswith("www. "):
        url = "www." + url[5:].strip()
        hubo_reparacion = True

    # Descartar si no parece una URL válida (contiene espacios, '@' de email o carece de punto de dominio)
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


def _resolver_provincia_y_localidad(
    provincia_id: str,
    provincia_nombre: str,
    municipio_id: str,
    municipio_nombre: str,
) -> tuple[str, str, str | None, bool]:
    """Resuelve códigos y nombres de provincia y el nombre de la localidad (municipio).

    Nota sobre claves:
    - `L.codigo` NO se extrae aquí porque la base de datos lo genera de forma automática (IDENTITY).
    - Solo necesitamos el `nombre_localidad` limpio, el `codigo_provincia` y el `nombre_provincia`.

    Reglas de transformación:
    - Provincia:
        - Si provincia_id == '_U', deducir el código a partir de los dos primeros dígitos de `municipio_id` (ej. '35003' -> '35').
        - Si provincia_nombre == '_U', deducir el nombre según el código:
            '35' -> 'Las Palmas', '38' -> 'Santa Cruz de Tenerife'.
    - Localidad / Municipio:
        - Si el nombre contiene artículo al final entre paréntesis (ej. 'Palmas de Gran Canaria (Las)'),
          invertirlo para obtener 'Las Palmas de Gran Canaria'.
        - Si viene como 'Oliva La', normalizar a 'La Oliva'.
        - Si viene con '_U', deducir la capital provincial si el código municipal corresponde a '35' o '38'.

    Retorna:
        Tupla `(cod_provincia, nombre_provincia, nombre_localidad, hubo_deduccion)`.
    """
    hubo_deduccion = False

    # 1. Provincia
    if provincia_id and provincia_id != "_U":
        cod_provincia = provincia_id.strip()
        if provincia_nombre and provincia_nombre != "_U":
            nombre_provincia = provincia_nombre.strip()
        else:
            nombre_provincia = "Las Palmas" if cod_provincia == "35" else "Santa Cruz de Tenerife"
            hubo_deduccion = True
    else:
        cod_provincia = municipio_id[:2].strip() if municipio_id and municipio_id != "_U" else ""
        nombre_provincia = "Las Palmas" if cod_provincia == "35" else "Santa Cruz de Tenerife"
        hubo_deduccion = True

    # 2. Localidad / Municipio
    if not municipio_nombre or municipio_nombre == "_U":
        if cod_provincia == "35":
            nombre_localidad = "Las Palmas de Gran Canaria"
            hubo_deduccion = True
        elif cod_provincia == "38":
            nombre_localidad = "Santa Cruz de Tenerife"
            hubo_deduccion = True
        else:
            nombre_localidad = None
    else:
        nombre_localidad = municipio_nombre.strip()
        if "(" in nombre_localidad and nombre_localidad.endswith(")"):
            base, articulo = nombre_localidad[:-1].split("(")
            nombre_localidad = f"{articulo.strip()} {base.strip()}"
            hubo_deduccion = True
        elif nombre_localidad == "Oliva La":
            nombre_localidad = "La Oliva"
            hubo_deduccion = True

    return cod_provincia, nombre_provincia, nombre_localidad, hubo_deduccion 

def extraer_canarias(
    ruta_archivo: Path | str | None = None,
    usar_scraper: bool = False,
) -> ResultadoExtraccion:
    """Extrae, valida y limpia las entidades del dataset JSON de Canarias.

    Pasos a realizar:
    1. Cargar el fichero JSON desde `ruta_archivo` (por defecto `DEFAULT_DATA_PATH`).
    2. Instanciar `ResultadoExtraccion(fuente=Fuente.CAN)`.
    3. Control de duplicados:
       - Usar `numero_registro` (o `nif`) para detectar si una entidad ya fue procesada
         (común cuando una entidad tiene asignadas múltiples subáreas).
       - Si ya existe en el conjunto procesado, registrar un error `TipoError.DUPLICADO`
         y no volver a agregarla a `resultado.entidades`.
       - `E.cod_entidad`: NO se asigna aquí, lo autogenera PostgreSQL al insertar.
    4. Para cada fila del JSON:
       a) Validar campo obligatorio `denominacion`: si está vacío o es nulo, registrar `TipoError.NULO`.
       b) Determinar el ámbito con `_mapear_ambito`:
          - Si no encaja en ningún ámbito, registrar `TipoError.SEMANTICO`.
       c) Procesar dirección con `_construir_direccion` y registrar `Reparacion` si cambió el valor.
       d) Procesar teléfonos con `_limpiar_contacto` y registrar `Reparacion` si se limpió prefijo.
       e) Procesar URL con `_normalizar_url` y registrar `Reparacion` si se añadió protocolo.
       f) Resolver provincia y nombre de localidad con `_resolver_provincia_y_localidad`.
          - `L.codigo`: NO se asigna aquí, lo autogenera PostgreSQL.
       g) `descripcion`: asignar `subarea_nombre` limpio si es distinto de '_U', o `None`.
       h) `codigo_postal`:
          - El dataset original no lo incluye.
          - Si `usar_scraper=True`, llamar al scraper (en `app.scraper`) pasando dirección,
            localidad y provincia para intentar obtenerlo (y validar formato 5 dígitos).
          - Si no se usa scraper o falla, dejar en `None`.
       i) `longitud`, `latitud`:
          - Opcionalmente obtenidas si el scraper geocodifica la dirección; de lo contrario `None`.
       j) Instanciar `EntidadExtraida` y agregarla a `resultado.entidades`.
    5. Retornar el `ResultadoExtraccion` completo.

    Args:
        ruta_archivo: Ruta al archivo JSON (ej. `canarias_sample.json` o `canarias.json`).
        usar_scraper: Booleano para activar el scraping de código postal y coordenadas.

    Returns:
        ResultadoExtraccion con las entidades extraídas, errores detectados y reparaciones aplicadas.
    """
    ruta = Path(ruta_archivo) if ruta_archivo else DEFAULT_DATA_PATH
    resultado = ResultadoExtraccion(fuente=Fuente.CAN)

    # 1. Leer el archivo JSON con codificación UTF-8
    if not ruta.exists():
        resultado.error(
            fila=None,
            campo="archivo",
            tipo=TipoError.FORMATO,
            motivo=f"No se encontró el archivo de datos en: {ruta}",
        )
        return resultado

    with open(ruta, "r", encoding="utf-8") as f:
        datos: list[dict[str, Any]] = json.load(f)

    # 2. Control de identificadores únicos para detectar duplicados
    # Se utiliza numero_registro (o nif como alternativa) para identificar entidades ya procesadas
    entidades_vistas: set[str] = set()

    # 3. Iterar sobre los registros y aplicar el pipeline de validación y limpieza
    for num_fila, fila in enumerate(datos, start=1):
        # a) Identificador y control de duplicados
        id_registro = (fila.get("numero_registro") or fila.get("nif") or "").strip()
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
        denominacion = (fila.get("denominacion") or "").strip()
        if not denominacion or denominacion == "_U":
            resultado.error(
                fila=num_fila,
                campo="nombre",
                tipo=TipoError.NULO,
                motivo="El campo denominación es nulo o no informado (_U)",
            )
            continue

        # c) Ámbito
        area_nombre = fila.get("area_nombre") or ""
        subarea_nombre = fila.get("subarea_nombre") or ""
        ambito = _mapear_ambito(denominacion, area_nombre, subarea_nombre)
        if ambito is None:
            resultado.error(
                fila=num_fila,
                campo="ambito",
                tipo=TipoError.SEMANTICO,
                motivo=f"No se pudo clasificar en ningún ámbito: area='{area_nombre}', subarea='{subarea_nombre}'",
            )
            continue

        # d) Provincia y Localidad (validar antes de registrar reparaciones de la fila)
        prov_id = fila.get("direccion_provincia_id") or ""
        prov_nombre = fila.get("direccion_provincia_nombre") or ""
        mun_id = fila.get("direccion_municipio_id") or ""
        mun_nombre = fila.get("direccion_municipio_nombre") or ""
        cod_prov, nom_prov, nom_loc, hubo_deduccion_geo = _resolver_provincia_y_localidad(
            prov_id, prov_nombre, mun_id, mun_nombre
        )
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
                regla="Deducción de provincia/localidad a partir de código postal/INE o inversión de artículo",
            )

        # e) Dirección
        tipo_via = fila.get("direccion_tipo_via") or ""
        nombre_via = fila.get("direccion_nombre_via") or ""
        numero = fila.get("direccion_numero") or ""
        complemento = fila.get("direccion_complemento") or ""
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
        tel_1 = fila.get("telefono_1") or ""
        tel_2 = fila.get("telefono_2") or ""
        contacto, hubo_limpieza_tel = _limpiar_contacto(tel_1, tel_2)
        if hubo_limpieza_tel:
            resultado.reparacion(
                fila=num_fila,
                campo="contacto",
                valor_antes=f"{tel_1} / {tel_2}" if tel_2 != "_U" else tel_1,
                valor_despues=contacto,
                regla="Limpieza de prefijo telefónico internacional (34) y unión con ' / '",
            )

        # g) Página web (URL)
        pagina_web_orig = (fila.get("pagina_web") or "").strip()
        url, hubo_reparacion_url = _normalizar_url(pagina_web_orig)
        if hubo_reparacion_url:
            resultado.reparacion(
                fila=num_fila,
                campo="url",
                valor_antes=pagina_web_orig,
                valor_despues=url,
                regla="Normalización de URL (esquema 'https://' y corrección de formato)",
            )
        elif pagina_web_orig and pagina_web_orig != "_U" and url is None:
            resultado.reparacion(
                fila=num_fila,
                campo="url",
                valor_antes=pagina_web_orig,
                valor_despues=None,
                regla="Anulación de URL con formato inválido (texto libre o correo electrónico)",
            )

        # h) Descripción
        descripcion = subarea_nombre.strip() if subarea_nombre and subarea_nombre != "_U" else None

        # i) Código postal y Coordenadas (scraper)
        codigo_postal = None
        longitud = None
        latitud = None

        if usar_scraper:
            # TODO: Invocar módulo app.scraper cuando esté disponible
            pass

        # j) Instanciar EntidadExtraida y añadir al resultado
        entidad = EntidadExtraida(
            nombre=denominacion,
            ambito=ambito,
            direccion=direccion,
            codigo_postal=codigo_postal,
            longitud=longitud,
            latitud=latitud,
            descripcion=descripcion,
            contacto=contacto,
            url=url,
            nombre_localidad=nom_loc,
            codigo_provincia=cod_prov,
            nombre_provincia=nom_prov,
        )
        resultado.entidades.append(entidad)

    return resultado