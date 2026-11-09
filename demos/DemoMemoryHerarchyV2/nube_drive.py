"""Almacenamiento compartido en la nube usando Google Drive."""
import os
from io import BytesIO

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# drive.file: la app solo ve los archivos que ella misma crea
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = os.environ.get("GDRIVE_CREDENTIALS", "credentials.json")
TOKEN_FILE = os.environ.get("GDRIVE_TOKEN", "token.json")
FOLDER_NAME = os.environ.get("GDRIVE_FOLDER", "DemoMemoryHerarchyV2")


def autenticar():
    """Obtiene credenciales; abre el navegador solo la primera vez. Llamar desde el proceso principal."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # token revocado o caducado (apps en modo "Prueba" caducan a los 7 días)
    if not (creds and creds.valid):
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"Falta '{CREDENTIALS_FILE}'. Descárgalo desde Google Cloud Console "
                "(OAuth client ID de tipo 'Desktop app')."
            )
        creds = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES).run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds


def servicio():
    # cada proceso construye su propio cliente: el cliente HTTP no es seguro entre procesos
    return build("drive", "v3", credentials=autenticar(), cache_discovery=False)


def carpeta_id(svc) -> str:
    """Busca (o crea) la carpeta de la demo en Drive."""
    q = (f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    found = svc.files().list(q=q, fields="files(id)", spaces="drive").execute().get("files", [])
    if found:
        return found[0]["id"]
    meta = {"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}
    return svc.files().create(body=meta, fields="id").execute()["id"]


def subir(svc, nombre: str, data: bytes, folder_id: str) -> str:
    media = MediaIoBaseUpload(BytesIO(data), mimetype="application/octet-stream", resumable=True)
    meta = {"name": nombre, "parents": [folder_id]}
    return svc.files().create(body=meta, media_body=media, fields="id").execute()["id"]


def descargar(svc, file_id: str) -> bytes:
    bio = BytesIO()
    downloader = MediaIoBaseDownload(bio, svc.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return bio.getvalue()
