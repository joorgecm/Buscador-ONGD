"""Esquemas Pydantic para la carga al almacén PostgreSQL y el informe de demo."""

from pydantic import BaseModel, Field

from app.extractors.common import ErrorExtraccion, Fuente, Reparacion


class ResumenFuenteCarga(BaseModel):
    """Resultado de ejecutar y cargar una fuente en el almacén."""

    fuente: Fuente
    extraidas: int = 0
    insertadas: int = 0
    omitidas_duplicado_bd: int = 0
    errores_total: int = 0
    errores_por_tipo: dict[str, int] = Field(default_factory=dict)
    reparaciones_total: int = 0
    errores: list[ErrorExtraccion] = Field(default_factory=list)
    reparaciones: list[Reparacion] = Field(default_factory=list)


class ProvinciaVista(BaseModel):
    """Representación de una provincia almacenada en PostgreSQL."""

    codigo: str
    nombre: str


class LocalidadVista(BaseModel):
    """Representación de una localidad almacenada en PostgreSQL."""

    codigo: int
    nombre: str
    codigo_provincia: str


class EntidadVista(BaseModel):
    """Representación de una entidad almacenada en PostgreSQL."""

    cod_entidad: int
    nombre: str
    ambito: str
    direccion: str | None
    codigo_postal: str | None
    longitud: float | None
    latitud: float | None
    contacto: str | None
    url: str | None
    localidad: str
    codigo_provincia: str
    provincia: str


class EstadoAlmacen(BaseModel):
    """Fotografía del contenido actual del almacén PostgreSQL."""

    total_provincias: int = 0
    total_localidades: int = 0
    total_entidades: int = 0
    entidades_por_ambito: dict[str, int] = Field(default_factory=dict)
    provincias: list[ProvinciaVista] = Field(default_factory=list)
    localidades: list[LocalidadVista] = Field(default_factory=list)
    entidades: list[EntidadVista] = Field(default_factory=list)


class InformeCarga(BaseModel):
    """Informe completo de una ejecución de carga en el almacén."""

    estado_inicial: EstadoAlmacen
    resumenes: list[ResumenFuenteCarga] = Field(default_factory=list)
    estado_final: EstadoAlmacen

    def a_markdown(self) -> str:
        """Genera un informe legible en formato Markdown."""
        lineas: list[str] = [
            "# Informe de Carga al Almacén PostgreSQL (ONGD)",
            "",
            "## 1. Estado de la Base de Datos",
            (
                f"- **Inicial**: {self.estado_inicial.total_provincias} provincias, "
                f"{self.estado_inicial.total_localidades} localidades, "
                f"{self.estado_inicial.total_entidades} entidades"
            ),
            (
                f"- **Final**: {self.estado_final.total_provincias} provincias, "
                f"{self.estado_final.total_localidades} localidades, "
                f"{self.estado_final.total_entidades} entidades"
            ),
            "",
        ]

        if self.resumenes:
            lineas.extend(
                [
                    "## 2. Resumen por Fuente",
                    "| Fuente | Válidas extraídas | Insertadas BD | Omitidas dup. BD | "
                    "Errores | Reparaciones |",
                    "| :--- | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for res in self.resumenes:
                lineas.append(
                    f"| `{res.fuente.value}` | {res.extraidas} | {res.insertadas} | "
                    f"{res.omitidas_duplicado_bd} | {res.errores_total} | "
                    f"{res.reparaciones_total} |"
                )
            lineas.append("")

            for res in self.resumenes:
                lineas.append(f"### Detalle `{res.fuente.value}`")
                if res.errores_por_tipo:
                    desglose = ", ".join(
                        f"`{tipo}`: {cnt}" for tipo, cnt in sorted(res.errores_por_tipo.items())
                    )
                    lineas.append(f"- **Errores por tipo**: {desglose}")
                if res.errores:
                    lineas.append("- **Errores detectados**:")
                    for err in res.errores:
                        fila_txt = f"fila {err.fila}" if err.fila is not None else "archivo"
                        lineas.append(
                            f"  - [{fila_txt}] `{err.campo}` (`{err.tipo.value}`): {err.motivo}"
                        )
                else:
                    lineas.append("- **Errores detectados**: ninguno.")

                if res.reparaciones:
                    lineas.append(f"- **Reparaciones aplicadas ({len(res.reparaciones)})**:")
                    for rep in res.reparaciones:
                        fila_txt = f"fila {rep.fila}" if rep.fila is not None else "archivo"
                        lineas.append(
                            f"  - [{fila_txt}] `{rep.campo}`: "
                            f"`{rep.valor_antes}` -> `{rep.valor_despues}` ({rep.regla})"
                        )
                else:
                    lineas.append("- **Reparaciones aplicadas**: ninguna.")
                lineas.append("")

        lineas.extend(["## 3. Contenido Almacenado en PostgreSQL"])
        if self.estado_final.entidades_por_ambito:
            lineas.append("### Distribución por ámbito")
            for ambito, total in sorted(self.estado_final.entidades_por_ambito.items()):
                lineas.append(f"- `{ambito}`: {total}")
            lineas.append("")

        if self.estado_final.entidades:
            lineas.extend(
                [
                    "### Entidades en `entidad`",
                    "| ID | Nombre | Ámbito | Localidad (Prov) | CP | Coordenadas |",
                    "| ---: | :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for ent in self.estado_final.entidades:
                coords = (
                    f"{ent.latitud:.6f}, {ent.longitud:.6f}"
                    if ent.latitud is not None and ent.longitud is not None
                    else "-"
                )
                cp = ent.codigo_postal or "-"
                lineas.append(
                    f"| {ent.cod_entidad} | {ent.nombre} | `{ent.ambito}` | "
                    f"{ent.localidad} ({ent.codigo_provincia}) | {cp} | {coords} |"
                )
        else:
            lineas.append("_No hay entidades almacenadas en la base de datos._")

        return "\n".join(lineas) + "\n"
