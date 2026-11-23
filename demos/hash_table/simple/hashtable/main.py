import logging
import os
import shutil
import tempfile
import time
from typing import Final
from urllib.parse import quote

import httpx
import uvicorn
from fastapi import FastAPI, UploadFile, status
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from hashtable import Location, Storage, StorageType

HOST: Final[str] = os.environ.get('HOST', '0.0.0.0')
PORT: Final[str] = os.environ.get('PORT', '8000')
CLOUD_URL: Final[str] = os.environ.get('CLOUD_URL', 'http://localhost:8001').rstrip('/')
STORAGE_DIR: Final[str] = os.path.abspath('storage')
LOG_DIR: Final[str] = 'logs'


os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level    = logging.INFO,
    format   = '%(asctime)s %(levelname)-7s  %(message)s',
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, 'hash_table.log')),
    ]
)
log = logging.getLogger('hash_table')

app   = FastAPI()
table = Storage(size=512)


def validate_filename(filename: str | None) -> str:
    # Filenames become disk paths and URL segments: allow plain names only.
    if not filename or filename in ('.', '..') or os.path.basename(filename) != filename:
        raise HTTPException(
            status_code = status.HTTP_400_BAD_REQUEST,
            detail      = 'A plain filename (no directories) is required.'
        )

    return filename


def download_headers(filename: str, storage: StorageType) -> dict[str, str]:
    return {
        'Content-Disposition': f"attachment; filename*=utf-8''{quote(filename)}",
        'X-Storage':           storage,
    }


def store_on_disk(filename: str, file: UploadFile) -> Location:
    # Write to a temp file and rename so a failed upload never clobbers an existing copy.
    with tempfile.NamedTemporaryFile(dir=STORAGE_DIR, delete=False) as tmp:
        try:
            shutil.copyfileobj(file.file, tmp)
        except BaseException:
            os.unlink(tmp.name)
            raise

    os.replace(tmp.name, os.path.join(STORAGE_DIR, filename))

    return Location(StorageType.DISK, address=STORAGE_DIR)


def store_in_cloud(filename: str, file: UploadFile) -> Location:
    try:
        response = httpx.post(
            f'{CLOUD_URL}/upload',
            files={'file': (filename, file.file, 'application/octet-stream')}
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code = status.HTTP_502_BAD_GATEWAY,
            detail      = f'Cloud upload failed: {e}'
        )

    return Location(StorageType.CLOUD, address=f'{CLOUD_URL}/download/{quote(filename)}')


@app.post('/files')
def upload(file: UploadFile, storage: StorageType = StorageType.RAM) -> JSONResponse:
    filename = validate_filename(file.filename)

    match storage:
        case StorageType.RAM:
            location = Location(StorageType.RAM, data=file.file.read())
        case StorageType.DISK:
            location = store_on_disk(filename, file)
        case StorageType.CLOUD:
            location = store_in_cloud(filename, file)

    start = time.perf_counter()
    table.write(filename, location)
    log.info(f'table write {filename} (storage={location.storage}) took {(time.perf_counter() - start) * 1e6:.1f} µs')

    return JSONResponse(
        status_code = status.HTTP_201_CREATED,
        content     = {
            'status':   'created',
            'filename': filename,
            'storage':  location.storage,
            'address':  location.address or None,
        }
    )


@app.get('/files/{filename}')
def download(filename: str) -> Response:
    validate_filename(filename)

    start    = time.perf_counter()
    location = table.read(filename)
    log.info(f'table read {filename} (storage={location.storage if location else None}) took {(time.perf_counter() - start) * 1e6:.1f} µs')

    if location is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = f'File {filename} not found.'
        )

    match location.storage:
        case StorageType.RAM:
            return Response(
                content    = location.data,
                media_type = 'application/octet-stream',
                headers    = download_headers(filename, location.storage)
            )

        case StorageType.DISK:
            path = os.path.join(location.address, filename)

            if not os.path.isfile(path):
                raise HTTPException(
                    status_code = status.HTTP_404_NOT_FOUND,
                    detail      = f'File {filename} missing from {location.address}.'
                )

            return FileResponse(
                path       = path,
                media_type = 'application/octet-stream',
                filename   = filename,
                headers    = {'X-Storage': location.storage}
            )

        case StorageType.CLOUD:
            try:
                response = httpx.get(location.address)
                response.raise_for_status()
            except httpx.HTTPError as e:
                raise HTTPException(
                    status_code = status.HTTP_502_BAD_GATEWAY,
                    detail      = f'Cloud download from {location.address} failed: {e}'
                )

            return Response(
                content    = response.content,
                media_type = 'application/octet-stream',
                headers    = download_headers(filename, location.storage)
            )


if __name__ == '__main__':
    # log_config=None: uvicorn's loggers propagate to the root handlers above.
    uvicorn.run(app, host=HOST, port=int(PORT), log_config=None)
