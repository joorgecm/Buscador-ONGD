from pathlib import Path

from app.extractors.catalogo_municipios import CatalogoMunicipios
from app.extractors.common import TipoError
from app.extractors.extractorCAT import ExtractorCAT
from app.llm.clasificador_ambito import ResultadoAmbito
from app.models.ambito import Ambito
from app.scraper.geocoder import DatosGeo
from app.wrappers.wrapperCAT import WrapperCAT

CABECERA = '<?xml version="1.0" encoding="utf-8"?>\n<registre_ongd>\n'


def _entitat(
    registre: str = "1",
    nombre: str = "AccióSolidàriadelVallès",
    cif: str = "",
    direccion: str = "Mallorca,2",
    cp: str = "08192",
    municipio: str = "SantQuirzedelVallès",
    fijo: str = "937214977",
    movil: str = "",
    email: str = "",
    web: str = "",
) -> str:
    return (
        f"<entitat><n_mero_registre>{registre}</n_mero_registre>"
        f"<nom_de_l_entitat>{nombre}</nom_de_l_entitat><naturalesa>Associació</naturalesa>"
        f"<cif_entitat>{cif}</cif_entitat><adre_a>{direccion}</adre_a>"
        f"<codi_postal>{cp}</codi_postal><municipi>{municipio}</municipi>"
        f"<tel_fon>{fijo}</tel_fon><tel_fon_m_bil>{movil}</tel_fon_m_bil>"
        f"<correu_electr_nic>{email}</correu_electr_nic><web>{web}</web></entitat>\n"
    )


class ClasificadorFalso:
    def __init__(self, por_defecto: bool = False) -> None:
        self.por_defecto = por_defecto

    def clasificar(self, entidades: list[tuple[str, str | None]]) -> list[ResultadoAmbito]:
        return [
            ResultadoAmbito(Ambito.MUJER, self.por_defecto, "prueba" if self.por_defecto else None)
            for _ in entidades
        ]


class GeoFalso:
    def __init__(self, geo: DatosGeo) -> None:
        self.geo = geo

    def geocodificar(self, **kwargs: object) -> DatosGeo:
        return self.geo


def _extraer(
    tmp_path: Path,
    entidades: list[str],
    geo: DatosGeo | None = None,
    clasificador: ClasificadorFalso | None = None,
):
    xml = tmp_path / "cat.xml"
    xml.write_text(CABECERA + "".join(entidades) + "</registre_ongd>", encoding="utf-8")
    return ExtractorCAT(
        wrapper=WrapperCAT(xml),
        scraper=GeoFalso(geo or DatosGeo(latitud=41.4, longitud=2.1)),
        catalogo=CatalogoMunicipios(),
        clasificador=clasificador or ClasificadorFalso(),
    ).extraer()


def test_entidad_valida_se_repara_y_se_carga(tmp_path: Path) -> None:
    resultado = _extraer(
        tmp_path,
        [_entitat(movil="650399867\n629401111", email="asoc@gmailcom", web="http://wwwazaharaorg")],
    )

    assert len(resultado.entidades) == 1
    entidad = resultado.entidades[0]
    assert entidad.nombre == "Acció Solidària del Vallès"
    assert entidad.direccion == "Mallorca, 2"
    assert entidad.nombre_localidad == "Sant Quirze del Vallès"
    assert entidad.codigo_provincia == "08"
    assert entidad.nombre_provincia == "Barcelona"
    assert entidad.codigo_postal == "08192"
    assert entidad.latitud == 41.4
    assert entidad.url == "http://www.azahara.org"
    assert entidad.contacto == ("Tel: 937214977 / 650399867 / 629401111 | Email: asoc@gmail.com")
    assert entidad.ambito == Ambito.MUJER
    assert not resultado.errores


def test_codigo_postal_de_otra_provincia_se_informa_y_se_anula(tmp_path: Path) -> None:
    resultado = _extraer(
        tmp_path,
        [_entitat(cp="00800", municipio="VilanovailaGeltrú")],
        geo=DatosGeo(latitud=41.2, longitud=1.7),
    )

    assert len(resultado.entidades) == 1
    assert resultado.entidades[0].codigo_postal is None
    assert resultado.entidades[0].codigo_provincia == "08"
    assert [(e.campo, e.tipo) for e in resultado.errores] == [("codi_postal", TipoError.SEMANTICO)]


def test_municipio_fuera_de_catalunya_no_se_carga(tmp_path: Path) -> None:
    resultado = _extraer(tmp_path, [_entitat(cp="28003", municipio="Madrid")])

    assert resultado.entidades == []
    assert [(e.campo, e.tipo) for e in resultado.errores] == [("municipi", TipoError.SEMANTICO)]


def test_cif_duplicado_se_informa_y_se_descarta(tmp_path: Path) -> None:
    resultado = _extraer(
        tmp_path,
        [
            _entitat(registre="1", cif="G111", nombre="EntitatUna"),
            _entitat(registre="2", cif="G111", nombre="EntitatDos"),
        ],
    )

    assert len(resultado.entidades) == 1
    assert [(e.campo, e.tipo, e.fila) for e in resultado.errores] == [
        ("cif_entitat", TipoError.DUPLICADO, 2)
    ]


def test_email_y_web_irreparables_se_informan(tmp_path: Path) -> None:
    resultado = _extraer(
        tmp_path, [_entitat(email="sakadawaorggmailcom", web="http://wwwocularisong")]
    )

    assert resultado.entidades[0].contacto == "Tel: 937214977"
    assert resultado.entidades[0].url is None
    assert {(e.campo, e.tipo) for e in resultado.errores} == {
        ("correu_electr_nic", TipoError.FORMATO),
        ("web", TipoError.FORMATO),
    }


def test_sin_resultado_de_geocodificacion_las_coordenadas_quedan_nulas(tmp_path: Path) -> None:
    resultado = _extraer(tmp_path, [_entitat()], geo=DatosGeo())

    assert resultado.entidades[0].latitud is None
    assert [(e.campo, e.tipo) for e in resultado.errores] == [("coordenadas", TipoError.NULO)]


def test_coordenadas_fuera_de_catalunya_se_informan(tmp_path: Path) -> None:
    resultado = _extraer(tmp_path, [_entitat()], geo=DatosGeo(latitud=40.4168, longitud=-3.7))

    assert resultado.entidades[0].latitud is None
    assert [(e.campo, e.tipo) for e in resultado.errores] == [
        ("coordenadas", TipoError.FUERA_DE_RANGO)
    ]


def test_codigo_postal_nulo_se_completa_con_el_geocodificador(tmp_path: Path) -> None:
    resultado = _extraer(
        tmp_path, [_entitat(cp="")], geo=DatosGeo(codigo_postal="08192", latitud=41.4, longitud=2.1)
    )

    assert resultado.entidades[0].codigo_postal == "08192"


def test_ambito_por_defecto_se_informa_como_reparacion(tmp_path: Path) -> None:
    resultado = _extraer(tmp_path, [_entitat()], clasificador=ClasificadorFalso(por_defecto=True))

    assert any(r.campo == "ambito" for r in resultado.reparaciones)
