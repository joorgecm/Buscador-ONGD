"""CLI de demo: ejecuta extractores, carga en PostgreSQL y genera informe.

Uso habitual desde `backend/`:
    uv run python -m app.cli.demo_carga --fuente all --reset --demo-dir "<ruta_archivos_demo>"
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.db.session import SessionLocal
from app.extractors import ExtractorCAN, ExtractorCAT, ExtractorCV
from app.extractors.common import ResultadoExtraccion
from app.schemas.carga import EstadoAlmacen, InformeCarga, ResumenFuenteCarga
from app.services.carga import (
    cargar_resultado_en_bd,
    limpiar_geocache,
    obtener_estado_almacen,
    vaciar_almacen,
)

FUENTES_VALIDAS = ("cv", "cat", "can")


def _resolver_ruta_fuente(
    fuente: str,
    *,
    explicit_path: Path | None,
    demo_dir: Path | None,
) -> Path:
    if explicit_path is not None:
        return explicit_path

    if demo_dir is not None:
        candidatos: dict[str, tuple[str, ...]] = {
            "cv": ("entidades_CV.csv", "muestra_entidades_CV_20.csv"),
            "cat": ("Entitats_ONGD_pretty.xml",),
            "can": (
                "datos-abiertos-csv-segundo-trimestre26.json",
                "canarias_sample.json",
                "canarias.json",
            ),
        }
        for nombre in candidatos[fuente]:
            candidato = demo_dir / nombre
            if candidato.is_file():
                return candidato
        return demo_dir / candidatos[fuente][0]

    por_defecto: dict[str, Path] = {
        "cv": settings.CV_CSV_PATH,
        "cat": settings.CAT_XML_PATH,
        "can": settings.CAN_JSON_PATH,
    }
    return por_defecto[fuente]


def _construir_extractor(fuente: str, ruta: Path, *, usar_scraper: bool):
    if fuente == "cv":
        return ExtractorCV(ruta, usar_scraper=usar_scraper)
    if fuente == "cat":
        return ExtractorCAT(ruta, usar_scraper=usar_scraper)
    if fuente == "can":
        return ExtractorCAN(ruta, usar_scraper=usar_scraper)
    raise ValueError(f"Fuente no soportada: {fuente}")


def _imprimir_estado(titulo: str, estado: EstadoAlmacen) -> None:
    print(f"\n=== {titulo} ===")
    print(
        f"Provincias: {estado.total_provincias} | "
        f"Localidades: {estado.total_localidades} | "
        f"Entidades: {estado.total_entidades}"
    )
    if estado.entidades_por_ambito:
        print("Distribución por ámbito:")
        for ambito, cnt in sorted(estado.entidades_por_ambito.items()):
            print(f"  - {ambito}: {cnt}")
    if estado.entidades:
        print("Entidades almacenadas en PostgreSQL:")
        for ent in estado.entidades:
            cp = ent.codigo_postal or "-"
            coords = (
                f"({ent.latitud:.6f}, {ent.longitud:.6f})"
                if ent.latitud is not None and ent.longitud is not None
                else "(-)"
            )
            print(
                f"  [{ent.cod_entidad}] {ent.nombre} | {ent.ambito} | "
                f"{ent.localidad} ({ent.codigo_provincia}) | CP={cp} | {coords}"
            )


def _imprimir_resumen_fuente(resumen: ResumenFuenteCarga) -> None:
    print(
        f"\n--- Resumen carga [{resumen.fuente.value}] ---\n"
        f"  Válidas extraídas : {resumen.extraidas}\n"
        f"  Insertadas en BD  : {resumen.insertadas}\n"
        f"  Omitidas dup. BD  : {resumen.omitidas_duplicado_bd}\n"
        f"  Errores           : {resumen.errores_total} ({resumen.errores_por_tipo or {}})\n"
        f"  Reparaciones      : {resumen.reparaciones_total}"
    )
    if resumen.errores:
        print("  Detalle de errores:")
        for err in resumen.errores:
            fila_txt = f"fila {err.fila}" if err.fila is not None else "archivo"
            print(f"    * [{fila_txt}] {err.campo} ({err.tipo.value}): {err.motivo}")
    if resumen.reparaciones:
        print("  Detalle de reparaciones:")
        for rep in resumen.reparaciones:
            fila_txt = f"fila {rep.fila}" if rep.fila is not None else "archivo"
            print(
                f"    * [{fila_txt}] {rep.campo}: "
                f"{rep.valor_antes!r} -> {rep.valor_despues!r} ({rep.regla})"
            )


def _exportar_informe(informe: InformeCarga, ruta_salida: Path) -> None:
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    if ruta_salida.suffix.lower() == ".json":
        ruta_salida.write_text(informe.model_dump_json(indent=2), encoding="utf-8")
    else:
        ruta_salida.write_text(informe.a_markdown(), encoding="utf-8")
    print(f"\nInforme guardado en: {ruta_salida}")


def ejecutar_demo(
    *,
    fuente: str = "all",
    demo_dir: Path | None = None,
    cv_path: Path | None = None,
    cat_path: Path | None = None,
    can_path: Path | None = None,
    reset: bool = False,
    reset_cache: bool = False,
    usar_scraper: bool = True,
    solo_estado: bool = False,
    report_out: Path | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
    cache_path: Path | str | None = None,
) -> InformeCarga:
    """Orquesta la limpieza opcional, extracción, carga en BD y generación del informe."""
    if reset_cache:
        eliminada = limpiar_geocache(cache_path)
        estado_cache = "eliminada" if eliminada else "no existía"
        print(f"Caché de geocodificación {estado_cache}.")

    with session_factory() as db:
        if reset:
            vaciar_almacen(db)
            print("Base de datos vaciada (TRUNCATE / RESET IDENTITY).")

        estado_inicial = obtener_estado_almacen(db)
        _imprimir_estado("Estado inicial de la base de datos", estado_inicial)

        resumenes: list[ResumenFuenteCarga] = []
        if not solo_estado:
            fuentes = list(FUENTES_VALIDAS) if fuente == "all" else [fuente]
            rutas_explicitas = {"cv": cv_path, "cat": cat_path, "can": can_path}

            for codigo_fuente in fuentes:
                ruta = _resolver_ruta_fuente(
                    codigo_fuente,
                    explicit_path=rutas_explicitas[codigo_fuente],
                    demo_dir=demo_dir,
                )
                print(f"\nEjecutando extractor [{codigo_fuente.upper()}] sobre: {ruta}")
                extractor = _construir_extractor(codigo_fuente, ruta, usar_scraper=usar_scraper)
                resultado: ResultadoExtraccion = extractor.extraer()
                resumen = cargar_resultado_en_bd(db, resultado)
                resumenes.append(resumen)
                _imprimir_resumen_fuente(resumen)

        estado_final = obtener_estado_almacen(db)
        if not solo_estado:
            _imprimir_estado("Estado final de la base de datos", estado_final)

        informe = InformeCarga(
            estado_inicial=estado_inicial,
            resumenes=resumenes,
            estado_final=estado_final,
        )
        if report_out is not None:
            _exportar_informe(informe, report_out)
        return informe


def _crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Demo CLI: ejecuta extractores, carga en PostgreSQL y muestra informe.",
    )
    parser.add_argument(
        "--fuente",
        choices=("cv", "cat", "can", "all"),
        default="all",
        help="Fuente a extraer y cargar (por defecto: all).",
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=None,
        help="Directorio que contiene los ficheros de demo (CSV, XML, JSON).",
    )
    parser.add_argument("--cv-path", type=Path, default=None, help="Ruta manual CSV de CV.")
    parser.add_argument("--cat-path", type=Path, default=None, help="Ruta manual XML de CAT.")
    parser.add_argument("--can-path", type=Path, default=None, help="Ruta manual JSON de CAN.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Vacía las tablas de PostgreSQL antes de cargar (empezar con BD vacía).",
    )
    parser.add_argument(
        "--reset-cache",
        action="store_true",
        help="Elimina el archivo de caché de geocodificación (geocache.json) antes de ejecutar.",
    )
    parser.add_argument(
        "--sin-scraper",
        action="store_true",
        help="Desactiva el scraper de geocodificación (usar_scraper=False).",
    )
    parser.add_argument(
        "--solo-estado",
        action="store_true",
        help="Muestra únicamente lo que hay en PostgreSQL sin ejecutar extractores.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="Guarda el informe completo en un archivo (.md o .json).",
    )
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Abre el menú interactivo de demo.",
    )
    return parser


def _detectar_demo_dir_por_defecto() -> Path | None:
    en_repo = BACKEND_DIR / "data" / "demo"
    if en_repo.is_dir():
        return en_repo
    en_descargas = Path.home() / "Downloads" / "Iei" / "Proyecto" / "Entrega_1" / "Archivos_demo"
    return en_descargas if en_descargas.is_dir() else None


def _ruta_cache_efectiva(cache_path: Path | str | None) -> Path:
    ruta = Path(cache_path) if cache_path is not None else settings.GEOCACHE_PATH
    return ruta if ruta.is_absolute() else BACKEND_DIR / ruta


def _leer_estado_seguro(session_factory: Callable[[], Session]) -> str:
    try:
        with session_factory() as db:
            est = obtener_estado_almacen(db)
        return (
            f"{est.total_provincias} provincias | "
            f"{est.total_localidades} localidades | "
            f"{est.total_entidades} entidades"
        )
    except Exception as exc:
        return f"Sin conexión ({exc})"


def _preguntar_si_no(input_fn: Callable[[str], str], mensaje: str) -> bool:
    resp = input_fn(mensaje).strip().casefold()
    return resp in {"s", "si", "sí", "y", "yes"}


def _ejecutar_carga_desde_menu(
    *,
    fuente: str,
    demo_dir: Path | None,
    usar_scraper: bool,
    input_fn: Callable[[str], str],
    session_factory: Callable[[], Session],
    cache_path: Path | str | None,
) -> InformeCarga | None:
    reset = _preguntar_si_no(input_fn, "¿Vaciar la BD antes de cargar? [s/N]: ")
    try:
        return ejecutar_demo(
            fuente=fuente,
            demo_dir=demo_dir,
            reset=reset,
            usar_scraper=usar_scraper,
            session_factory=session_factory,
            cache_path=cache_path,
        )
    except Exception as exc:
        print(f"\n[ERROR] No se pudo completar la carga: {exc}")
        return None


def _cambiar_carpeta_datos(
    demo_dir_actual: Path | None,
    demo_detectado: Path | None,
    input_fn: Callable[[str], str],
) -> Path | None:
    print("\nOpciones de carpeta de datos:")
    print(f"  1. Por defecto del proyecto ({BACKEND_DIR / 'data'})")
    if demo_detectado is not None:
        print(f"  2. Carpeta de demo ({demo_detectado})")
    print("  3. Introducir otra ruta manualmente")
    sel = input_fn("Elige opción [Enter para cancelar]: ").strip()
    if sel == "1":
        return None
    if sel == "2" and demo_detectado is not None:
        return demo_detectado
    if sel == "3":
        nueva = Path(input_fn("Ruta de la carpeta: ").strip().strip('"'))
        if nueva.is_dir():
            return nueva
        print(f"[AVISO] No existe la carpeta: {nueva}")
    return demo_dir_actual


def ejecutar_menu(
    *,
    demo_dir_inicial: Path | None = None,
    input_fn: Callable[[str], str] = input,
    session_factory: Callable[[], Session] = SessionLocal,
    cache_path: Path | str | None = None,
) -> int:
    """Menú interactivo sencillo para ejecutar la demo sin comandos largos."""
    demo_detectado = _detectar_demo_dir_por_defecto()
    demo_dir = demo_dir_inicial if demo_dir_inicial is not None else demo_detectado
    usar_scraper = True
    ultimo_informe: InformeCarga | None = None
    ruta_cache = _ruta_cache_efectiva(cache_path)

    acciones_fuente = {"1": "cv", "2": "cat", "3": "can", "4": "all"}

    while True:
        origen_txt = str(demo_dir) if demo_dir is not None else f"{BACKEND_DIR / 'data'} (config)"
        cache_txt = "presente" if ruta_cache.is_file() else "vacía"
        scraper_txt = "activado" if usar_scraper else "desactivado"
        estado_txt = _leer_estado_seguro(session_factory)

        print("\n" + "=" * 62)
        print("  DEMO BUSCADOR ONGD (IEI) - MENÚ PRINCIPAL")
        print("=" * 62)
        print(f"  Datos   : {origen_txt}")
        print(f"  BD      : {estado_txt}")
        print(f"  Caché   : {cache_txt} ({ruta_cache.name}) | Scraper: {scraper_txt}")
        print("-" * 62)
        print("  1. Cargar Comunitat Valenciana (CV)")
        print("  2. Cargar Catalunya (CAT)")
        print("  3. Cargar Canarias (CAN)")
        print("  4. Cargar TODAS las fuentes (CV + CAT + CAN)")
        print("  5. Ver qué hay ahora en la BD")
        print("  6. Vaciar BD (TRUNCATE + RESET IDENTITY)")
        print("  7. Resetear caché de geocodificación (geocache.json)")
        print("  8. Guardar informe en Markdown (.md)")
        print("  9. Cambiar carpeta de datos / activar o desactivar scraper")
        print("  0. Salir")
        print("=" * 62)

        opcion = input_fn("Elige una opción: ").strip()

        if opcion == "0":
            print("Hasta luego.")
            return 0

        if opcion in acciones_fuente:
            informe = _ejecutar_carga_desde_menu(
                fuente=acciones_fuente[opcion],
                demo_dir=demo_dir,
                usar_scraper=usar_scraper,
                input_fn=input_fn,
                session_factory=session_factory,
                cache_path=cache_path,
            )
            if informe is not None:
                ultimo_informe = informe
        elif opcion == "5":
            try:
                ultimo_informe = ejecutar_demo(
                    solo_estado=True,
                    session_factory=session_factory,
                    cache_path=cache_path,
                )
            except Exception as exc:
                print(f"\n[ERROR] No se pudo consultar la BD: {exc}")
        elif opcion == "6":
            if _preguntar_si_no(input_fn, "¿Seguro que quieres vaciar toda la BD? [s/N]: "):
                try:
                    with session_factory() as db:
                        vaciar_almacen(db)
                    print("BD vaciada correctamente.")
                except Exception as exc:
                    print(f"\n[ERROR] No se pudo vaciar la BD: {exc}")
        elif opcion == "7":
            eliminada = limpiar_geocache(cache_path)
            print("Caché eliminada." if eliminada else "La caché ya estaba vacía.")
        elif opcion == "8":
            if ultimo_informe is None:
                try:
                    ultimo_informe = ejecutar_demo(
                        solo_estado=True,
                        session_factory=session_factory,
                        cache_path=cache_path,
                    )
                except Exception as exc:
                    print(f"\n[ERROR] No se pudo generar el informe: {exc}")
                    continue
            destino_raw = input_fn("Ruta del informe [informe_demo.md]: ").strip()
            destino = Path(destino_raw) if destino_raw else Path("informe_demo.md")
            _exportar_informe(ultimo_informe, destino)
        elif opcion == "9":
            sub = input_fn("1=Cambiar carpeta | 2=Alternar scraper: ").strip()
            if sub == "1":
                demo_dir = _cambiar_carpeta_datos(demo_dir, demo_detectado, input_fn)
            elif sub == "2":
                usar_scraper = not usar_scraper
                print(f"Scraper {'activado' if usar_scraper else 'desactivado'}.")
        else:
            print("Opción no válida. Elige un número del 0 al 9.")


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None and len(sys.argv) == 1:
        return ejecutar_menu()

    parser = _crear_parser()
    args = parser.parse_args(argv)
    if args.menu:
        return ejecutar_menu(demo_dir_inicial=args.demo_dir)

    ejecutar_demo(
        fuente=args.fuente,
        demo_dir=args.demo_dir,
        cv_path=args.cv_path,
        cat_path=args.cat_path,
        can_path=args.can_path,
        reset=args.reset,
        reset_cache=args.reset_cache,
        usar_scraper=not args.sin_scraper,
        solo_estado=args.solo_estado,
        report_out=args.report_out,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
