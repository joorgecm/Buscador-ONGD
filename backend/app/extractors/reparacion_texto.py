import math
import re
from collections import Counter
from collections.abc import Iterable

from app.extractors.catalogo_municipios import CatalogoMunicipios, clave_texto

PARTICULAS: tuple[str, ...] = (
    "a",
    "al",
    "als",
    "amb",
    "con",
    "contra",
    "d'",
    "de",
    "del",
    "dels",
    "el",
    "els",
    "en",
    "i",
    "l'",
    "la",
    "las",
    "les",
    "lo",
    "los",
    "n'",
    "o",
    "para",
    "pel",
    "pels",
    "entre",
    "per",
    "por",
    "que",
    "s'",
    "se",
    "sense",
    "sin",
    "sobre",
    "u",
    "un",
    "una",
    "y",
)

VOCABULARIO_BASE: tuple[str, ...] = (
    "associació",
    "asociación",
    "fundació",
    "fundación",
    "cooperativa",
    "cooperació",
    "cooperación",
    "solidaritat",
    "solidaridad",
    "desenvolupament",
    "desarrollo",
    "federació",
    "federación",
    "entitat",
    "centre",
    "centro",
    "catalunya",
    "cataluña",
    "internacional",
    "carrer",
    "avinguda",
    "plaça",
    "passeig",
    "calle",
    "avenida",
    "plaza",
    "paseo",
    "ronda",
    "travessera",
    "barcelona",
    "girona",
    "lleida",
    "tarragona",
    "sant",
    "santa",
)

SUFIJOS_PEGADOS: tuple[str, ...] = (
    "dels",
    "del",
    "de",
    "les",
    "las",
    "los",
    "els",
    "per",
    "para",
    "amb",
    "sense",
)

SUFIJOS_DOMINIO: tuple[str, ...] = ("info", "coop", "com", "org", "cat", "net", "edu", "eu", "es")

_PIEZA_RE = re.compile(
    r"[A-ZÀ-Ý]{2,}(?![a-zà-ÿ])|[A-ZÀ-Ý]?[a-zà-ÿ·ºª]+['’]?|[A-ZÀ-Ý]|\d+|[^\sA-Za-zÀ-ÿ\d]"
)
_SIN_ESPACIO_ANTES = set(",.;:)]!?-·/%º")
_SIN_ESPACIO_DESPUES = set("([-·/")
_ESQUEMA_RE = re.compile(r"^(?:[A-Za-z]{3,5}://)+")
_ULTIMO_ESQUEMA_RE = re.compile(r"([A-Za-z]{3,5})://(?!.*://)")
_SEPARADOR_CORREOS_RE = re.compile(r"[\s,;]+")
_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$")
_PUNTO_NOMBRE_RE = re.compile(r"(?<=Asso)Carrer|(?<=Aso)Carrer|Carrer$")
_PUNTO_ARTEFACTO_RE = re.compile(r"Carrer(?=[a-z]{2,4}(?:$|/))|(?<=\b[A-Z])Carrer|(?<=Asso)Carrer")


def _es_palabra(pieza: str) -> bool:
    return bool(pieza) and (pieza[0].isalpha() or pieza[0] in "ºª")


class ReparadorTexto:
    def __init__(
        self,
        textos_corpus: Iterable[str] = (),
        catalogo: CatalogoMunicipios | None = None,
    ) -> None:
        conteo: Counter[str] = Counter()
        for texto in textos_corpus:
            for pieza in _PIEZA_RE.findall(texto or ""):
                if pieza.isalpha() and pieza.isupper():
                    continue
                if _es_palabra(pieza) and len(pieza.rstrip("'’")) >= 3:
                    conteo[pieza.lower()] += 1
        self._eliminar_compuestos(conteo)
        for palabra in VOCABULARIO_BASE:
            conteo[palabra] += 20
        if catalogo is not None:
            for municipio in catalogo.municipios:
                for palabra in re.findall(r"[^\s']+'?", municipio.nombre.lower()):
                    if len(palabra) >= 3:
                        conteo[palabra] += 5
        for particula in PARTICULAS:
            conteo[particula.replace("’", "'")] += 800
        self._conteo = conteo
        self._total = sum(conteo.values())
        self._maximo = max((len(p) for p in conteo), default=1)

    @staticmethod
    def _eliminar_compuestos(conteo: Counter[str]) -> None:
        particulas = sorted(
            (p.replace("’", "'") for p in PARTICULAS if len(p.rstrip("'")) >= 2),
            key=len,
            reverse=True,
        )
        base_confiable: set[str] = set()

        def descomponible(texto: str) -> bool:
            if len(texto) >= 5 and texto in base_confiable:
                return True
            for particula in particulas:
                if texto.startswith(particula) and descomponible(texto[len(particula) :]):
                    return True
                if texto.endswith(particula) and descomponible(texto[: -len(particula)]):
                    return True
            return False

        for palabra in sorted(conteo, key=len):
            compuesta = any(
                (palabra.startswith(p) and descomponible(palabra[len(p) :]))
                or (palabra.endswith(p) and descomponible(palabra[: -len(p)]))
                for p in particulas
                if len(palabra) > len(p)
            )
            if compuesta:
                del conteo[palabra]
            else:
                base_confiable.add(palabra)

    def _coste(self, palabra: str) -> float:
        cuenta = self._conteo.get(palabra)
        if cuenta:
            return math.log(self._total / cuenta) + 1.0
        return math.log(self._total) + 3.5 * len(palabra)

    def _segmentar(self, pieza: str) -> list[str]:
        minuscula = pieza.lower().replace("’", "'")
        n = len(minuscula)
        mejor = [0.0] + [math.inf] * n
        origen = [0] * (n + 1)
        for fin in range(1, n + 1):
            for inicio in range(max(0, fin - self._maximo), fin):
                coste = mejor[inicio] + self._coste(minuscula[inicio:fin])
                if coste < mejor[fin]:
                    mejor[fin] = coste
                    origen[fin] = inicio
        trozos: list[str] = []
        fin = n
        while fin > 0:
            inicio = origen[fin]
            trozos.append(pieza[inicio:fin])
            fin = inicio
        trozos.reverse()
        resultado: list[str] = []
        for trozo in trozos:
            resultado.extend(self._separar_sufijos(trozo))
        return resultado

    def _separar_sufijos(self, trozo: str) -> list[str]:
        clave = trozo.lower()
        if len(clave) < 8:
            return [trozo]
        for sufijo in SUFIJOS_PEGADOS:
            if clave.endswith(sufijo) and len(clave) - len(sufijo) >= 6:
                return [*self._separar_sufijos(trozo[: -len(sufijo)]), trozo[-len(sufijo) :]]
        return [trozo]

    def reparar_texto(self, texto: str | None, *, es_nombre: bool = False) -> str | None:
        if texto is None:
            return None
        if es_nombre:
            texto = _PUNTO_NOMBRE_RE.sub(".", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        if not texto:
            return None

        palabras: list[str] = []
        for pieza in _PIEZA_RE.findall(texto):
            if _es_palabra(pieza) and not (pieza.isalpha() and pieza.isupper()):
                palabras.extend(self._segmentar(pieza))
            else:
                palabras.append(pieza)

        resultado = ""
        anterior = ""
        for palabra in palabras:
            if anterior:
                if self._necesita_espacio(anterior, palabra):
                    resultado += " "
            resultado += palabra
            anterior = palabra
        return resultado

    @staticmethod
    def _necesita_espacio(anterior: str, actual: str) -> bool:
        if actual[0] in _SIN_ESPACIO_ANTES or anterior[-1] in _SIN_ESPACIO_DESPUES:
            return False
        if anterior[-1] in "'’":
            return False
        if actual[0].isdigit() and anterior[-1].isdigit():
            return False
        if actual[0].isdigit() and _es_palabra(anterior):
            return len(anterior.rstrip("ºª")) >= 3
        if anterior[-1].isdigit() and _es_palabra(actual):
            return len(actual) > 2
        return True

    @staticmethod
    def _restaurar_dominio(dominio: str) -> str | None:
        dominio = _PUNTO_ARTEFACTO_RE.sub(".", dominio).lower()
        if "." in dominio.strip("."):
            return dominio.strip(".")
        for sufijo in SUFIJOS_DOMINIO:
            if dominio.endswith(sufijo) and len(dominio) > len(sufijo):
                return f"{dominio[: -len(sufijo)]}.{sufijo}"
        return None

    def reparar_email(self, texto: str | None) -> str | None:
        if texto is None or not texto.strip():
            return None
        candidatos = [c for c in _SEPARADOR_CORREOS_RE.split(texto.strip()) if c]
        reparados: list[str] = []
        for candidato in candidatos:
            candidato = re.sub(r"arroba", "@", candidato, flags=re.I)
            if candidato.count("@") != 1:
                return None
            local, dominio = candidato.split("@")
            local = _PUNTO_ARTEFACTO_RE.sub(".", local)
            dominio_reparado = self._restaurar_dominio(dominio)
            if not local or dominio_reparado is None:
                return None
            reparados.append(f"{local}@{dominio_reparado}")
        return " / ".join(reparados) if reparados else None

    def reparar_url(self, texto: str | None) -> str | None:
        if texto is None or not texto.strip():
            return None
        texto = texto.strip()
        ultimo = _ULTIMO_ESQUEMA_RE.search(texto)
        esquema = "https" if ultimo and ultimo.group(1).lower() == "https" else "http"
        resto = _ESQUEMA_RE.sub("", texto)
        host, separador, ruta = resto.partition("/")
        host = host.strip()
        if not host:
            return None
        host_reparado = self._restaurar_dominio(host)
        if host_reparado is None:
            return None
        if host_reparado.startswith("www") and not host_reparado.startswith("www."):
            host_reparado = f"www.{host_reparado[3:]}"
        return f"{esquema}://{host_reparado}{separador}{ruta}"

    @staticmethod
    def email_valido(correo: str | None) -> bool:
        return bool(correo) and all(_CORREO_RE.match(c) for c in correo.split(" / "))

    @staticmethod
    def clave(texto: str | None) -> str:
        return clave_texto(texto)
