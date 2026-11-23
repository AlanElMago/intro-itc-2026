import asyncio
import logging
import os
import threading
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Final

import httpx
from chord import Chord, hashfunc
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

JOIN_ADDR: Final[str | None] = os.environ.get('JOIN_ADDR')
HTTP_TIMEOUT: Final[httpx.Timeout] = httpx.Timeout(timeout=1.0)




log = logging.getLogger('api')




async def request(method: str, url: str, **kwargs) -> httpx.Response:
    '''Send an HTTP request with a client bound to the running event loop.'''
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await client.request(method, url, **kwargs)




class KvAction(Enum):
    '''Enum for key-value actions in the distributed hash table.'''
    ADD = 0
    DEL = 1

@dataclass(frozen=True)
class KvRecord:
    '''Dataclass for a key-value record in the distributed hash table.'''
    key:   str
    value: str

@dataclass(frozen=True)
class LogRecord:
    '''Dataclass for a log record in the distributed hash table.'''
    action: KvAction
    record: KvRecord

class Value(BaseModel):
    '''Pydantic model for a value in the distributed hash table.'''
    value: str




class DistributedHashTable:
    '''Class representing a distributed hash table using the Chord protocol.'''
    _chord:     Chord
    _router:    APIRouter
    _kv:        dict[str, str]
    _self_logs: list[LogRecord]
    _pred_logs: list[LogRecord]

    @property
    def router(self) -> APIRouter:
        '''Get the FastAPI router for the distributed hash table.'''
        return self._router

    async def get(self, key: str) -> str | None:
        '''Get the value for a given key from the distributed hash table.

        Args:
            key: The key to retrieve the value for.

        Returns:
            The value associated with the key, or None if the key is not found.
        '''
        id = hashfunc(key.encode())

        if self._chord.node.in_range(id):
            return self._kv.get(key)

        node = self._chord.node.find_successor(id)
        url  = f'http://{node.frontend_address}/key/{key}'

        try:
            res  = await request('GET', url)
            body = res.json()
        except httpx.HTTPError:
            log.error(f'Failed to get key {key} from {node.frontend_address}')

            return None

        return body['value']

    async def put(self, key: str, value: str) -> None:
        '''Put a key-value pair into the distributed hash table.

        Args:
            key: The key to store the value under.
            value: The value to store.
        '''
        id = hashfunc(key.encode())

        if self._chord.node.in_range(id):
            self._self_logs.append(
                LogRecord(action=KvAction.ADD, record=KvRecord(key, value)))

            self._kv[key] = value

            log.info(f'{key} = {value} added to KV')

            return

        node = self._chord.node.find_successor(id)
        url  = f'http://{node.frontend_address}/key/{key}'

        try:
            _ = await request('PUT', url, json={'value': value})
        except httpx.HTTPError as e:
            log.error(
                f'Failed to put key {key} to {node.frontend_address}: {e}')

    async def _remove(self, key: str) -> None:
        value = self._kv.pop(key, None)

        if value:
            self._self_logs.append(
                LogRecord(action=KvAction.DEL, record=KvRecord(key, value)))

            log.info(f'{key} = {value} removed from KV')

    async def _replay(self) -> None:
        for log_record in self._pred_logs:
            if log_record.action == KvAction.ADD:
                await self.put(log_record.record.key, log_record.record.value)
            if log_record.action == KvAction.DEL:
                await self._remove(log_record.record.key)

        self._pred_logs.clear()

    async def _sync_pred_logs(self) -> None:
        pred = self._chord.node.predecessor

        if pred is None or pred.frontend_address is None \
                or pred.frontend_address == self._chord.node.frontend_address:
            return

        offset = len(self._pred_logs)
        url    = f'http://{pred.frontend_address}/logs'
        res    = await request('GET', url, params={'offset': offset})
        res.raise_for_status()
        body   = res.json()

        new_logs = []

        for log_dict in body['logs']:
            action = KvAction[log_dict['action']]
            record = KvRecord(**log_dict['record'])
            new_logs.append(LogRecord(action=action, record=record))

        if new_logs:
            self._pred_logs.extend(new_logs)

    async def _move_keys(self) -> None:
        pred = self._chord.node.predecessor

        if pred is None:
            return

        kvs_to_remove = {}

        try:
            for key, value in self._kv.items():
                url = f'http://{pred.frontend_address}/key/{key}'
                id  = hashfunc(key.encode())

                if not self._chord.node.in_range(id):
                    _ = await request('PUT', url, json={'value': value})
                    kvs_to_remove[key] = value
        except httpx.HTTPError as e:
            log.error(f'Failed to move keys to predecessor: {e}')

            return

        try:
            await self._sync_pred_logs()
        except httpx.HTTPError as e:
            log.error(f'Failed to sync logs from predecessor: {e}')

            return

        for key, value in kvs_to_remove.items():
            self._self_logs.append(
                LogRecord(action=KvAction.DEL, record=KvRecord(key, value)))
            await self._remove(key)

    async def _sync_pred_logs_loop(self):
        while not self._chord.should_exit.wait(timeout=5.0):
            try:
                await self._sync_pred_logs()
            except httpx.HTTPError as e:
                log.error(f'Failed to sync logs from predecessor: {e}')

    async def _predecessor_failed_handler_loop(self):
        while not self._chord.should_exit.wait(timeout=1.0):
            if self._chord.node.predecessor_failed.is_set():
                await self._replay()
                self._chord.node.predecessor_failed.clear()

    async def _predecessor_changed_handler_loop(self):
        while not self._chord.should_exit.wait(timeout=1.0):
            if self._chord.node.predecessor_changed.is_set():
                self._pred_logs.clear()
                await self._move_keys()
                self._chord.node.predecessor_changed.clear()

    def serve(self) -> None:
        '''Start the distributed hash table service.'''
        self._chord.serve()

        threading.Thread(
            target = asyncio.run,
            args   = (self._sync_pred_logs_loop(),),
            daemon = True
        ).start()
        threading.Thread(
            target = asyncio.run,
            args   = (self._predecessor_failed_handler_loop(),),
            daemon = True
        ).start()
        threading.Thread(
            target = asyncio.run,
            args   = (self._predecessor_changed_handler_loop(),),
            daemon = True
        ).start()

    def shutdown(self) -> None:
        '''Shutdown the distributed hash table service.'''
        self._chord.shutdown()

    @classmethod
    async def build(
        cls,
        initial_kv:       dict[str, str] | None = None,
        frontend_address: str | None            = None
    ) -> 'DistributedHashTable':
        '''Build a distributed hash table instance.

        Args:
            initial_kv: Initial key-value pairs to populate the DHT.
            frontend_address: Frontend address for the DHT node.

        Returns:
            An instance of DistributedHashTable.
        '''
        dht    = cls()
        router = APIRouter()

        join_chord: str | None = JOIN_ADDR
        join_front: str | None = None

        if join_chord is not None:
            req  = await request('GET', f'http://{JOIN_ADDR}/addresses')
            body = req.json()
            join_front = body.get('frontend_address')

        kv:        dict[str, str]  = {}
        self_logs: list[LogRecord] = []

        if join_front is not None and initial_kv is not None:
            for key, value in initial_kv.items():
                url = f'http://{join_front}/key/{key}'

                try:
                    _ = await request('PUT', url, json={'value': value})
                except httpx.HTTPError as e:
                    log.error(f'Failed to put key {key} to {join_front}: {e}')
        else:
            kv = (initial_kv or {})

            for key, value in kv.items():
                self_logs.append(
                    LogRecord(action=KvAction.ADD, record=KvRecord(key, value)))

        @router.get('/key/{key}')
        async def get_key(key: str) -> Value:
            value = await dht.get(key)

            if value is None:
                detail = f'Key {key} not found'

                raise HTTPException(status.HTTP_404_NOT_FOUND, detail)

            return Value(value=value)

        @router.put('/key/{key}')
        async def put_key(key: str, body: Value) -> Response:
            await dht.put(key, body.value)

            return Response(status_code=status.HTTP_204_NO_CONTENT)

        @router.get('/logs')
        async def logs(offset: int) -> JSONResponse:
            if offset < 0 or offset > len(dht._self_logs):
                detail = f'Offset {offset} out of range'

                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)

            content = {
                'logs': [
                    asdict(log) | {'action': log.action.name}
                    for log in dht._self_logs[offset:]
                ]
            }

            return JSONResponse(content, status.HTTP_200_OK)

        dht._kv        = kv
        dht._router    = router
        dht._self_logs = self_logs
        dht._pred_logs = []
        dht._chord     = Chord.build(
            join_address     = join_chord,
            frontend_address = frontend_address
        )

        return dht
