import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self

import httpx
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import BACKEND_DIR, settings

NOMINATIM_UI_SEARCH = "https://nominatim.openstreetmap.org/ui/search.html"
NOMINATIM_UI_REVERSE = "https://nominatim.openstreetmap.org/ui/reverse.html"
NOMINATIM_API_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_API_REVERSE = "https://nominatim.openstreetmap.org/reverse"
CARTOCIUDAD_API_FIND = "https://www.cartociudad.es/geocoder/api/geocoder/find"
CARTOCIUDAD_API_REVERSE = "https://www.cartociudad.es/geocoder/api/geocoder/reverseGeocode"

USER_AGENT = "BuscadorONGD-IEI-UPV/1.0"
_CP_ESP_RE = re.compile(r"\b(?:0[1-9]|[1-4]\d|5[0-2])\d{3}\b")


@dataclass(slots=True)
class DatosGeo:
    codigo_postal: str | None = None
    latitud: float | None = None
    longitud: float | None = None


class GeoScraper(Protocol):
    def geocodificar(
        self,
        *,
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float | None = None,
        longitud: float | None = None,
    ) -> DatosGeo: ...


def limpiar_direccion_busqueda(direccion: str | None) -> str:
    if not direccion:
        return ""
    texto = re.sub(r"\([^)]*\)", " ", direccion)
    reemplazos = (
        (r"\bC/\s*", "Calle "),
        (r"\bCL\.?\s+", "Calle "),
        (r"\bAVDA\.?\s+", "Avenida "),
        (r"\bAV\.?\s+", "Avenida "),
        (r"\bPZA\.?\s+", "Plaza "),
        (r"\bPL\.?\s+", "Plaza "),
        (r"\bPCA\.?\s+", "Plaça "),
        (r"\bCTRA\.?\s+", "Carretera "),
        (r"\bCRTRA\.?\s+", "Carretera "),
        (r"\bPDA\.?\s+", "Partida "),
        (r"\bS/N\b", ""),
        (r"\bBAJO\b", ""),
        (r"\bPTA\.?\s*\w+", ""),
        (r"\bN[ÚU]M\.?\s*", ""),
        (r"\bN[º°.]+\s*", ""),
    )
    for patron, sustituto in reemplazos:
        texto = re.sub(patron, sustituto, texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+,", ",", texto)
    return " ".join(texto.split()).strip(" ,.-")


def extraer_cp_de_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    coincidencias = _CP_ESP_RE.findall(texto)
    return coincidencias[-1] if coincidencias else None


def _limpiar_toponimo(nombre: str) -> str:
    # Para topónimos bilingües como 'València/Valencia' o 'Pinós, el/Pinoso', tomar una forma limpia
    parte = nombre.split("/")[-1].strip()
    if "," in parte:
        trozos = [p.strip() for p in parte.split(",") if p.strip()]
        if len(trozos) == 2 and trozos[1].lower() in {"el", "la", "els", "les", "los", "las"}:
            return f"{trozos[1]} {trozos[0]}"
    return parte


class ScraperGeo:
    def __init__(
        self,
        *,
        cache_path: Path | str | None = None,
        usar_selenium: bool | None = None,
        headless: bool | None = None,
        timeout: float = 10.0,
        min_intervalo_seg: float = 1.0,
    ) -> None:
        ruta = Path(cache_path) if cache_path is not None else settings.GEOCACHE_PATH
        if not ruta.is_absolute():
            ruta = BACKEND_DIR / ruta
        self.cache_path = ruta
        self.usar_selenium = settings.USAR_SELENIUM if usar_selenium is None else usar_selenium
        self.headless = settings.SELENIUM_HEADLESS if headless is None else headless
        self.timeout = timeout
        self.min_intervalo_seg = min_intervalo_seg

        self._driver: WebDriver | None = None
        self._selenium_disponible: bool = True
        self._ultima_peticion_ts: float = 0.0
        self._cache: dict[str, dict[str, Any]] = self._cargar_cache()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            finally:
                self._driver = None

    def _cargar_cache(self) -> dict[str, dict[str, Any]]:
        if not self.cache_path.is_file():
            return {}
        try:
            datos = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return datos if isinstance(datos, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _guardar_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            contenido = json.dumps(self._cache, ensure_ascii=False, indent=2, sort_keys=True)
            self.cache_path.write_text(contenido, encoding="utf-8")
        except OSError:
            pass

    def _respetar_rate_limit(self) -> None:
        restante = self.min_intervalo_seg - (time.monotonic() - self._ultima_peticion_ts)
        if restante > 0:
            time.sleep(restante)
        self._ultima_peticion_ts = time.monotonic()

    @staticmethod
    def _clave_cache(
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float | None,
        longitud: float | None,
    ) -> str:
        if latitud is not None and longitud is not None:
            return f"rev:{latitud:.5f},{longitud:.5f}"
        dir_norm = limpiar_direccion_busqueda(direccion).casefold()
        mun_norm = _limpiar_toponimo(municipio).casefold()
        prov_norm = _limpiar_toponimo(provincia).casefold()
        return f"fwd:{dir_norm}|{mun_norm}|{prov_norm}"

    def geocodificar(
        self,
        *,
        direccion: str | None,
        municipio: str,
        provincia: str,
        latitud: float | None = None,
        longitud: float | None = None,
    ) -> DatosGeo:
        clave = self._clave_cache(direccion, municipio, provincia, latitud, longitud)
        if clave in self._cache:
            entrada = self._cache[clave]
            return DatosGeo(
                codigo_postal=entrada.get("codigo_postal"),
                latitud=entrada.get("latitud"),
                longitud=entrada.get("longitud"),
            )

        resultado = DatosGeo(latitud=latitud, longitud=longitud)

        if latitud is not None and longitud is not None:
            resultado = self._resolver_inversa(latitud, longitud)
        else:
            resultado = self._resolver_directa(direccion, municipio, provincia)

        if resultado.codigo_postal is None and (direccion or municipio):
            respaldo_dir = self._resolver_directa(direccion, municipio, provincia)
            if respaldo_dir.codigo_postal is not None:
                resultado.codigo_postal = respaldo_dir.codigo_postal
            if resultado.latitud is None:
                resultado.latitud = respaldo_dir.latitud
                resultado.longitud = respaldo_dir.longitud

        if resultado.codigo_postal is not None or (
            resultado.latitud is not None and resultado.longitud is not None
        ):
            self._cache[clave] = {
                "codigo_postal": resultado.codigo_postal,
                "latitud": resultado.latitud,
                "longitud": resultado.longitud,
            }
            self._guardar_cache()

        return resultado

    def _obtener_driver(self) -> WebDriver | None:
        if not self.usar_selenium or not self._selenium_disponible:
            return None
        if self._driver is not None:
            return self._driver

        opciones = Options()
        if self.headless:
            opciones.add_argument("--headless=new")
        opciones.add_argument("--no-sandbox")
        opciones.add_argument("--disable-dev-shm-usage")
        opciones.add_argument("--disable-gpu")
        opciones.add_argument("--window-size=1280,800")
        opciones.add_argument(f"--user-agent={USER_AGENT}")

        try:
            self._driver = webdriver.Chrome(options=opciones)
            self._driver.set_page_load_timeout(self.timeout)
            return self._driver
        except WebDriverException:
            self._selenium_disponible = False
            return None

    def _resolver_inversa(self, latitud: float, longitud: float) -> DatosGeo:
        if self.usar_selenium:
            via_selenium = self._inversa_selenium(latitud, longitud)
            if via_selenium.codigo_postal is not None:
                return via_selenium

        via_nominatim = self._inversa_nominatim_http(latitud, longitud)
        if via_nominatim.codigo_postal is not None:
            return via_nominatim

        via_cartociudad = self._inversa_cartociudad_http(latitud, longitud)
        if via_cartociudad.codigo_postal is not None:
            return via_cartociudad

        return DatosGeo(codigo_postal=None, latitud=latitud, longitud=longitud)

    def _resolver_directa(
        self, direccion: str | None, municipio: str, provincia: str
    ) -> DatosGeo:
        mun_limpio = _limpiar_toponimo(municipio)
        prov_limpia = _limpiar_toponimo(provincia)
        dir_limpia = limpiar_direccion_busqueda(direccion)

        consultas: list[str] = []
        if dir_limpia:
            consultas.append(f"{dir_limpia}, {mun_limpio}, {prov_limpia}, España")
        consultas.append(f"{mun_limpio}, {prov_limpia}, España")

        for consulta in consultas:
            if self.usar_selenium:
                via_sel = self._directa_selenium(consulta)
                if via_sel.latitud is not None and via_sel.codigo_postal is not None:
                    return via_sel

            via_nom = self._directa_nominatim_http(consulta)
            if via_nom.latitud is not None and via_nom.codigo_postal is not None:
                return via_nom

            via_cc = self._directa_cartociudad_http(consulta)
            if via_cc.latitud is not None or via_cc.codigo_postal is not None:
                return DatosGeo(
                    codigo_postal=via_cc.codigo_postal or via_nom.codigo_postal,
                    latitud=via_cc.latitud if via_cc.latitud is not None else via_nom.latitud,
                    longitud=via_cc.longitud if via_cc.longitud is not None else via_nom.longitud,
                )

            if via_nom.latitud is not None:
                return via_nom

        return DatosGeo()

    def _inversa_selenium(self, latitud: float, longitud: float) -> DatosGeo:
        driver = self._obtener_driver()
        if driver is None:
            return DatosGeo(latitud=latitud, longitud=longitud)

        try:
            self._respetar_rate_limit()
            driver.get(NOMINATIM_UI_REVERSE)
            wait = WebDriverWait(driver, self.timeout)

            input_lat = wait.until(ec.presence_of_element_located((By.ID, "reverse-lat")))
            input_lon = driver.find_element(By.ID, "reverse-lon")
            boton = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")

            input_lat.clear()
            input_lat.send_keys(f"{latitud:.6f}")
            input_lon.clear()
            input_lon.send_keys(f"{longitud:.6f}")
            boton.click()

            wait.until(
                ec.presence_of_element_located((By.CSS_SELECTOR, "#searchresults .result, #intro"))
            )
            resultados = driver.find_elements(By.CSS_SELECTOR, "#searchresults .result")
            if not resultados:
                return DatosGeo(latitud=latitud, longitud=longitud)

            nombre = resultados[0].find_element(By.CSS_SELECTOR, "span.name").text
            cp = extraer_cp_de_texto(nombre)
            return DatosGeo(codigo_postal=cp, latitud=latitud, longitud=longitud)
        except Exception:
            return DatosGeo(latitud=latitud, longitud=longitud)

    def _directa_selenium(self, consulta: str) -> DatosGeo:
        driver = self._obtener_driver()
        if driver is None:
            return DatosGeo()

        try:
            self._respetar_rate_limit()
            driver.get(NOMINATIM_UI_SEARCH)
            wait = WebDriverWait(driver, self.timeout)

            input_q = wait.until(ec.presence_of_element_located((By.ID, "q")))
            boton = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")

            input_q.clear()
            input_q.send_keys(consulta)
            boton.click()

            wait.until(
                ec.presence_of_element_located(
                    (By.CSS_SELECTOR, "#searchresults .result, .noresults")
                )
            )
            resultados = driver.find_elements(By.CSS_SELECTOR, "#searchresults .result")
            if not resultados:
                return DatosGeo()

            primero = resultados[0]
            nombre = primero.find_element(By.CSS_SELECTOR, "span.name").text
            coords_txt = (
                primero.find_element(By.CSS_SELECTOR, "p.coords").get_attribute("textContent")
                or ""
            )

            lat, lon = self._parsear_coords_ui(coords_txt)
            cp = extraer_cp_de_texto(nombre)
            return DatosGeo(codigo_postal=cp, latitud=lat, longitud=lon)
        except Exception:
            return DatosGeo()

    @staticmethod
    def _parsear_coords_ui(texto: str) -> tuple[float | None, float | None]:
        partes = [p.strip() for p in texto.split(",")]
        if len(partes) != 2:
            return None, None
        try:
            return float(partes[0]), float(partes[1])
        except ValueError:
            return None, None

    def _inversa_nominatim_http(self, latitud: float, longitud: float) -> DatosGeo:
        try:
            self._respetar_rate_limit()
            resp = httpx.get(
                NOMINATIM_API_REVERSE,
                params={
                    "format": "jsonv2",
                    "lat": f"{latitud:.6f}",
                    "lon": f"{longitud:.6f}",
                    "addressdetails": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            cp = extraer_cp_de_texto(
                data.get("address", {}).get("postcode")
            ) or extraer_cp_de_texto(data.get("display_name"))
            return DatosGeo(codigo_postal=cp, latitud=latitud, longitud=longitud)
        except Exception:
            return DatosGeo(latitud=latitud, longitud=longitud)

    def _directa_nominatim_http(self, consulta: str) -> DatosGeo:
        try:
            self._respetar_rate_limit()
            resp = httpx.get(
                NOMINATIM_API_SEARCH,
                params={
                    "format": "jsonv2",
                    "q": consulta,
                    "countrycodes": "es",
                    "addressdetails": 1,
                    "limit": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                return DatosGeo()
            primero = items[0]
            cp = extraer_cp_de_texto(
                primero.get("address", {}).get("postcode")
            ) or extraer_cp_de_texto(primero.get("display_name"))
            lat = float(primero["lat"]) if "lat" in primero else None
            lon = float(primero["lon"]) if "lon" in primero else None
            return DatosGeo(codigo_postal=cp, latitud=lat, longitud=lon)
        except Exception:
            return DatosGeo()

    def _inversa_cartociudad_http(self, latitud: float, longitud: float) -> DatosGeo:
        data = self._peticion_cartociudad(
            CARTOCIUDAD_API_REVERSE, {"lat": f"{latitud:.6f}", "lon": f"{longitud:.6f}"}
        )
        if not isinstance(data, dict):
            return DatosGeo(latitud=latitud, longitud=longitud)
        cp = extraer_cp_de_texto(str(data.get("postalCode") or ""))
        return DatosGeo(codigo_postal=cp, latitud=latitud, longitud=longitud)

    def _directa_cartociudad_http(self, consulta: str) -> DatosGeo:
        data = self._peticion_cartociudad(CARTOCIUDAD_API_FIND, {"q": consulta})
        if not isinstance(data, dict):
            return DatosGeo()
        cp = extraer_cp_de_texto(str(data.get("postalCode") or ""))
        lat = float(data["lat"]) if data.get("lat") is not None else None
        lon = float(data["lng"]) if data.get("lng") is not None else None
        return DatosGeo(codigo_postal=cp, latitud=lat, longitud=lon)

    def _peticion_cartociudad(self, url: str, params: dict[str, str]) -> Any:
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            try:
                resp = httpx.get(
                    url, params=params, headers=headers, timeout=self.timeout, verify=False
                )
                resp.raise_for_status()
                return resp.json()
            except Exception:
                return None
        except Exception:
            return None