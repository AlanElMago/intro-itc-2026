import mmap
import os
import ram_kax
from config import *


from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


DEFAULT_SALT = b'ipc-demo-salt'  

def _derive_aes_key(master_key: bytes, salt: bytes | None = None) -> bytes:
    """Deriva una clave de 32 bytes (AES-256) desde KEY usando HKDF-SHA256."""
    if salt is None:
        salt = globals().get("SALT", DEFAULT_SALT)
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b'ipc-aes-gcm-v1',
    )
    return hkdf.derive(master_key)

def aes_encrypt(data: bytes, master_key: bytes) -> bytes:
    """Cifra con AES-GCM. Empaqueta como b'v1' + nonce(12) + ciphertext||tag."""
    aes_key = _derive_aes_key(master_key)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)  
    ct = aesgcm.encrypt(nonce, data, associated_data=None)
    return b'v1' + nonce + ct



def process_one_disk(lock, t_transfer):
    """Implementa IPC en DISCO usando mmap."""
    print("P1 (Cifrar): Iniciando modo DISCO...")
    
    
    with open(INPUT_FILE, 'rb') as f:
        original_data = f.read()
    
    
    encrypted_data = aes_encrypt(original_data, KEY)
    
    
    with lock:  
        temp_file_path = os.path.join(SHARED_FOLDER, "cifrado.bin")
        with medir(t_transfer):
            with open(temp_file_path, 'wb') as f:
                f.write(encrypted_data)
            with open(temp_file_path, 'r+b') as f:
                mm = mmap.mmap(f.fileno(), 0)
                mm.flush()
                mm.close()
             
        print(f"P1 (Cifrar): Archivo cifrado guardado en {temp_file_path} y sincronizado.")

def process_one_ram(sem_out, t_transfer):
    """IPC en RAM usando kax (SharedMemory local)."""
    print("P1 (Cifrar): Iniciando modo RAM (kax)...")
    try:
        with open(INPUT_FILE, 'rb') as f:
            encrypted_data = aes_encrypt(f.read(), KEY)
        with medir(t_transfer):
            ram_kax.escribir(SHM_NAME, encrypted_data)
        print(f"P1 (Cifrar): {len(encrypted_data)} bytes cifrados escritos en RAM compartida (kax).")
    except Exception as e:
        print(f"P1 Error: {e}")
    finally:
        sem_out.release()  # siempre avisar, para que P2 no quede bloqueado si P1 falla


def process_one_cloud(folder_id, sem_out, t_transfer):
    """IPC en la NUBE: sube el cifrado a Google Drive y pasa su ID por RAM (kax)."""
    import nube_drive
    print("P1 (Cifrar): Iniciando modo NUBE (Google Drive)...")
    try:
        with open(INPUT_FILE, 'rb') as f:
            encrypted_data = aes_encrypt(f.read(), KEY)
        svc = nube_drive.servicio()
        with medir(t_transfer):
            file_id = nube_drive.subir(svc, "cifrado.bin", encrypted_data, folder_id)
            ram_kax.escribir(SHM_NAME, file_id.encode())
        print(f"P1 (Cifrar): {len(encrypted_data)} bytes subidos a Drive como cifrado.bin (id {file_id}).")
    except Exception as e:
        print(f"P1 Error: {e}")
    finally:
        sem_out.release()
