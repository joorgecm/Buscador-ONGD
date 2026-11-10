import json

from app.llm.clasificador_ambito import AMBITO_POR_DEFECTO, ClasificadorAmbito
from app.models.ambito import Ambito


class ClienteFalso:
    def __init__(self, respuestas: list[str]) -> None:
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def completar(self, sistema: str, usuario: str) -> str:
        self.llamadas += 1
        return self.respuestas.pop(0)


def _respuesta(*pares: tuple[int, str]) -> str:
    return json.dumps({"clasificacion": [{"id": i, "ambito": a} for i, a in pares]})


def test_clasifica_un_lote_con_una_sola_llamada() -> None:
    cliente = ClienteFalso([_respuesta((0, "MUJER"), (1, "MAYORES"))])
    resultados = ClasificadorAmbito(cliente).clasificar([("A", "Associació"), ("B", None)])

    assert [r.ambito for r in resultados] == [Ambito.MUJER, Ambito.MAYORES]
    assert not any(r.por_defecto for r in resultados)
    assert cliente.llamadas == 1


def test_reintenta_solo_las_entidades_invalidas() -> None:
    cliente = ClienteFalso([_respuesta((0, "MUJER"), (1, "INVENTADO")), _respuesta((1, "MAYORES"))])
    resultados = ClasificadorAmbito(cliente).clasificar([("A", None), ("B", None)])

    assert [r.ambito for r in resultados] == [Ambito.MUJER, Ambito.MAYORES]
    assert cliente.llamadas == 2


def test_usa_valor_por_defecto_tras_un_reintento() -> None:
    cliente = ClienteFalso([_respuesta((0, "INVENTADO")), "no es json"])
    resultado = ClasificadorAmbito(cliente).clasificar([("A", None)])[0]

    assert resultado.ambito == AMBITO_POR_DEFECTO
    assert resultado.por_defecto
    assert resultado.motivo is not None
    assert cliente.llamadas == 2


def test_divide_en_lotes() -> None:
    cliente = ClienteFalso([_respuesta((0, "MUJER"), (1, "MUJER")), _respuesta((2, "MAYORES"))])
    resultados = ClasificadorAmbito(cliente, tamano_lote=2).clasificar(
        [("A", None), ("B", None), ("C", None)]
    )

    assert [r.ambito for r in resultados] == [Ambito.MUJER, Ambito.MUJER, Ambito.MAYORES]
    assert cliente.llamadas == 2
