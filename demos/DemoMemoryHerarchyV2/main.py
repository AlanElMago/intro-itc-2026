# main.py
import os
import sys
import time
import statistics
from multiprocessing import Process, Lock, Semaphore, Value
from config import *
import ram_kax
from proceso_1_cifrar import process_one_disk, process_one_ram, process_one_cloud
from proceso_2_descifrar_comprimir import process_two_disk, process_two_ram, process_two_cloud
from proceso_3_descomprimir_final import process_three_disk, process_three_ram, process_three_cloud

# Tamaño del segmento de RAM compartida, según el archivo de entrada.
# kax guarda texto, así que los datos viajan en base64 (+33%); +1 MB de margen
# para la cabecera del cifrado y del ZIP.
SHM_MAX_SIZE = (os.path.getsize(INPUT_FILE) + 1024 * 1024) * 4 // 3 + 4


def run_disk_demo():
    """Ejecuta la demo con memoria compartida en DISCO (mmap a archivo)."""
    print("\n" + "="*50)
    print(" DEMO: MEMORIA COMPARTIDA EN DISCO (mmap a Archivo)")
    print("="*50)

    lock = Lock()
    t_transfer = Value('d', 0.0)
    start_time = time.time()
    # Secuencial: la transferencia se da a través del disco
    for target in (process_one_disk, process_two_disk, process_three_disk):
        p = Process(target=target, args=(lock, t_transfer))
        p.start()
        p.join()

    elapsed = time.time() - start_time
    print(f"\n Demo en Disco finalizada en {elapsed:.4f} s (transferencias: {t_transfer.value:.4f} s).")
    return elapsed, t_transfer.value


def _run_pipeline(titulo, procesos):
    """Crea el segmento SHM con kax, lanza los 3 procesos a la vez y limpia al final."""
    print("\n" + "="*50)
    print(f" DEMO: {titulo}")
    print("="*50)

    ram_kax.crear(SHM_NAME, SHM_MAX_SIZE)
    print(f"Segmento de RAM Compartida creado con kax: {SHM_NAME} ({SHM_MAX_SIZE / 1024 / 1024:.1f} MB)")
    try:
        t_transfer = Value('d', 0.0)
        start_time = time.time()
        ps = [Process(target=t, args=a + (t_transfer,)) for t, a in procesos]
        # Arrancan simultáneamente y se bloquean en los semáforos
        for p in ps:
            p.start()
        for p in ps:
            p.join()
        elapsed = time.time() - start_time
        print(f"\n {titulo} finalizada en {elapsed:.4f} s (transferencias: {t_transfer.value:.4f} s).")
        return elapsed, t_transfer.value
    finally:
        ram_kax.eliminar(SHM_NAME)
        print("Segmento de RAM Compartida eliminado.")


def run_ram_demo():
    """Memoria compartida en RAM gestionada con kax."""
    sem_encrypted, sem_compressed = Semaphore(0), Semaphore(0)
    return _run_pipeline("MEMORIA COMPARTIDA EN RAM (kax)", [
        (process_one_ram, (sem_encrypted,)),
        (process_two_ram, (sem_encrypted, sem_compressed)),
        (process_three_ram, (sem_compressed,)),
    ])


def run_cloud_demo():
    """Datos en Google Drive; los IDs de archivo se pasan entre procesos por RAM (kax)."""
    import nube_drive
    # Autenticar aquí, en el proceso principal: el flujo OAuth abre el navegador una sola vez
    folder_id = nube_drive.carpeta_id(nube_drive.servicio())
    print(f"Carpeta de Drive: {nube_drive.FOLDER_NAME} (id {folder_id})")

    sem_encrypted, sem_compressed = Semaphore(0), Semaphore(0)
    return _run_pipeline("MEMORIA COMPARTIDA EN LA NUBE (Google Drive)", [
        (process_one_cloud, (folder_id, sem_encrypted)),
        (process_two_cloud, (folder_id, sem_encrypted, sem_compressed)),
        (process_three_cloud, (sem_compressed,)),
    ])


if __name__ == "__main__":
    modos = {"disco": run_disk_demo, "ram": run_ram_demo, "nube": run_cloud_demo}
    try:
        modo = sys.argv[1].lower()
        repeticiones = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        if modo not in modos or repeticiones < 1:
            raise ValueError
    except (IndexError, ValueError):
        print("Uso: python main.py <disco|ram|nube> [repeticiones>=1, por defecto 1]")
        sys.exit(1)

    totales, transferencias = zip(*(modos[modo]() for _ in range(repeticiones)))

    print("\n" + "="*50)
    print(f" RESUMEN modo '{modo}': {repeticiones} repeticion(es)")
    print(f"   {'':15} {'Media':>10} {'Mediana':>10}")
    for nombre, ts in (("Transferencias", transferencias), ("Total", totales)):
        print(f"   {nombre:15} {statistics.mean(ts):>9.4f}s {statistics.median(ts):>9.4f}s")
    print("="*50)
