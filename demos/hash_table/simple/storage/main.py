import logging
import os
from typing import Final

import uvicorn
from fastapi import FastAPI, UploadFile, status
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse

HOST: Final[str] = os.environ.get('HOST', '0.0.0.0')
PORT: Final[str] = os.environ.get('PORT', '8000')
FILES_DIR: Final[str] = 'files'
LOG_DIR:   Final[str] = 'logs'




os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level    = logging.INFO,
    format   = '%(asctime)s %(levelname)-8s  %(message)s',
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, 'simple_storage.log')),
    ]
)

app = FastAPI()




@app.get('/health')
def health() -> JSONResponse:
    return JSONResponse(
        status_code = status.HTTP_200_OK,
        content     = {'status': 'ok'}
    )

@app.post('/upload')
def upload(file: UploadFile) -> JSONResponse:
    if not file.filename:
        return JSONResponse(
            status_code = status.HTTP_400_BAD_REQUEST,
            content     = {
                'status': 'bad_request',
                'message': 'Filename is required for file upload.'
            }
        )

    file_path = os.path.join(FILES_DIR, file.filename)

    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    return JSONResponse(
        status_code = status.HTTP_201_CREATED,
        content     = {
            'status':  'created',
            'message': f'File {file.filename} uploaded successfully.'
        }
    )

@app.get('/download/{filename}')
def download(filename: str) -> FileResponse:
    file_path = os.path.join(FILES_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail      = f'File {filename} not found.'
        )

    return FileResponse(
        path         = file_path,
        media_type   = 'application/octet-stream',
        filename     = filename
    )




if __name__ == '__main__':
    uvicorn.run(app, host=HOST, port=int(PORT), log_config=None)
