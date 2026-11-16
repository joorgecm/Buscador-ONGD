"""Tests unitarios y de endpoint para el Wrapper de Canarias (wrapperCAN)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR
from app.main import app
from app.wrappers.wrapperCAN import WrapperCAN

MUESTRA_JSON = BACKEND_DIR / "data" / "canarias_sample.json"
COMPLETO_JSON = BACKEND_DIR / "data" / "canarias.json"


def test_wrapper_can_lee_muestra_por_defecto() -> None:
    wrapper = WrapperCAN(MUESTRA_JSON)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 35
    assert entidades[0].fila == 1
    assert entidades[-1].fila == 35

    primera = entidades[0]
    assert primera.numero_registro == "ERE1986CA00001"
    assert primera.denominacion == "Asociacion Adepsi"
    assert primera.direccion_municipio_nombre == "Palmas de Gran Canaria (Las)"
    assert primera.pagina_web == "wwwadepsi.org"


def test_wrapper_can_lee_archivo_completo() -> None:
    wrapper = WrapperCAN(COMPLETO_JSON)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 810


def test_wrapper_can_filtros() -> None:
    wrapper = WrapperCAN(MUESTRA_JSON)

    por_registro = wrapper.obtener_entidades(numero_registro="ERE1986CA00001")
    assert len(por_registro) == 1
    assert por_registro[0].nif == "G35068824"

    por_nif = wrapper.obtener_entidades(nif="g35068824")
    assert len(por_nif) == 1

    por_isla = wrapper.obtener_entidades(isla="Hierro")
    assert len(por_isla) >= 1
    assert all("Hierro" in (e.direccion_isla_nombre or "") for e in por_isla)

    por_area = wrapper.obtener_entidades(area="Mujer")
    assert len(por_area) >= 1
    assert all("Mujer" in (e.area_nombre or "") for e in por_area)


def test_wrapper_can_tolera_tipos_numericos_y_espacios_crudos(tmp_path: Path) -> None:
    archivo = tmp_path / "can_sucio.json"
    datos = [
        {
            "nif": "G35000001",
            "denominacion": "  Entidad Cruda  ",
            "numero_registro": "ERE2026CA00001",
            "direccion_numero": 15,
            "direccion_complemento": "",
            "telefono_1": 928111222,
        }
    ]
    archivo.write_text(json.dumps(datos), encoding="utf-8")

    wrapper = WrapperCAN(archivo)
    entidades = wrapper.obtener_entidades()

    assert len(entidades) == 1
    reg = entidades[0]
    assert reg.fila == 1
    assert reg.denominacion == "  Entidad Cruda  "
    assert reg.direccion_numero == "15"
    assert reg.direccion_complemento is None
    assert reg.telefono_1 == "928111222"


def test_wrapper_can_archivo_inexistente_o_invalido(tmp_path: Path) -> None:
    wrapper_no = WrapperCAN(tmp_path / "no_existe.json")
    with pytest.raises(FileNotFoundError):
        wrapper_no.obtener_entidades()

    roto = tmp_path / "roto.json"
    roto.write_text("{invalido", encoding="utf-8")
    wrapper_roto = WrapperCAN(roto)
    with pytest.raises(ValueError):
        wrapper_roto.obtener_entidades()


def test_endpoint_wrappers_can() -> None:
    client = TestClient(app)

    resp = client.get("/wrappers/can")
    assert resp.status_code == 200
    datos = resp.json()
    assert len(datos) == 35
    assert datos[0]["numero_registro"] == "ERE1986CA00001"

    resp_filtrado = client.get("/wrappers/can", params={"area": "Mujer"})
    assert resp_filtrado.status_code == 200
    mujeres = resp_filtrado.json()
    assert len(mujeres) >= 1
    assert all("Mujer" in (item["area_nombre"] or "") for item in mujeres)

