"""Servicio de carga al almacén PostgreSQL a partir de `ResultadoExtraccion`."""

from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.extractors.common import EntidadExtraida, ResultadoExtraccion
from app.models.almacen import Entidad, Localidad, Provincia
from app.schemas.carga import (
    EntidadVista,
    EstadoAlmacen,
    LocalidadVista,
    ProvinciaVista,
    ResumenFuenteCarga,
)


def limpiar_geocache(cache_path: Path | str | None = None) -> bool:
    """Elimina el archivo de caché de geocodificación si existe.

    Retorna `True` si existía y se eliminó, o `False` si no estaba presente.
    """
    ruta = Path(cache_path) if cache_path is not None else settings.GEOCACHE_PATH
    if not ruta.is_absolute():
        ruta = BACKEND_DIR / ruta
    if ruta.is_file():
        ruta.unlink()
        return True
    return False


def vaciar_almacen(db: Session) -> None:
    """Elimina todos los registros del almacén reiniciando los contadores IDENTITY."""
    dialecto = db.bind.dialect.name if db.bind is not None else ""
    if dialecto == "postgresql":
        db.execute(text("TRUNCATE TABLE entidad, localidad, provincia RESTART IDENTITY CASCADE"))
    else:
        db.execute(delete(Entidad))
        db.execute(delete(Localidad))
        db.execute(delete(Provincia))
    db.commit()


def obtener_estado_almacen(db: Session) -> EstadoAlmacen:
    """Consulta el estado real actual de las tablas `provincia`, `localidad` y `entidad`."""
    provincias_rows = db.scalars(select(Provincia).order_by(Provincia.codigo)).all()
    localidades_rows = db.scalars(
        select(Localidad).order_by(Localidad.codigo_provincia, Localidad.nombre)
    ).all()

    entidades_stmt = (
        select(Entidad, Localidad, Provincia)
        .join(Localidad, Entidad.codigo_localidad == Localidad.codigo)
        .join(Provincia, Localidad.codigo_provincia == Provincia.codigo)
        .order_by(Entidad.cod_entidad)
    )
    entidades_rows = db.execute(entidades_stmt).all()

    ambitos_stmt = select(Entidad.ambito, func.count(Entidad.cod_entidad)).group_by(Entidad.ambito)
    ambitos_rows = db.execute(ambitos_stmt).all()

    return EstadoAlmacen(
        total_provincias=len(provincias_rows),
        total_localidades=len(localidades_rows),
        total_entidades=len(entidades_rows),
        entidades_por_ambito={ambito.value: total for ambito, total in ambitos_rows},
        provincias=[ProvinciaVista(codigo=p.codigo, nombre=p.nombre) for p in provincias_rows],
        localidades=[
            LocalidadVista(
                codigo=loc.codigo,
                nombre=loc.nombre,
                codigo_provincia=loc.codigo_provincia,
            )
            for loc in localidades_rows
        ],
        entidades=[
            EntidadVista(
                cod_entidad=ent.cod_entidad,
                nombre=ent.nombre,
                ambito=ent.ambito.value,
                direccion=ent.direccion,
                codigo_postal=ent.codigo_postal,
                longitud=ent.longitud,
                latitud=ent.latitud,
                contacto=ent.contacto,
                url=ent.url,
                localidad=loc.nombre,
                codigo_provincia=prov.codigo,
                provincia=prov.nombre,
            )
            for ent, loc, prov in entidades_rows
        ],
    )


def _asegurar_provincia(
    db: Session,
    cache_provincias: dict[str, Provincia],
    item: EntidadExtraida,
) -> Provincia:
    codigo = item.codigo_provincia.strip()[:2]
    if codigo in cache_provincias:
        return cache_provincias[codigo]

    existente = db.get(Provincia, codigo)
    if existente is not None:
        cache_provincias[codigo] = existente
        return existente

    nueva = Provincia(codigo=codigo, nombre=item.nombre_provincia.strip()[:100])
    db.add(nueva)
    db.flush()
    cache_provincias[codigo] = nueva
    return nueva


def _asegurar_localidad(
    db: Session,
    cache_localidades: dict[tuple[str, str], Localidad],
    codigo_provincia: str,
    nombre_localidad: str,
) -> Localidad:
    nombre_limpio = nombre_localidad.strip()[:150]
    clave = (nombre_limpio, codigo_provincia)
    if clave in cache_localidades:
        return cache_localidades[clave]

    existente = db.scalar(
        select(Localidad).where(
            Localidad.nombre == nombre_limpio,
            Localidad.codigo_provincia == codigo_provincia,
        )
    )
    if existente is not None:
        cache_localidades[clave] = existente
        return existente

    nueva = Localidad(nombre=nombre_limpio, codigo_provincia=codigo_provincia)
    db.add(nueva)
    db.flush()
    cache_localidades[clave] = nueva
    return nueva


def cargar_resultado_en_bd(db: Session, resultado: ResultadoExtraccion) -> ResumenFuenteCarga:
    """Inserta en PostgreSQL las entidades de `resultado` evitando duplicados en almacén."""
    cache_provincias: dict[str, Provincia] = {
        p.codigo: p for p in db.scalars(select(Provincia)).all()
    }
    cache_localidades: dict[tuple[str, str], Localidad] = {
        (loc.nombre, loc.codigo_provincia): loc for loc in db.scalars(select(Localidad)).all()
    }
    entidades_existentes: set[tuple[str, int]] = {
        (nombre.strip().casefold(), cod_loc)
        for nombre, cod_loc in db.execute(
            select(Entidad.nombre, Entidad.codigo_localidad)
        ).all()
    }

    insertadas = 0
    omitidas_duplicado = 0

    for item in resultado.entidades:
        prov = _asegurar_provincia(db, cache_provincias, item)
        loc = _asegurar_localidad(db, cache_localidades, prov.codigo, item.nombre_localidad)

        nombre_limpio = item.nombre.strip()[:300]
        clave_entidad = (nombre_limpio.casefold(), loc.codigo)
        if clave_entidad in entidades_existentes:
            omitidas_duplicado += 1
            continue

        entidad = Entidad(
            nombre=nombre_limpio,
            ambito=item.ambito,
            direccion=item.direccion[:300] if item.direccion else None,
            codigo_postal=item.codigo_postal[:5] if item.codigo_postal else None,
            longitud=item.longitud,
            latitud=item.latitud,
            descripcion=item.descripcion,
            contacto=item.contacto[:300] if item.contacto else None,
            url=item.url[:500] if item.url else None,
            codigo_localidad=loc.codigo,
        )
        db.add(entidad)
        entidades_existentes.add(clave_entidad)
        insertadas += 1

    db.commit()

    errores_por_tipo = dict(Counter(err.tipo.value for err in resultado.errores))
    return ResumenFuenteCarga(
        fuente=resultado.fuente,
        extraidas=len(resultado.entidades),
        insertadas=insertadas,
        omitidas_duplicado_bd=omitidas_duplicado,
        errores_total=len(resultado.errores),
        errores_por_tipo=errores_por_tipo,
        reparaciones_total=len(resultado.reparaciones),
        errores=list(resultado.errores),
        reparaciones=list(resultado.reparaciones),
    )
