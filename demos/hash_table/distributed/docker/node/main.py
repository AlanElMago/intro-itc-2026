import asyncio
import logging.config
import os
import socket
from collections.abc import Generator
from dataclasses import asdict
from pathlib import Path
from typing import Final

import httpx
import mylogging
import uvicorn
from chord import hashfunc
from dht import DistributedHashTable
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse

HOSTNAME: Final[str] = socket.gethostname()
HOST:     Final[str] = socket.gethostbyname(HOSTNAME)
API_PORT: Final[str] = os.environ.get('API_PORT', '43000')
ADDRESS:  Final[str] = f'{HOST}:{API_PORT}'

FILE_STREAM_CHUNK_SIZE: Final[int] = 8192




logging.config.dictConfig(mylogging.CONFIG)

kv = {}
for file in [f for f in Path('files').iterdir() if f.is_file]:
    kv[file.name] = ADDRESS

app = FastAPI()
log = logging.getLogger('api')
dht = asyncio.run(
    DistributedHashTable.build(initial_kv=kv, frontend_address=ADDRESS))




def file_iterator(filepath: Path) -> Generator[bytes, None, None]:
    '''Generator that yields chunks of a file for streaming responses.'''
    with open(filepath, 'rb') as f:
        while chunk := f.read(FILE_STREAM_CHUNK_SIZE):
            yield chunk




@app.get('/health')
def health() -> JSONResponse:
    '''
    Health check endpoint.
    '''
    content = {'status': 'ok'}

    return JSONResponse(content, status.HTTP_200_OK)




@app.get('/debug')
def info() -> JSONResponse:
    '''Debug information endpoint.'''
    successor = {
        'id':               dht._chord.node.successor.id,
        'chord_address':    dht._chord.node.successor.chord_address,
        'frontend_address': dht._chord.node.successor.frontend_address
    }
    predecessor = {
        'id':               dht._chord.node.predecessor.id,
        'chord_address':    dht._chord.node.predecessor.chord_address,
        'frontend_address': dht._chord.node.predecessor.frontend_address
    } if dht._chord.node.predecessor is not None else {}

    content = {
        'hostname':         dht._chord.hostname,
        'id':               dht._chord.node.id,
        'chord_address':    dht._chord.node.chord_address,
        'frontend_address': dht._chord.node.frontend_address,
        'modulo':           dht._chord.modulo,
        'successor':        successor,
        'predecessor':      predecessor,
    }

    return JSONResponse(content, status.HTTP_200_OK)

@app.get('/debug/fingers')
def info_fingers() -> JSONResponse:
    '''Debug information endpoint for the finger table.'''
    content = {
        str(idx): {
            'id':      node.id,
            'address': node.chord_address,
        } for idx, node in enumerate(dht._chord.node._fingers)
    }

    return JSONResponse(content, status.HTTP_200_OK)

@app.get('/debug/dht')
def info_dht() -> JSONResponse:
    '''Debug information endpoint for the distributed hash table.'''
    content = {
        'kv': {
            k: v + f' id={hashfunc(k.encode())}' for k, v in dht._kv.items()
        },
        'self_logs': [{
            'action': log.action.name,
            'record': asdict(log.record)
        } for log in dht._self_logs[-5:]],
        'pred_logs': [{
            'action': log.action.name,
            'record': asdict(log.record)
        } for log in dht._pred_logs[-5:]]
    }

    return JSONResponse(content, status.HTTP_200_OK)




@app.get('/file/{filename}')
def get_file(filename: str) -> StreamingResponse:
    address   = asyncio.run(dht.get(filename))
    not_found = HTTPException(
        status.HTTP_404_NOT_FOUND, f'File {filename} not found')

    if address is None:
        raise not_found

    if address == ADDRESS:
        filepath = Path('files') / filename

        if not filepath.exists():
            raise not_found

        return StreamingResponse(
            content     = file_iterator(filepath),
            status_code = status.HTTP_200_OK,
        )

    url = f'http://{address}/file/{filename}'

    try:
        with httpx.Client() as c, c.stream('GET', url) as response:
            if response.status_code == status.HTTP_404_NOT_FOUND:
                raise not_found

            return StreamingResponse(
                content     = response.aiter_raw(FILE_STREAM_CHUNK_SIZE),
                status_code = response.status_code,
            )
    except httpx.RequestError as e:
        detail = f'Error forwarding request to {url}'

        log.error(f'{detail}: {e}')

        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail)




def main() -> None:
    app.include_router(dht.router)
    app.add_middleware(
        mylogging.AccessLog, log=logging.getLogger('api.access'))

    dht.serve()

    log.info(f'API running on port {API_PORT}')

    uvicorn.run(
        app        = app,
        host       = '0.0.0.0',
        port       = int(API_PORT),
        log_config = None,
        access_log = False
    )

    log.info('API shutting down')

    dht.shutdown()

if __name__ == '__main__':
    main()
