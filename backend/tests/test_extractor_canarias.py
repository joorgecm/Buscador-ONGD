import json
from pathlib import Path
from unittest.mock import patch

from app.core.config import BACKEND_DIR
from app.extractors import ExtractorCAN, ExtractorCAT, ExtractorCV, extraer_canarias
from app.extractors.common import Fuente, TipoError
from app.models.ambito import Ambito
from app.scraper.geocoder import DatosGeo

MUESTRA_JSON = BACKEND_DIR / "data" / "canarias_sample.json"
COMPLETO_JSON = BACKEND_DIR / "data" / "canarias.json"


class ScraperMock:
    def __init__(self, respuestas: dict[str, DatosGeo] | DatosGeo) -> None:
        self.respuestas = respuestas
        self.llamadas: list[tuple[str | None, str, str]] = []

    def geocodificar(
        self,
        *,
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float | None = None,
        longitud: float | None = None,
    ) -> DatosGeo:
        self.llamadas.append((direccion, municipio, provincia))
        if isinstance(self.respuestas, DatosGeo):
            return self.respuestas
        return self.respuestas.get(provincia, DatosGeo())


def _registro(**overrides: str) -> dict[str, str]:
    base = {
        "nif": "G35000001",
        "denominacion": "Entidad Prueba Canarias",
        "numero_registro": "ERE2025CA00001",
        "direccion_tipo_via": "Calle",
        "direccion_nombre_via": "Mayor",
        "direccion_numero": "10",
        "direccion_complemento": "_U",
        "direccion_provincia_id": "35",
        "direccion_provincia_nombre": "Las Palmas",
        "direccion_municipio_id": "35001",
        "direccion_municipio_nombre": "Palmas de Gran Canaria (Las)",
        "direccion_isla_id": "GC",
        "direccion_isla_nombre": "Gran Canaria",
        "telefono_1": "(34)928111222",
        "telefono_2": "_U",
        "pagina_web": "www.ejemplo.org",
        "area_id": "03",
        "area_nombre": "Discapacidad",
        "subarea_id": "_U",
        "subarea_nombre": "_U",
    }
    base.update(overrides)
    return base


def test_exports_paquete_extractors() -> None:
    assert ExtractorCAN is not None
    assert ExtractorCV is not None
    assert ExtractorCAT is not None
    assert callable(extraer_canarias)


def test_extractor_canarias_muestra_sin_scraper() -> None:
    res = extraer_canarias(MUESTRA_JSON, usar_scraper=False)

    assert res.fuente == Fuente.CAN
    assert len(res.entidades) == 34
    assert [(e.fila, e.campo, e.tipo) for e in res.errores] == [
        (35, "numero_registro", TipoError.DUPLICADO)
    ]

    primera = res.entidades[0]
    assert primera.nombre == "Asociacion Adepsi"
    assert primera.ambito == Ambito.DISCAPACIDAD
    assert primera.direccion == "Calle Lomo La Plana Nº 28"
    assert primera.nombre_localidad == "Las Palmas de Gran Canaria"
    assert primera.codigo_provincia == "35"
    assert primera.nombre_provincia == "Las Palmas"
    assert primera.contacto == "Tel: 928414484"
    assert primera.url == "https://www.adepsi.org"
    assert primera.codigo_postal is None
    assert primera.latitud is None
    assert primera.longitud is None

    multi_tel = next(
        e for e in res.entidades if e.nombre == "Asoc Benefico Social FaycaN-Ciudad Alta"
    )
    assert multi_tel.contacto == "Tel: 928208591 / 928250125"


def test_extractor_canarias_archivo_completo_sin_scraper() -> None:
    res = extraer_canarias(COMPLETO_JSON, usar_scraper=False)

    assert len(res.entidades) == 749
    assert len(res.errores) == 61
    assert all(e.tipo == TipoError.DUPLICADO for e in res.errores)

    for ent in res.entidades:
        assert len(ent.nombre) <= 300
        assert ent.direccion is None or len(ent.direccion) <= 300
        assert ent.contacto is None or (
            ent.contacto.startswith("Tel: ") and len(ent.contacto) <= 300
        )
        assert ent.url is None or len(ent.url) <= 500
        assert len(ent.nombre_localidad) <= 150
        assert len(ent.codigo_provincia) == 2
        assert len(ent.nombre_provincia) <= 100


def test_extractor_canarias_con_scraper_asigna_cp_y_coordenadas(tmp_path: Path) -> None:
    archivo = tmp_path / "canarias.json"
    datos = [
        _registro(numero_registro="1"),
        _registro(
            numero_registro="2",
            direccion_provincia_id="28",
            direccion_provincia_nombre="Madrid",
            direccion_municipio_id="28079",
            direccion_municipio_nombre="Madrid",
        ),
        _registro(
            numero_registro="3",
            direccion_provincia_id="06",
            direccion_provincia_nombre="Badajoz",
            direccion_municipio_id="06015",
            direccion_municipio_nombre="Badajoz",
        ),
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    scraper = ScraperMock(
        {
            "Las Palmas": DatosGeo(
                codigo_postal="35011", latitud=28.12354321, longitud=-15.43629876
            ),
            "Madrid": DatosGeo(codigo_postal="28001", latitud=40.416775, longitud=-3.70379),
            "Badajoz": DatosGeo(codigo_postal="6001", latitud=38.8794, longitud=-6.9707),
        }
    )

    res = extraer_canarias(archivo, scraper=scraper)

    assert len(res.entidades) == 3
    assert len(res.errores) == 0
    assert len(scraper.llamadas) == 3

    canaria, madrid, badajoz = res.entidades
    assert canaria.codigo_postal == "35011"
    assert canaria.latitud == 28.123543
    assert canaria.longitud == -15.436299
    assert madrid.codigo_postal == "28001"
    assert madrid.latitud == 40.416775
    assert badajoz.codigo_postal == "06001"
    assert sum(1 for r in res.reparaciones if r.campo == "codigo_postal") == 3


def test_extractor_canarias_scraper_rechaza_cp_y_coords_fuera_de_rango(tmp_path: Path) -> None:
    archivo = tmp_path / "canarias_err.json"
    datos = [
        _registro(numero_registro="1"),
        _registro(numero_registro="2"),
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    class ScraperSecuencial:
        def __init__(self) -> None:
            self.idx = 0

        def geocodificar(self, **kwargs: object) -> DatosGeo:
            self.idx += 1
            if self.idx == 1:
                return DatosGeo(codigo_postal="38001", latitud=40.4168, longitud=-3.7038)
            return DatosGeo()

    res = extraer_canarias(archivo, scraper=ScraperSecuencial())

    assert len(res.entidades) == 2
    assert res.entidades[0].codigo_postal is None
    assert res.entidades[0].latitud is None
    assert res.entidades[1].latitud is None
    assert [(e.fila, e.campo, e.tipo) for e in res.errores] == [
        (1, "coordenadas", TipoError.FUERA_DE_RANGO),
        (2, "coordenadas", TipoError.NULO),
    ]


def test_extractor_canarias_reparaciones_deducciones_y_truncado(tmp_path: Path) -> None:
    archivo = tmp_path / "sintetico.json"
    datos = [
        _registro(
            numero_registro="1",
            denominacion="Asociación Salud Mental " + ("X" * 320),
            area_nombre="Discapacidad",
            direccion_nombre_via="Avenida " + ("Y" * 310),
            direccion_numero="0",
            direccion_provincia_id="_U",
            direccion_provincia_nombre="_U",
            direccion_municipio_id="38023",
            direccion_municipio_nombre="_U",
            telefono_1="(34)922111222",
            telefono_2="(34)922111222",
            pagina_web="hhtps://www." + ("a" * 510) + ".org",
        ),
        _registro(
            numero_registro="2",
            direccion_municipio_nombre="Oliva La",
            pagina_web="correo@ejemplo.com",
            telefono_1="_U",
            telefono_2="_U",
        ),
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    res = extraer_canarias(archivo, usar_scraper=False)

    assert len(res.entidades) == 2
    assert len(res.errores) == 0

    ent1, ent2 = res.entidades
    assert ent1.ambito == Ambito.SALUD_MENTAL
    assert ent1.codigo_provincia == "38"
    assert ent1.nombre_provincia == "Santa Cruz de Tenerife"
    assert ent1.nombre_localidad == "Santa Cruz de Tenerife"
    assert ent1.contacto == "Tel: 922111222"
    assert len(ent1.nombre) == 300
    assert ent1.direccion is not None and len(ent1.direccion) == 300
    assert ent1.url is not None and ent1.url.startswith("https://") and len(ent1.url) == 500

    assert ent2.nombre_localidad == "La Oliva"
    assert ent2.url is None
    assert ent2.contacto is None


def test_extractor_canarias_archivo_inexistente_o_invalido(tmp_path: Path) -> None:
    res_no = extraer_canarias(tmp_path / "no_existe.json", usar_scraper=False)
    assert res_no.entidades == []
    assert [(e.campo, e.tipo) for e in res_no.errores] == [("archivo", TipoError.FORMATO)]

    roto = tmp_path / "roto.json"
    roto.write_text("{no json", encoding="utf-8")
    res_roto = extraer_canarias(roto, usar_scraper=False)
    assert res_roto.entidades == []
    assert [(e.campo, e.tipo) for e in res_roto.errores] == [("archivo", TipoError.FORMATO)]


def test_extractor_canarias_instancia_y_cierra_scraper_por_defecto(tmp_path: Path) -> None:
    archivo = tmp_path / "auto_scraper.json"
    archivo.write_text(json.dumps([_registro(numero_registro="1")]), encoding="utf-8")

    class ScraperAutoMock:
        def __init__(self) -> None:
            self.cerrado = False

        def geocodificar(self, **kwargs: object) -> DatosGeo:
            return DatosGeo(codigo_postal="35001", latitud=28.12, longitud=-15.43)

        def cerrar(self) -> None:
            self.cerrado = True

    instancia = ScraperAutoMock()
    with patch("app.extractors.canarias.ScraperGeo", return_value=instancia):
        res = extraer_canarias(archivo)

    assert instancia.cerrado is True
    assert len(res.entidades) == 1
    assert res.entidades[0].codigo_postal == "35001"
    assert res.entidades[0].latitud == 28.12
    assert res.entidades[0].longitud == -15.43


def test_extractor_canarias_limpia_direccion_de_busqueda_para_scraper(tmp_path: Path) -> None:
    archivo = tmp_path / "dir_busqueda.json"
    datos = [
        _registro(
            numero_registro="1",
            direccion_tipo_via="Avda",
            direccion_nombre_via="Avenida De Escaleritas 64",
            direccion_numero="64",
            direccion_complemento="1",
        ),
        _registro(
            numero_registro="2",
            direccion_tipo_via="Calle",
            direccion_nombre_via="C/ Escultor Estevez",
            direccion_numero="17",
            direccion_complemento=" 12",
        ),
        _registro(
            numero_registro="3",
            direccion_tipo_via="Cmno",
            direccion_nombre_via="Real",
            direccion_numero="03",
            direccion_complemento="Bajo",
        ),
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    scraper = ScraperMock(DatosGeo(codigo_postal="35011", latitud=28.12, longitud=-15.43))
    res = extraer_canarias(archivo, scraper=scraper)

    assert len(res.entidades) == 3
    assert [llamada[0] for llamada in scraper.llamadas] == [
        "Avenida De Escaleritas 64",
        "C/ Escultor Estevez 17",
        "Camino Real 3",
    ]
    assert res.entidades[0].direccion == "Avda Avenida De Escaleritas 64 Nº 64 1"


def test_extractor_canarias_tolera_datos_distintos_tipos_e_inconsistencias(
    tmp_path: Path,
) -> None:
    archivo = tmp_path / "distinto.json"
    datos = [
        "elemento_no_dict",
        {
            **_registro(numero_registro="10"),
            "direccion_numero": 28,
            "direccion_provincia_id": 35,
            "direccion_municipio_id": 35001,
            "telefono_1": 928111222,
            "area_nombre": " exclusion social ",
        },
        _registro(
            numero_registro="11",
            direccion_provincia_id="35",
            direccion_municipio_id="38001",
        ),
        _registro(
            numero_registro="12",
            direccion_provincia_id="99",
            direccion_provincia_nombre="Desconocida",
            direccion_municipio_id="38430",
            direccion_municipio_nombre="Tacoronte",
        ),
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    res = extraer_canarias(archivo, usar_scraper=False)

    assert len(res.entidades) == 2
    assert res.entidades[0].ambito == Ambito.INCLUSION_SOCIAL
    assert res.entidades[0].direccion == "Calle Mayor Nº 28"
    assert res.entidades[0].contacto == "Tel: 928111222"
    assert res.entidades[1].codigo_provincia == "38"
    assert res.entidades[1].nombre_provincia == "Santa Cruz de Tenerife"
    assert res.entidades[1].nombre_localidad == "Tacoronte"
    assert [(e.fila, e.campo, e.tipo) for e in res.errores] == [
        (1, "registro", TipoError.FORMATO),
        (3, "provincia", TipoError.SEMANTICO),
    ]


def test_extractor_can_lee_archivo_directamente_con_scraper() -> None:
    extractor = ExtractorCAN(
        MUESTRA_JSON,
        scraper=ScraperMock(
            {
                "Las Palmas": DatosGeo(codigo_postal="35019", latitud=28.1043, longitud=-15.4513),
                "Santa Cruz de Tenerife": DatosGeo(
                    codigo_postal="38203", latitud=28.4879, longitud=-16.3220
                ),
                "Madrid": DatosGeo(codigo_postal="28001", latitud=40.4168, longitud=-3.7038),
                "Badajoz": DatosGeo(codigo_postal="06001", latitud=38.8794, longitud=-6.9707),
            }
        ),
    )
    res = extractor.extraer()

    assert res.fuente == Fuente.CAN
    assert len(res.entidades) == 34
    assert [(e.fila, e.campo, e.tipo) for e in res.errores] == [
        (35, "numero_registro", TipoError.DUPLICADO)
    ]
    assert res.entidades[0].codigo_postal == "35019"
    assert res.entidades[0].latitud == 28.1043


def test_extractor_can_no_usa_red_ni_wrapper(tmp_path: Path) -> None:
    archivo = tmp_path / "can.json"
    archivo.write_text(json.dumps([_registro(numero_registro="1")]), encoding="utf-8")

    with patch("httpx.get", side_effect=AssertionError("no debe llamar a la red")):
        res = ExtractorCAN(archivo, usar_scraper=False).extraer()

    assert len(res.entidades) == 1
    assert res.entidades[0].nombre == "Entidad Prueba Canarias"



