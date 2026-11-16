"""Tests unitarios y de endpoint para el Wrapper de la Comunitat Valenciana (wrapperCV)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR
from app.main import app
from app.wrappers.wrapperCV import WrapperCV

MUESTRA_CSV = BACKEND_DIR / "data" / "muestra_entidades_CV_20.csv"
COMPLETO_CSV = BACKEND_DIR / "data" / "entidades_CV.csv"


def test_wrapper_cv_lee_muestra_por_defecto() -> None:
    wrapper = WrapperCV(MUESTRA_CSV)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 20
    assert entidades[0].fila == 2
    assert entidades[-1].fila == 21

    # Fila 2: comprobar campos principales, WKT y clasificacion
    primera = entidades[0]
    assert primera.id == "270"
    assert primera.WKT == "POINT (718183 4368857)"
    assert primera.municipio == "Torrent"
    assert primera.provincia == "València/Valencia"
    assert primera.cod_ine_mun == "46244"
    assert primera.sector == "PERSONAS MAYORES"
    assert primera.clasificacion == "PERSONAS MAYORES"
    assert primera.x_25830 == "718183"
    assert primera.y_25830 == "4368857"

    # Fila 8 del CSV (índice 6): email vacío -> None y coordenadas decimales preservadas
    cim_benicassim = entidades[6]
    assert cim_benicassim.fila == 8
    assert cim_benicassim.id == "1699"
    assert cim_benicassim.email is None
    assert cim_benicassim.x_25830 == "761156.21"
    assert cim_benicassim.y_25830 == "4438160.02"

    # Fila 9 del CSV (índice 7): comillas dobles escapadas en el nombre
    adis = entidades[7]
    assert adis.nombre == 'CENTRO DE ATENCION TEMPRANA "ADIS VEGA BAJA"'


def test_wrapper_cv_lee_archivo_completo() -> None:
    wrapper = WrapperCV(COMPLETO_CSV)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 1697
    # Comprobar municipio con coma interna (fila 33, id 32: "Pinós, el/Pinoso")
    pinoso = wrapper.obtener_entidades(id="32")
    assert len(pinoso) == 1
    assert pinoso[0].municipio == "Pinós, el/Pinoso"
    assert pinoso[0].cod_ine_mun == "03105"


def test_wrapper_cv_filtros() -> None:
    wrapper = WrapperCV(MUESTRA_CSV)

    por_provincia = wrapper.obtener_entidades(provincia="Castellón")
    assert len(por_provincia) == 4

    por_sector = wrapper.obtener_entidades(sector="INFANCIA")
    assert len(por_sector) == 1
    assert por_sector[0].municipio == "Gandia"

    por_ine = wrapper.obtener_entidades(cod_ine_mun="03065")
    assert len(por_ine) == 2


def test_wrapper_cv_tolera_bom_punto_y_coma_y_errores_crudos(tmp_path: Path) -> None:
    csv_sucio = tmp_path / "evaluacion_cv.csv"
    contenido = (
        "\ufeffWKT;id;tipo_centro;nombre;domici;cod_ine_mun;provincia;municipio;"
        "sector;clasificacion;email;telefono;x_25830;y_25830\n"
        "\n"
        "POINT (700000 4300000);99;ALBERGUES;  Albergue Test  ;;3014;Alacant/Alicante;"
        "Alicante;POBLACIÓN EN GENERAL;POBLACIÓN EN GENERAL;zero@gva.es;0;texto_malo;4300000\n"
    )
    csv_sucio.write_text(contenido, encoding="utf-8")

    wrapper = WrapperCV(csv_sucio)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 1
    reg = entidades[0]
    assert reg.fila == 3  # línea 1 cabecera, línea 2 vacía ignorada, línea 3 registro
    assert reg.WKT == "POINT (700000 4300000)"
    assert reg.nombre == "  Albergue Test  "  # sin alterar para que el Extractor haga trim/repare
    assert reg.domici is None
    assert reg.x_25830 == "texto_malo"  # valor erróneo preservado para que el Extractor informe


def test_wrapper_cv_archivo_inexistente(tmp_path: Path) -> None:
    wrapper = WrapperCV(tmp_path / "no_existe.csv")
    with pytest.raises(FileNotFoundError):
        wrapper.obtener_entidades()


def test_endpoint_wrappers_cv() -> None:
    client = TestClient(app)

    resp = client.get("/wrappers/cv")
    assert resp.status_code == 200
    datos = resp.json()
    assert len(datos) == 20
    assert datos[0]["id"] == "270"

    resp_filtrado = client.get("/wrappers/cv", params={"sector": "MUJERES"})
    assert resp_filtrado.status_code == 200
    mujeres = resp_filtrado.json()
    assert len(mujeres) == 1
    assert mujeres[0]["id"] == "1672"

