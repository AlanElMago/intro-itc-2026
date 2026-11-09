import os
import time
from contextlib import contextmanager

DEFAULT_INPUT = "input/documento_secreto.txt"
# Otro archivo de entrada: DEMO_INPUT=images.zip python main.py ram
INPUT_FILE = os.environ.get("DEMO_INPUT", DEFAULT_INPUT)
OUTPUT_DIR = "output_final/"
SHARED_FOLDER = "shared_disk_memory/" 

KEY = b'Sixteen byte key' 
BUFFER_SIZE = 1024 * 1024 
SHM_NAME = "mi_demo_shm" 

os.makedirs("input", exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SHARED_FOLDER, exist_ok=True)

if INPUT_FILE == DEFAULT_INPUT and not os.path.exists(INPUT_FILE):
    with open(INPUT_FILE, "w") as f:
        f.write("Este es el contenido secreto que pasará por tres procesos. " * 50)
    print(f" Archivo de entrada creado: {INPUT_FILE}")

if not os.path.exists(INPUT_FILE):
    raise SystemExit(f"No existe el archivo de entrada '{INPUT_FILE}'. Revisa la variable DEMO_INPUT.")


@contextmanager
def medir(t_transfer):
    """Suma al contador compartido (multiprocessing.Value) el tiempo del bloque: solo transferencias."""
    inicio = time.perf_counter()
    try:
        yield
    finally:
        with t_transfer.get_lock():
            t_transfer.value += time.perf_counter() - inicio


def output_path(modo):
    """Ruta de salida con la misma extensión que la entrada (p. ej. .txt o .zip)."""
    return os.path.join(OUTPUT_DIR, f"archivo_recuperado_{modo}{os.path.splitext(INPUT_FILE)[1]}")