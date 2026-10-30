"""Scraper con Selenium (Chrome headless), pyproj y respaldos (CartoCiudad/Nominatim)."""

from app.scraper.geocoder import DatosGeo, GeoScraper, ScraperGeo

__all__ = ["DatosGeo", "GeoScraper", "ScraperGeo"]
