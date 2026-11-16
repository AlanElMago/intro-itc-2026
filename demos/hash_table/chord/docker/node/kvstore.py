import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import httpx

log = logging.getLogger('uvicorn.main')


class KvAction(Enum):
    ADD = 0
    DEL = 1

@dataclass(frozen=True)
class KvRecord:
    filename: str
    address:  str  # where the file is located

@dataclass(frozen=True)
class LogRecord:
    action: KvAction
    record: KvRecord

class KvStore:
    _kv:       dict[int, KvRecord]
    _curr_log: list[LogRecord]
    _pred_log: list[LogRecord]

    def __init__(self) -> None:
        self._kv = {}
        self._curr_log = []
        self._pred_log = []

    def get(self, key: int) -> KvRecord | None:
        return self._kv.get(key)

    def put(self, key: int, record: KvRecord) -> None:
        self._kv[key] = record
        self._curr_log.append(LogRecord(action=KvAction.ADD, record=record))

        log.info(f'{record} added to KV with key {key}')

    def remove(self, key: int) -> KvRecord | None:
        try:
            record = self._kv.pop(key)
        except KeyError:
            return None

        self._curr_log.append(LogRecord(action=KvAction.DEL, record=record))

        log.info(f'{record} removed from KV with key {key}')

        return record

    async def move_keys(
        self,
        address:    str,
        range_func: Callable[[int], bool],
        client:     httpx.AsyncClient
    ) -> None:
        url = f'http://{address}/key'
        keys_to_remove = []

        for key, record in self._kv.items():
            if not range_func(key):
                _ = await client.post(url, json={
                    'filename': record.filename,
                    'address':  record.address
                })
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.remove(key)

def register_files_local(
    kv_store: KvStore,
    address:  str,
    hashfunc: Callable[[bytes], int]
) -> None:
    for file in [f for f in Path('files').iterdir() if f.is_file]:
        kv_store.put(
            key    = hashfunc(file.name.encode()),
            record = KvRecord(
                filename = file.name,
                address  = address
            )
        )

async def register_files_remote(
    self_address:   str,
    target_address: str,
    client:         httpx.AsyncClient
) -> None:
    url = f'http://{target_address}/key'

    for file in [f for f in Path('files').iterdir() if f.is_file]:
        _ = await client.post(url, json={
            'filename': file.name,
            'address':  self_address
        })
