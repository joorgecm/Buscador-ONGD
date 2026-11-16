"""Tests para el servicio de carga en BD y la CLI de demo."""

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.cli.demo_carga import ejecutar_demo, ejecutar_menu, main
from app.db.session import Base
from app.extractors.common import EntidadExtraida, Fuente, ResultadoExtraccion, TipoError
from app.models import Ambito
from app.services.carga import (
    cargar_resultado_en_bd,
    limpiar_geocache,
    obtener_estado_almacen,
    vaciar_almacen,
)


def _crear_session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_cargar_resultado_reutiliza_geo_y_detecta_duplicados_en_bd() -> None:
    session_factory = _crear_session_factory()

    res_cv = ResultadoExtraccion(fuente=Fuente.CV)
    res_cv.entidades.append(
        EntidadExtraida(
            nombre="Entidad Uno",
            ambito=Ambito.MAYORES,
            direccion="Calle Mayor 1",
            codigo_postal="46001",
            longitud=-0.376,
            latitud=39.469,
            nombre_localidad="València",
            codigo_provincia="46",
            nombre_provincia="València/Valencia",
        )
    )
    res_cv.error(2, "id", TipoError.DUPLICADO, "ID repetido")
    res_cv.reparacion(1, "telefono", "96 000 00 00", "960000000", "Normalización")

    res_can = ResultadoExtraccion(fuente=Fuente.CAN)
    res_can.entidades.extend(
        [
            # Mismo nombre y misma localidad -> debe detectarse como duplicado en BD
            EntidadExtraida(
                nombre="entidad uno",
                ambito=Ambito.MAYORES,
                nombre_localidad="València",
                codigo_provincia="46",
                nombre_provincia="Valencia",
            ),
            # Misma provincia '46' y localidad 'València', entidad distinta -> debe insertarse
            EntidadExtraida(
                nombre="Entidad Dos",
                ambito=Ambito.INCLUSION_SOCIAL,
                nombre_localidad="València",
                codigo_provincia="46",
                nombre_provincia="Valencia",
            ),
        ]
    )

    with session_factory() as db:
        r1 = cargar_resultado_en_bd(db, res_cv)
        assert r1.insertadas == 1
        assert r1.omitidas_duplicado_bd == 0
        assert r1.errores_por_tipo == {"duplicado": 1}

        r2 = cargar_resultado_en_bd(db, res_can)
        assert r2.insertadas == 1
        assert r2.omitidas_duplicado_bd == 1

        estado = obtener_estado_almacen(db)
        assert estado.total_provincias == 1
        assert estado.total_localidades == 1
        assert estado.total_entidades == 2
        assert estado.entidades_por_ambito == {"MAYORES": 1, "INCLUSION_SOCIAL": 1}

        vaciar_almacen(db)
        vacio = obtener_estado_almacen(db)
        assert vacio.total_provincias == 0
        assert vacio.total_localidades == 0
        assert vacio.total_entidades == 0


def test_limpiar_geocache(tmp_path: Path) -> None:
    cache = tmp_path / "geocache.json"
    assert limpiar_geocache(cache) is False

    cache.write_text("{}", encoding="utf-8")
    assert limpiar_geocache(cache) is True
    assert not cache.exists()


def test_cli_ejecutar_demo_con_reset_cache_y_report_md_json(tmp_path: Path) -> None:
    session_factory = _crear_session_factory()
    cache = tmp_path / "geocache.json"
    cache.write_text('{"k": {}}', encoding="utf-8")

    can_json = tmp_path / "can_demo.json"
    can_json.write_text(
        json.dumps(
            [
                {
                    "nif": "G38000001",
                    "denominacion": "Entidad Demo Canarias",
                    "numero_registro": "ERE2026CA00001",
                    "direccion_tipo_via": "Calle",
                    "direccion_nombre_via": "Mayor",
                    "direccion_numero": "10",
                    "direccion_complemento": "_U",
                    "direccion_provincia_id": "99",
                    "direccion_provincia_nombre": "Desconocida",
                    "direccion_municipio_id": "38001",
                    "direccion_municipio_nombre": "Santa Cruz de Tenerife",
                    "telefono_1": "(34)922111222",
                    "telefono_2": "_U",
                    "pagina_web": "_U",
                    "area_nombre": "Tercera Edad",
                    "subarea_nombre": "_U",
                },
                {
                    "nif": "G38000002",
                    "denominacion": "",
                    "numero_registro": "ERE2026CA00002",
                    "direccion_provincia_id": "38",
                    "direccion_municipio_id": "38001",
                    "direccion_municipio_nombre": "Santa Cruz de Tenerife",
                    "area_nombre": "Mujer",
                    "subarea_nombre": "_U",
                },
            ]
        ),
        encoding="utf-8",
    )

    reporte_md = tmp_path / "informe.md"
    informe = ejecutar_demo(
        fuente="can",
        can_path=can_json,
        reset=True,
        reset_cache=True,
        usar_scraper=False,
        report_out=reporte_md,
        session_factory=session_factory,
        cache_path=cache,
    )

    assert not cache.exists()
    assert informe.estado_inicial.total_entidades == 0
    assert informe.estado_final.total_entidades == 1
    assert informe.estado_final.entidades[0].nombre == "Entidad Demo Canarias"
    assert informe.estado_final.entidades[0].codigo_provincia == "38"
    assert informe.resumenes[0].errores_total == 1
    assert informe.resumenes[0].reparaciones_total == 2
    assert reporte_md.is_file()
    contenido_md = reporte_md.read_text(encoding="utf-8")
    assert "Entidad Demo Canarias" in contenido_md
    assert "El campo denominación es nulo" in contenido_md

    reporte_json = tmp_path / "estado.json"
    informe_estado = ejecutar_demo(
        solo_estado=True,
        report_out=reporte_json,
        session_factory=session_factory,
    )
    assert informe_estado.resumenes == []
    assert informe_estado.estado_final.total_entidades == 1
    datos_json = json.loads(reporte_json.read_text(encoding="utf-8"))
    assert datos_json["estado_final"]["total_entidades"] == 1


def test_cli_main_solo_estado_con_parser(monkeypatch) -> None:
    session_factory = _crear_session_factory()
    monkeypatch.setattr("app.cli.demo_carga.SessionLocal", session_factory)

    exit_code = main(["--solo-estado"])
    assert exit_code == 0


def test_cli_menu_interactivo(tmp_path: Path) -> None:
    session_factory = _crear_session_factory()
    cache = tmp_path / "geocache.json"
    cache.write_text("{}", encoding="utf-8")

    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    (demo_dir / "datos-abiertos-csv-segundo-trimestre26.json").write_text(
        json.dumps(
            [
                {
                    "nif": "G38000001",
                    "denominacion": "Entidad Menu Demo",
                    "numero_registro": "ERE2026CA00001",
                    "direccion_tipo_via": "Calle",
                    "direccion_nombre_via": "Mayor",
                    "direccion_numero": "1",
                    "direccion_complemento": "_U",
                    "direccion_provincia_id": "38",
                    "direccion_provincia_nombre": "Santa Cruz de Tenerife",
                    "direccion_municipio_id": "38001",
                    "direccion_municipio_nombre": "Santa Cruz de Tenerife",
                    "telefono_1": "(34)922000111",
                    "telefono_2": "_U",
                    "pagina_web": "_U",
                    "area_nombre": "Mujer",
                    "subarea_nombre": "_U",
                }
            ]
        ),
        encoding="utf-8",
    )

    informe_md = tmp_path / "menu_informe.md"
    entradas = iter(
        [
            "9",
            "2",  # Desactivar scraper
            "7",  # Resetear caché
            "3",
            "s",  # Cargar CAN vaciando BD
            "5",  # Ver estado BD
            "8",
            str(informe_md),  # Guardar informe
            "6",
            "s",  # Vaciar BD
            "0",  # Salir
        ]
    )

    codigo = ejecutar_menu(
        demo_dir_inicial=demo_dir,
        input_fn=lambda _: next(entradas),
        session_factory=session_factory,
        cache_path=cache,
    )

    assert codigo == 0
    assert not cache.exists()
    assert informe_md.is_file()
    assert "Entidad Menu Demo" in informe_md.read_text(encoding="utf-8")
    with session_factory() as db:
        assert obtener_estado_almacen(db).total_entidades == 0

