import hashlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from string import Template

log = logging.getLogger(__name__)

log_template = Template(
    '$filename $status (storage=$storage, idx=$idx, pos=$pos, keyhash=$keyhash)')


def hashfunc(data: bytes) -> int:
    return int.from_bytes(hashlib.sha1(data, usedforsecurity=False).digest())


class StorageType(StrEnum):
    RAM   = 'ram'
    DISK  = 'disk'
    CLOUD = 'cloud'


@dataclass
class Location:
    """Where a file lives.

    ram:   `data` holds the file bytes, `address` is empty.
    disk:  `address` is the directory containing the file.
    cloud: `address` is the URI the file can be downloaded from.
    """
    storage: StorageType
    data:    bytes = b''
    address: str   = ''


@dataclass
class Record:
    keyhash:     int
    location:    Location
    next_record: 'Record | None' = None


class Storage:
    _records:  list[Record | None]  # None = empty bucket
    _hashfunc: Callable[[bytes], int]
    _lock:     threading.Lock

    def __init__(
        self,
        size: int=16,
        hashfunc: Callable[[bytes], int]=hashfunc
    ):
        self._records  = [None] * size
        self._hashfunc = hashfunc
        self._lock     = threading.Lock()

        log.info(f'storage created with size {size}')

    @property
    def size(self) -> int:
        return len(self._records)

    def read(self, filename: str) -> Location | None:
        keyhash = self._hashfunc(filename.encode())
        idx     = keyhash % self.size

        pos    = 0
        record = self._records[idx]

        while record is not None:
            if record.keyhash == keyhash:
                log.info(log_template.substitute(
                    filename=filename,
                    status='found',
                    storage=record.location.storage,
                    idx=idx,
                    pos=pos,
                    keyhash=keyhash
                ))

                return record.location

            record = record.next_record
            pos += 1

        log.info(f'{filename} not found')

        return None

    def write(self, filename: str, location: Location) -> None:
        keyhash = self._hashfunc(filename.encode())
        idx     = keyhash % self.size

        # Chain appends are read-modify-write; serialize concurrent writers.
        with self._lock:
            head = self._records[idx]

            if head is None:
                self._records[idx] = Record(keyhash, location)

                log.info(log_template.substitute(
                    filename=filename,
                    status='written',
                    storage=location.storage,
                    idx=idx,
                    pos=0,
                    keyhash=keyhash
                ))

                return

            pos         = 0
            curr_record = head

            while True:
                if curr_record.keyhash == keyhash:
                    curr_record.location = location

                    log.info(log_template.substitute(
                        filename=filename,
                        status='overwritten',
                        storage=location.storage,
                        idx=idx,
                        pos=pos,
                        keyhash=keyhash
                    ))

                    return

                if curr_record.next_record is None:
                    break

                curr_record = curr_record.next_record
                pos += 1

            log.warning(log_template.substitute(
                filename=filename,
                status='hash collision',
                storage=head.location.storage,
                idx=idx,
                pos=0,
                keyhash=head.keyhash
            ))

            curr_record.next_record = Record(keyhash, location)

            log.info(log_template.substitute(
                filename=filename,
                status='appended',
                storage=location.storage,
                idx=idx,
                pos=pos + 1,
                keyhash=keyhash
            ))
