"""Tests unitarios y de endpoint para el Wrapper de Catalunya (wrapperCAT)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR
from app.main import app
from app.wrappers.wrapperCAT import WrapperCAT

XML_CAT = BACKEND_DIR / "data" / "Entitats_ONGD_pretty.xml"


def test_wrapper_cat_lee_xml_y_filtra() -> None:
    wrapper = WrapperCAT(XML_CAT)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) > 0
    assert entidades[0].fila == 1

    por_cp = wrapper.obtener_entidades(codigo_postal="08029")
    assert len(por_cp) >= 1
    assert all(e.codi_postal == "08029" for e in por_cp)


def test_wrapper_cat_archivo_inexistente(tmp_path: Path) -> None:
    wrapper = WrapperCAT(tmp_path / "no_existe.xml")
    with pytest.raises(FileNotFoundError):
        wrapper.obtener_entidades()


def test_endpoint_wrappers_cat() -> None:
    client = TestClient(app)

    resp = client.get("/wrappers/cat")
    assert resp.status_code == 200
    datos = resp.json()
    assert len(datos) > 0

    resp_filtrado = client.get("/wrappers/cat", params={"naturaleza": "Fundació"})
    assert resp_filtrado.status_code == 200
    fundaciones = resp_filtrado.json()
    assert len(fundaciones) >= 1
    assert all("fundació" in (item["naturalesa"] or "").casefold() for item in fundaciones)

