from pathlib import Path

from app.core.config import BACKEND_DIR
from app.extractors.common import Fuente, TipoError
from app.extractors.extractorCV import ExtractorCV
from app.models.ambito import Ambito
from app.scraper.geocoder import DatosGeo
from app.wrappers.wrapperCV import WrapperCV

MUESTRA_CSV = BACKEND_DIR / "data" / "muestra_entidades_CV_20.csv"
COMPLETO_CSV = BACKEND_DIR / "data" / "entidades_CV.csv"


class ScraperMock:
    def __init__(
        self,
        cp: str = "46900",
        lat: float | None = None,
        lon: float | None = None,
    ) -> None:
        self.cp = cp
        self.lat = lat
        self.lon = lon

    def geocodificar(
        self,
        *,
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float | None = None,
        longitud: float | None = None,
    ) -> DatosGeo:
        return DatosGeo(codigo_postal=self.cp, latitud=self.lat, longitud=self.lon)


def test_extractor_cv_muestra_20() -> None:
    extractor = ExtractorCV(wrapper=WrapperCV(MUESTRA_CSV), usar_scraper=False)
    res = extractor.extraer()

    assert res.fuente == Fuente.CV
    assert len(res.entidades) == 20
    assert len(res.errores) == 0

    primera = res.entidades[0]
    assert primera.ambito == Ambito.MAYORES
    assert primera.codigo_provincia == "46"
    assert primera.nombre_provincia == "València/Valencia"
    assert primera.nombre_localidad == "Torrent"
    assert primera.longitud is not None and -1.7 <= primera.longitud <= 0.8
    assert primera.latitud is not None and 37.7 <= primera.latitud <= 41.0
    assert primera.contacto == "Tel: 961563155 | Email: residenciabconsejo@gmail.com"

    caritas = res.entidades[14]
    assert caritas.ambito == Ambito.INCLUSION_SOCIAL
    assert caritas.contacto == "Email: acsocial@caritas-sc.org"

    aldaia = res.entidades[15]
    assert aldaia.contacto == "Tel: 961500557"


def test_extractor_cv_con_scraper_asigna_cp_valido() -> None:
    extractor = ExtractorCV(
        wrapper=WrapperCV(MUESTRA_CSV),
        scraper=ScraperMock(cp="46900"),
    )
    res = extractor.extraer()

    entidades_valencia = [e for e in res.entidades if e.codigo_provincia == "46"]
    entidades_alicante = [e for e in res.entidades if e.codigo_provincia == "03"]

    assert all(e.codigo_postal == "46900" for e in entidades_valencia)
    assert all(e.codigo_postal is None for e in entidades_alicante)


def test_extractor_cv_archivo_completo_detecta_duplicados_y_ambitos() -> None:
    extractor = ExtractorCV(wrapper=WrapperCV(COMPLETO_CSV), usar_scraper=False)
    res = extractor.extraer()

    ambitos_obtenidos = {e.ambito for e in res.entidades}
    assert Ambito.EMPLEO_E_INSERCION_LABORAL in ambitos_obtenidos
    assert Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO in ambitos_obtenidos
    assert Ambito.INCLUSION_SOCIAL in ambitos_obtenidos

    duplicados = [err for err in res.errores if err.tipo == TipoError.DUPLICADO]
    assert len(duplicados) >= 1


def test_extractor_cv_reparaciones_y_errores(tmp_path: Path) -> None:
    csv_eval = tmp_path / "eval_cv.csv"
    lineas = [
        (
            "WKT,id,tipo_centro,nombre,domici,cod_ine_mun,provincia,municipio,"
            "sector,clasificacion,email,telefono,x_25830,y_25830"
        ),
        (
            "POINT (717780 4247138),1,CLUBS DE CONVIVENCIA,Club Alacant,C/ Mayor 1,"
            "3014,,Alacant,,POBLACIÓN EN GENERAL,INFO@ALACANT. ES,96 528 76 78,malo,4247138"
        ),
        (
            "POINT (726984 4373714),2,RESIDENCIAS,Residencia Valencia,C/ Colon 2,"
            "46250,València/Valencia,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            'zero@gva.es,0,"4373714,5","726984,2"'
        ),
        (
            "POINT (726984 4373714),2,RESIDENCIAS,Otra,C/ Colon 3,46250,"
            "València/Valencia,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            "zero@gva.es,0,726984,4373714"
        ),
        (
            "POINT (726984 4373714),3,RESIDENCIAS,   ,C/ Colon 3,46250,"
            "València/Valencia,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            "zero@gva.es,0,726984,4373714"
        ),
        (
            "POINT (726984 4373714),4,RESIDENCIAS,Centro Conflicto,C/ Colon 4,"
            "46250,Alacant/Alicante,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            "zero@gva.es,0,726984,4373714"
        ),
        (
            "POINT (100000 100000),5,RESIDENCIAS,Centro Lejano,C/ Colon 5,"
            "46250,València/Valencia,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            "zero@gva.es,0,100000,100000"
        ),
        (
            ",6,RESIDENCIAS,Centro Sin Coords,C/ Colon 6,46250,"
            "València/Valencia,València,PERSONAS MAYORES,PERSONAS MAYORES,"
            "zero@gva.es,0,abc,def"
        ),
    ]
    csv_eval.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    res = ExtractorCV(wrapper=WrapperCV(csv_eval), usar_scraper=False).extraer()

    assert len(res.entidades) == 2
    assert res.entidades[0].ambito == Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO
    assert res.entidades[0].codigo_provincia == "03"
    assert res.entidades[0].nombre_provincia == "Alacant/Alicante"
    assert res.entidades[0].contacto == "Tel: 965287678 | Email: info@alacant.es"

    tipos_error = {e.fila: e.tipo for e in res.errores}
    assert tipos_error[4] == TipoError.DUPLICADO
    assert tipos_error[5] == TipoError.NULO
    assert tipos_error[6] == TipoError.SEMANTICO
    assert tipos_error[7] == TipoError.FUERA_DE_RANGO
    assert tipos_error[8] == TipoError.FORMATO

    campos_esperados = {
        "sector",
        "cod_ine_mun",
        "provincia",
        "coordenadas",
        "email",
        "telefono",
    }
    campos_reparados = {r.campo for r in res.reparaciones}
    assert campos_esperados <= campos_reparados
