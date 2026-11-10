import pytest

from app.extractors.catalogo_municipios import CatalogoMunicipios
from app.extractors.reparacion_texto import ReparadorTexto

CORPUS = [
    "AssociacióSolidàriaDelVallès",
    "AssociacióCulturalBarcelona",
    "FundacióAccióSolidària",
    "CarrerGuillemTell,47",
    "CarrerMallorca,2",
]


@pytest.fixture(scope="module")
def catalogo() -> CatalogoMunicipios:
    return CatalogoMunicipios()


@pytest.fixture(scope="module")
def reparador(catalogo: CatalogoMunicipios) -> ReparadorTexto:
    return ReparadorTexto(CORPUS, catalogo)


def test_catalogo_resuelve_municipio_pegado(catalogo: CatalogoMunicipios) -> None:
    municipio = catalogo.resolver("SantCugatdelVallès")
    assert municipio is not None
    assert municipio.nombre == "Sant Cugat del Vallès"
    assert municipio.cod_provincia == "08"


def test_catalogo_resuelve_articulo_entre_parentesis(catalogo: CatalogoMunicipios) -> None:
    municipio = catalogo.resolver("HospitaletdeLlobregat(L')")
    assert municipio is not None
    assert municipio.nombre == "l'Hospitalet de Llobregat"


def test_catalogo_no_resuelve_municipio_de_fuera(catalogo: CatalogoMunicipios) -> None:
    assert catalogo.resolver("Madrid") is None
    assert catalogo.provincia_de("Madrid") is None


def test_texto_separa_palabras_y_particulas(reparador: ReparadorTexto) -> None:
    assert (
        reparador.reparar_texto("AssociacióSolidàriadelVallès") == "Associació Solidària del Vallès"
    )


def test_direccion_separa_numeros_y_comas(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_texto("CarrerGuillemTell,47") == "Carrer Guillem Tell, 47"
    assert reparador.reparar_texto("Numància,149-151") == "Numància, 149-151"


def test_texto_vacio_devuelve_none(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_texto("   ") is None
    assert reparador.reparar_texto(None) is None


def test_email_restaura_puntos(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_email("asocolgi@gmailcom") == "asocolgi@gmail.com"
    assert reparador.reparar_email("avaluem@avaluemcat") == "avaluem@avaluem.cat"
    assert reparador.reparar_email("institut@idhCarrerorg") == "institut@idh.org"


def test_email_con_puntos_no_se_toca(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_email("info@africaviva.org") == "info@africaviva.org"


def test_email_irreparable_devuelve_none(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_email("sakadawaorggmailcom") is None
    assert reparador.reparar_email("ingman@ingmancatmaria_novella@igmancat") is None


def test_email_multiple_se_separa(reparador: ReparadorTexto) -> None:
    resultado = reparador.reparar_email("ongconosud@gmail.com\ninfoconosud@gmailcom")
    assert resultado == "ongconosud@gmail.com / infoconosud@gmail.com"


def test_url_restaura_puntos_y_esquema(reparador: ReparadorTexto) -> None:
    assert reparador.reparar_url("http://wwwazaharaorg") == "http://www.azahara.org"
    assert reparador.reparar_url("http://https://nexescatorg") == "https://nexescat.org"
    assert reparador.reparar_url("http://wwwaeryCarrerorg/") == "http://www.aery.org/"
    assert reparador.reparar_url("http://htpp://edpaCarrercat") == "http://edpa.cat"
