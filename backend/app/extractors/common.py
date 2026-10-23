import enum

from pydantic import BaseModel, Field

from app.models.ambito import Ambito


class Fuente(enum.Enum):
    CV = "CV"
    CAT = "CAT"
    CAN = "CAN"


class TipoError(enum.Enum):
    FORMATO = "formato"
    NULO = "nulo"
    FUERA_DE_RANGO = "fuera_de_rango"
    DUPLICADO = "duplicado"
    SEMANTICO = "semantico"


class EntidadExtraida(BaseModel):
    nombre: str
    ambito: Ambito
    direccion: str | None = None
    codigo_postal: str | None = None
    longitud: float | None = None
    latitud: float | None = None
    descripcion: str | None = None
    contacto: str | None = None
    url: str | None = None
    nombre_localidad: str
    codigo_provincia: str
    nombre_provincia: str


class ErrorExtraccion(BaseModel):
    fuente: Fuente
    fila: int | None
    campo: str
    tipo: TipoError
    motivo: str


class Reparacion(BaseModel):
    fuente: Fuente
    fila: int | None
    campo: str
    valor_antes: str | None
    valor_despues: str | None
    regla: str


class ResultadoExtraccion(BaseModel):
    fuente: Fuente
    entidades: list[EntidadExtraida] = Field(default_factory=list)
    errores: list[ErrorExtraccion] = Field(default_factory=list)
    reparaciones: list[Reparacion] = Field(default_factory=list)

    def error(self, fila: int | None, campo: str, tipo: TipoError, motivo: str) -> None:
        self.errores.append(
            ErrorExtraccion(fuente=self.fuente, fila=fila, campo=campo, tipo=tipo, motivo=motivo)
        )

    def reparacion(
        self,
        fila: int | None,
        campo: str,
        valor_antes: str | None,
        valor_despues: str | None,
        regla: str,
    ) -> None:
        self.reparaciones.append(
            Reparacion(
                fuente=self.fuente,
                fila=fila,
                campo=campo,
                valor_antes=valor_antes,
                valor_despues=valor_despues,
                regla=regla,
            )
        )
