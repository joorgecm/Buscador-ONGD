"""Wrappers por fuente (CV, CAT, CAN) sobre los archivos originales de datos."""

from app.wrappers.wrapperCAN import WrapperCAN
from app.wrappers.wrapperCAT import WrapperCAT
from app.wrappers.wrapperCV import WrapperCV

__all__ = ["WrapperCAN", "WrapperCAT", "WrapperCV"]
