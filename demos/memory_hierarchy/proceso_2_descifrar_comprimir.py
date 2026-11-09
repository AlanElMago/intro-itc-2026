import mmap
import os
from io import BytesIO
import ram_kax
from config import *

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import zipfile

DEFAULT_SALT = b'ipc-demo-salt'
ZIP_ENTRY_NAME = globals().get("ZIP_ENTRY_NAME", "contenido.bin")  

def _derive_aes_key(master_key: bytes, salt: bytes | None = None) -> bytes:
    if salt is None:
        salt = globals().get("SALT", DEFAULT_SALT)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b'ipc-aes-gcm-v1',
    )
    return hkdf.derive(master_key)

def aes_decrypt(blob: bytes, master_key: bytes) -> bytes:
    """Espera b'v1' + nonce(12) + ciphertext||tag."""
    if len(blob) < 2 + 12 + 16:
        raise ValueError("Blob cifrado demasiado corto o corrupto.")
    if blob[:2] != b'v1':
        raise ValueError("Versión de payload no soportada.")
    nonce = blob[2:14]
    ct = blob[14:]
    aes_key = _derive_aes_key(master_key)
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ct, associated_data=None)

def zip_bytes(data: bytes) -> bytes:
    """Crea un ZIP (deflate) en memoria con una sola entrada ZIP_ENTRY_NAME."""
    bio = BytesIO()
    
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(ZIP_ENTRY_NAME, data)
    return bio.getvalue()

# ---------------------------------------------

def process_two_disk(lock, t_transfer):
    """Implementa IPC en DISCO usando mmap."""
    print("P2 (Descifrar/Comprimir): Iniciando modo DISCO...")

    with lock:
        input_path = os.path.join(SHARED_FOLDER, "cifrado.bin")
        output_path = os.path.join(SHARED_FOLDER, "comprimido.zip")
        
        try:
            with medir(t_transfer), open(input_path, 'r+b') as f_in:
                mm_in = mmap.mmap(f_in.fileno(), 0)
                encrypted_data = mm_in.read()
                mm_in.close()
        except FileNotFoundError:
            print("P2 Error: Archivo 'cifrado.bin' no encontrado. P1 no ha terminado.")
            return

        try:
            decrypted_data = aes_decrypt(encrypted_data, KEY)
        except Exception as e:
            print(f"P2 Error de descifrado: {e}")
            return

        
        zip_blob = zip_bytes(decrypted_data)

        with medir(t_transfer):
            with open(output_path, 'wb') as f_out:
                f_out.write(zip_blob)
            with open(output_path, 'r+b') as f:
                mm = mmap.mmap(f.fileno(), 0)
                mm.flush()
                mm.close()

        print(f"P2 (Descifrar/Comprimir): ZIP guardado en {output_path} y sincronizado.")

def process_two_ram(sem_in, sem_out, t_transfer):
    """IPC en RAM usando kax (SharedMemory local)."""
    print("P2 (Descifrar/Comprimir): Iniciando modo RAM (kax)...")
    sem_in.acquire()
    try:
        with medir(t_transfer):
            encrypted_data = ram_kax.leer(SHM_NAME)
        zip_blob = zip_bytes(aes_decrypt(encrypted_data, KEY))
        with medir(t_transfer):
            ram_kax.escribir(SHM_NAME, zip_blob)
        print(f"P2: {len(zip_blob)} bytes (ZIP) escritos en RAM compartida (kax).")
    except Exception as e:
        print(f"P2 Error: {e}")
    finally:
        sem_out.release()


def process_two_cloud(folder_id, sem_in, sem_out, t_transfer):
    """IPC en la NUBE: descarga de Drive, descifra, comprime y vuelve a subir."""
    import nube_drive
    print("P2 (Descifrar/Comprimir): Iniciando modo NUBE (Google Drive)...")
    sem_in.acquire()
    try:
        svc = nube_drive.servicio()
        with medir(t_transfer):
            encrypted_data = nube_drive.descargar(svc, ram_kax.leer(SHM_NAME).decode())
        zip_blob = zip_bytes(aes_decrypt(encrypted_data, KEY))
        with medir(t_transfer):
            file_id = nube_drive.subir(svc, "comprimido.zip", zip_blob, folder_id)
            ram_kax.escribir(SHM_NAME, file_id.encode())
        print(f"P2: {len(zip_blob)} bytes subidos a Drive como comprimido.zip (id {file_id}).")
    except Exception as e:
        print(f"P2 Error: {e}")
    finally:
        sem_out.release()
