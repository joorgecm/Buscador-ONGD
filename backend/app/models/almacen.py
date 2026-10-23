from sqlalchemy import CHAR, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.ambito import Ambito


class Provincia(Base):
    __tablename__ = "provincia"

    codigo: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))

    localidades: Mapped[list["Localidad"]] = relationship(back_populates="provincia")


class Localidad(Base):
    __tablename__ = "localidad"

    codigo: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150))
    codigo_provincia: Mapped[str] = mapped_column(ForeignKey("provincia.codigo"))

    provincia: Mapped[Provincia] = relationship(back_populates="localidades")
    entidades: Mapped[list["Entidad"]] = relationship(back_populates="localidad")


class Entidad(Base):
    __tablename__ = "entidad"

    cod_entidad: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(300))
    ambito: Mapped[Ambito] = mapped_column(Enum(Ambito, name="ambito"))
    direccion: Mapped[str | None] = mapped_column(String(300))
    codigo_postal: Mapped[str | None] = mapped_column(CHAR(5))
    longitud: Mapped[float | None] = mapped_column(Float)
    latitud: Mapped[float | None] = mapped_column(Float)
    descripcion: Mapped[str | None] = mapped_column(Text)
    contacto: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(500))
    codigo_localidad: Mapped[int] = mapped_column(ForeignKey("localidad.codigo"))

    localidad: Mapped[Localidad] = relationship(back_populates="entidades")
