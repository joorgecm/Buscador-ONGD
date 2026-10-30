from pathlib import Path
from unittest.mock import patch

from app.scraper.geocoder import (
    DatosGeo,
    ScraperGeo,
    extraer_cp_de_texto,
    limpiar_direccion_busqueda,
)


def test_limpiar_direccion_busqueda() -> None:
    assert limpiar_direccion_busqueda("BUEN CONSEJO, 6, BAJO") == "BUEN CONSEJO, 6"
    assert (
        limpiar_direccion_busqueda("C/SAN JUAN DE DIOS, 7 PTA.19")
        == "Calle SAN JUAN DE DIOS, 7"
    )
    assert (
        limpiar_direccion_busqueda("Avda de Jubalcoy, n.º 34 (Centro Social Altabix)")
        == "Avenida de Jubalcoy, 34"
    )
    assert limpiar_direccion_busqueda("C/ Pintor Sorolla. núm. 28") == "Calle Pintor Sorolla. 28"


def test_extraer_cp_de_texto() -> None:
    texto = (
        "5, Carrer del Mestre Segarra, Benicàssim / Benicasim, "
        "la Plana Alta, Castelló / Castellón, Comunitat Valenciana, 12560, España"
    )
    assert extraer_cp_de_texto(texto) == "12560"
    assert extraer_cp_de_texto("Sin codigo postal") is None
    assert extraer_cp_de_texto("99999 fuera de rango español") is None


def test_scraper_cache_lectura_y_escritura(tmp_path: Path) -> None:
    cache_file = tmp_path / "geocache.json"
    scraper = ScraperGeo(cache_path=cache_file, usar_selenium=False, min_intervalo_seg=0.0)

    with patch.object(
        scraper,
        "_inversa_nominatim_http",
        return_value=DatosGeo(codigo_postal="46900", latitud=39.437, longitud=-0.465),
    ) as mock_nom:
        res1 = scraper.geocodificar(
            direccion="BUEN CONSEJO, 6",
            municipio="Torrent",
            provincia="València/Valencia",
            latitud=39.437,
            longitud=-0.465,
        )
        assert res1.codigo_postal == "46900"
        assert mock_nom.call_count == 1
        assert cache_file.is_file()

        res2 = scraper.geocodificar(
            direccion="BUEN CONSEJO, 6",
            municipio="Torrent",
            provincia="València/Valencia",
            latitud=39.437,
            longitud=-0.465,
        )
        assert res2.codigo_postal == "46900"
        assert mock_nom.call_count == 1


def test_scraper_directa_respaldo_http(tmp_path: Path) -> None:
    cache_file = tmp_path / "geocache.json"
    scraper = ScraperGeo(cache_path=cache_file, usar_selenium=False, min_intervalo_seg=0.0)

    with patch.object(
        scraper,
        "_directa_nominatim_http",
        return_value=DatosGeo(codigo_postal="03202", latitud=38.2699, longitud=-0.7126),
    ):
        res = scraper.geocodificar(
            direccion="Avda de Jubalcoy, 34",
            municipio="Elx/Elche",
            provincia="Alacant/Alicante",
        )
        assert res.codigo_postal == "03202"
        assert res.latitud == 38.2699
        assert res.longitud == -0.7126
