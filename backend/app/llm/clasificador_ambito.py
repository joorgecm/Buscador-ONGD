import json
from dataclasses import dataclass
from typing import Any, Protocol

from groq import Groq, GroqError

from app.core.config import settings
from app.models.ambito import Ambito

AMBITO_POR_DEFECTO = Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO

DESCRIPCION_AMBITOS: dict[Ambito, str] = {
    Ambito.MAYORES: "personas mayores, tercera edad",
    Ambito.DISCAPACIDAD: "personas con discapacidad física, intelectual o sensorial",
    Ambito.SALUD_MENTAL: "salud mental y enfermedad mental",
    Ambito.INFANCIA_Y_JUVENTUD: "infancia, menores y juventud",
    Ambito.MUJER: "mujeres, igualdad de género, violencia machista",
    Ambito.MIGRACION: "personas migrantes, refugiadas, asilo, acogida",
    Ambito.INCLUSION_SOCIAL: "exclusión social, pobreza, personas sin hogar, vulnerables",
    Ambito.EDUCACION_Y_FORMACION: "educación, formación, alfabetización, investigación",
    Ambito.EMPLEO_E_INSERCION_LABORAL: "empleo, inserción laboral, economía social",
    Ambito.SALUD_Y_ATENCION_SOCIOSANITARIA: "salud, sanidad, atención sociosanitaria, enfermedades",
    Ambito.VOLUNTARIADO_Y_PARTICIPACION_COMUNITARIA: "voluntariado, participación, cooperación",
    Ambito.CULTURA_Y_DESARROLLO_COMUNITARIO: "cultura, medio ambiente, desarrollo comunitario",
}


@dataclass(slots=True)
class ResultadoAmbito:
    ambito: Ambito
    por_defecto: bool
    motivo: str | None = None


class ClienteChat(Protocol):
    def completar(self, sistema: str, usuario: str) -> str: ...


class ClienteGroq:
    def __init__(self, api_key: str | None = None, modelo: str | None = None) -> None:
        clave = api_key if api_key is not None else settings.GROQ_API_KEY
        if not clave:
            raise ValueError("GROQ_API_KEY no está configurada en el entorno (.env).")
        self._cliente = Groq(api_key=clave)
        self._modelo = modelo or settings.GROQ_MODEL

    def completar(self, sistema: str, usuario: str) -> str:
        respuesta = self._cliente.chat.completions.create(
            model=self._modelo,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
        )
        return respuesta.choices[0].message.content or ""


def _construir_sistema() -> str:
    lineas = "\n".join(f"- {a.value}: {d}" for a, d in DESCRIPCION_AMBITOS.items())
    return (
        "Eres un clasificador de entidades del Tercer Sector de Catalunya. "
        "Para cada entidad elige el ámbito principal de actuación entre estos valores exactos:\n"
        f"{lineas}\n\n"
        'Responde solo con un objeto JSON: {"clasificacion": [{"id": <int>, "ambito": "<VALOR>"}]} '
        "con una entrada por cada entidad recibida y usando únicamente los valores de la lista."
    )


class ClasificadorAmbito:
    def __init__(
        self,
        cliente: ClienteChat | None = None,
        *,
        tamano_lote: int | None = None,
    ) -> None:
        self._cliente = cliente
        self._tamano_lote = tamano_lote or settings.GROQ_TAMANO_LOTE
        self._sistema = _construir_sistema()

    def _obtener_cliente(self) -> ClienteChat:
        if self._cliente is None:
            self._cliente = ClienteGroq()
        return self._cliente

    def clasificar(self, entidades: list[tuple[str, str | None]]) -> list[ResultadoAmbito]:
        resultados: list[ResultadoAmbito | None] = [None] * len(entidades)
        for inicio in range(0, len(entidades), self._tamano_lote):
            indices = list(range(inicio, min(inicio + self._tamano_lote, len(entidades))))
            pendientes = indices
            motivo = "sin respuesta del modelo"
            for _ in range(2):
                validas, motivo = self._consultar(entidades, pendientes)
                for indice, ambito in validas.items():
                    resultados[indice] = ResultadoAmbito(ambito=ambito, por_defecto=False)
                pendientes = [i for i in pendientes if resultados[i] is None]
                if not pendientes:
                    break
            for indice in pendientes:
                resultados[indice] = ResultadoAmbito(
                    ambito=AMBITO_POR_DEFECTO,
                    por_defecto=True,
                    motivo=f"Respuesta no válida tras un reintento ({motivo})",
                )
        return [r for r in resultados if r is not None]

    def _consultar(
        self,
        entidades: list[tuple[str, str | None]],
        indices: list[int],
    ) -> tuple[dict[int, Ambito], str]:
        peticion = [
            {"id": i, "nombre": entidades[i][0], "naturaleza": entidades[i][1] or ""}
            for i in indices
        ]
        try:
            texto = self._obtener_cliente().completar(
                self._sistema, json.dumps(peticion, ensure_ascii=False)
            )
            datos: Any = json.loads(texto)
        except (GroqError, json.JSONDecodeError) as error:
            return {}, f"{type(error).__name__}"

        items = datos.get("clasificacion") if isinstance(datos, dict) else None
        if not isinstance(items, list):
            return {}, "formato de respuesta inesperado"

        validos = set(indices)
        resultado: dict[int, Ambito] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            identificador = item.get("id")
            valor = item.get("ambito")
            if identificador not in validos or not isinstance(valor, str):
                continue
            try:
                resultado[identificador] = Ambito(valor.strip())
            except ValueError:
                continue
        return resultado, "ámbito fuera del enum o entidad omitida"
