import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Final

import httpx
import logger
import uvicorn
from chord_protocol import Chord
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

HOSTNAME:  Final[str] = socket.gethostname()
IP_ADDR:   Final[str] = socket.gethostbyname(HOSTNAME)
PORT:      Final[str] = os.getenv('PORT', '42000')
JOIN_ADDR: Final[str] = os.getenv('JOIN_ADDR', f'{IP_ADDR}:{PORT}')
HASH_ALG:  Final[str] = os.getenv('HASH_ALG', 'sha1')
NUM_BITS:  Final[int] = 16  # hashing_algorithm().digest_size * 8

log   = logging.getLogger('uvicorn.main')
chord = Chord.build(
    ip_addr  = IP_ADDR,
    port     = PORT,
    num_bits = NUM_BITS,
    hash_alg = HASH_ALG
)


async def maintenance_loop(client: httpx.AsyncClient) -> None:
    while True:
        try:
            await chord.check_predecessor(client)
            await chord.stabilize(client)
            await chord.fix_fingers(client)
        except httpx.HTTPError as e:
            log.warning(f'maintenence failed: {e!r}')

        await asyncio.sleep(5.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(
        timeout = httpx.Timeout(timeout=2.0, connect=1.0),
        limits  = httpx.Limits(
            max_connections           = NUM_BITS * 2,
            max_keepalive_connections = NUM_BITS
        )
    ) as client:
        app.state.http = client
        await chord.join_ring(address=JOIN_ADDR, client=client)
        task = asyncio.create_task(maintenance_loop(client))
        log.info(f'server listening on port {PORT}')

        yield

        log.info('server shutting down...')
        task.cancel()
        # await chord.leave_ring(client)

app = FastAPI(lifespan=lifespan)


@app.get('/health')
def health() -> JSONResponse:
    return JSONResponse(
        status_code = status.HTTP_200_OK,
        content     = {'status': 'ok'}
    )


@app.get('/info')
def info() -> JSONResponse:
    pred = '' if chord.predecessor is None else asdict(chord.predecessor)

    return JSONResponse(
        status_code = status.HTTP_200_OK,
        content     = {
            'hostname':    HOSTNAME,
            'id':          chord.id,
            'address':     chord.address,
            'modulo':      2**NUM_BITS,
            'predecessor': pred,
            'successor':   asdict(chord.successor)
        }
    )


@app.get('/info/fingers')
def info_fingers() -> JSONResponse:
    return JSONResponse(
        status_code = status.HTTP_200_OK,
        content     = {
            str(idx): {
                'start': finger.start,
                'end':   finger.end,
                'node':  asdict(finger.node)
            } for idx, finger in enumerate(chord._fingers)
        }
    )


@app.get('/chord/predecessor')
def predecessor() -> JSONResponse:
    pred = '' if chord.predecessor is None else asdict(chord.predecessor)

    return JSONResponse(status_code=status.HTTP_200_OK, content=pred)

@app.get('/chord/successor')
def successor() -> JSONResponse:
    node = chord.successor

    return JSONResponse(status_code=status.HTTP_200_OK, content=asdict(node))

@app.get('/chord/closest-preceding-finger/{target_id}')
def closest_preceding_finger(target_id: int) -> JSONResponse:
    node = chord.closest_preceding_finger(target_id)

    return JSONResponse(status_code=status.HTTP_200_OK, content=asdict(node))

@app.get('/chord/find-successor/{target_id}')
async def find_successor(target_id: int, req: Request) -> JSONResponse:
    node = await chord.find_successor(target_id, client=req.app.state.http)

    return JSONResponse(status_code=status.HTTP_200_OK, content=asdict(node))

@app.put('/chord/notify')
async def notify(req: Request) -> JSONResponse:
    body = await req.json()
    chord.notify(address=body['address'])

    return JSONResponse(
        status_code = status.HTTP_200_OK,
        content     = {'status': 'ok'}
    )


if __name__ == '__main__':
    uvicorn.run(
        app        = app,
        host       = '0.0.0.0',
        port       = int(PORT),
        log_config = logger.config
    )
