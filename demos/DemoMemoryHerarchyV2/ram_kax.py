"""Memoria compartida en RAM a través de la biblioteca kax."""
import base64
from kax import Kax

kax = Kax()  # solo se usan las operaciones locales de SHM; no requiere servidor ESS


def crear(nombre: str, tamano: int):
    kax.makeShm(nombre, tamano)


def escribir(nombre: str, data: bytes):
    # kax guarda texto (str.encode), por eso los bytes viajan en base64
    kax.putDataToShm(nombre, base64.b64encode(data).decode())


def leer(nombre: str) -> bytes:
    texto = kax.getDataFromShm(nombre)
    if texto is None:
        raise FileNotFoundError(f"Segmento SHM '{nombre}' no existe.")
    # kax devuelve el buffer completo; el relleno son ceros
    return base64.b64decode(texto.rstrip("\x00"))


def eliminar(nombre: str):
    kax.removeShm(nombre)
