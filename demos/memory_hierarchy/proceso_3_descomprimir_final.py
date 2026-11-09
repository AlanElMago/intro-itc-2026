import mmap
import os
from io import BytesIO
import ram_kax
from config import *
import zipfile

ZIP_ENTRY_NAME = globals().get("ZIP_ENTRY_NAME", "contenido.bin")  

def unzip_bytes(zip_blob: bytes) -> bytes:
    """Extrae bytes del primer elemento o de ZIP_ENTRY_NAME si existe."""
    bio = BytesIO(zip_blob)
    with zipfile.ZipFile(bio, mode="r") as zf:
        names = zf.namelist()
        name = ZIP_ENTRY_NAME if ZIP_ENTRY_NAME in names else (names[0] if names else None)
        if not name:
            raise ValueError("ZIP vacío o corrupto.")
        return zf.read(name)



def process_three_disk(lock, t_transfer):
    """Implementa IPC en DISCO usando mmap."""
    print("P3 (Descomprimir/Final): Iniciando modo DISCO...")

    with lock:
        input_path = os.path.join(SHARED_FOLDER, "comprimido.zip")
        final_output_path = output_path("disco")
        
        try:
            with medir(t_transfer), open(input_path, 'r+b') as f_in:
                mm_in = mmap.mmap(f_in.fileno(), 0)
                zip_blob = mm_in.read()
                mm_in.close()
        except FileNotFoundError:
            print("P3 Error: Archivo 'comprimido.zip' no encontrado. P2 no ha terminado.")
            return

        
        final_data = unzip_bytes(zip_blob)
        
        with open(final_output_path, 'wb') as f_out:
            f_out.write(final_data)

        print(f"P3 (Descomprimir/Final): Proceso completado. Archivo guardado en {final_output_path}")

def process_three_ram(sem_in, t_transfer):
    """IPC en RAM usando kax (SharedMemory local)."""
    print("P3 (Descomprimir/Final): Iniciando modo RAM (kax)...")
    sem_in.acquire()
    try:
        with medir(t_transfer):
            zip_blob = ram_kax.leer(SHM_NAME)
        final_output_path = output_path("ram")
        with open(final_output_path, 'wb') as f_out:
            f_out.write(unzip_bytes(zip_blob))
        print(f"P3 (Descomprimir/Final): Proceso completado. Archivo guardado en {final_output_path}")
    except Exception as e:
        print(f"P3 Error: {e}")


def process_three_cloud(sem_in, t_transfer):
    """IPC en la NUBE: descarga el ZIP de Drive y recupera el archivo."""
    import nube_drive
    print("P3 (Descomprimir/Final): Iniciando modo NUBE (Google Drive)...")
    sem_in.acquire()
    try:
        svc = nube_drive.servicio()
        with medir(t_transfer):
            zip_blob = nube_drive.descargar(svc, ram_kax.leer(SHM_NAME).decode())
        final_output_path = output_path("nube")
        with open(final_output_path, 'wb') as f_out:
            f_out.write(unzip_bytes(zip_blob))
        print(f"P3 (Descomprimir/Final): Proceso completado. Archivo guardado en {final_output_path}")
    except Exception as e:
        print(f"P3 Error: {e}")
