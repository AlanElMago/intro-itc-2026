import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from string import Template

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)-7s  %(message)s')

log_template = Template(
    '$filename $status (idx=$idx, pos=$pos, keyhash=$keyhash)')


def hashfunc(data: bytes) -> int:
    return int.from_bytes(hashlib.sha1(data, usedforsecurity=False).digest())


@dataclass
class Record:
    keyhash: int   = 0
    data:    bytes = b''
    next_record: 'Record | None' = None


class Storage:
    _records:  list[Record]
    _hashfunc: Callable[[bytes], int]

    def __init__(
        self,
        size: int=16,
        hashfunc: Callable[[bytes], int]=hashfunc
    ):
        self._records  = [Record() for _ in range(size)]
        self._hashfunc = hashfunc

        log.info(f'storage created with size {size}')

    @property
    def size(self) -> int:
        return len(self._records)

    def read(self, filename: str) -> bytes:
        keyhash = self._hashfunc(filename.encode())
        idx     = keyhash % self.size

        if self._records[idx].keyhash == 0:
            log.info(f'{filename} not found')

            return b''

        if self._records[idx].keyhash == keyhash:
            log.info(log_template.substitute(
                filename=filename,
                status='found',
                idx=idx,
                pos=0,
                keyhash=keyhash
            ))

            return self._records[idx].data

        pos = 1
        curr_record = self._records[idx]
        next_record = curr_record.next_record

        while next_record is not None:
            if next_record.keyhash == keyhash:
                log.info(log_template.substitute(
                    filename=filename,
                    status='found',
                    idx=idx,
                    pos=pos,
                    keyhash=keyhash
                ))

                return next_record.data

            curr_record = next_record
            next_record = next_record.next_record
            pos += 1

        log.info(f'{filename} not found')

        return b''

    def write(self, filename: str, data: bytes) -> None:
        keyhash = self._hashfunc(filename.encode())
        idx     = keyhash % self.size

        if self._records[idx].keyhash == keyhash:
            self._records[idx].data = data

            log.info(log_template.substitute(
                filename=filename,
                status='overwritten',
                idx=idx,
                pos=0,
                keyhash=keyhash
            ))

            return

        if self._records[idx].keyhash == 0:
            self._records[idx] = Record(keyhash, data)

            log.info(log_template.substitute(
                filename=filename,
                status='written',
                idx=idx,
                pos=0,
                keyhash=keyhash
            ))

            return

        pos = 1
        curr_record = self._records[idx]
        next_record = curr_record.next_record

        while next_record is not None:
            if next_record.keyhash == keyhash:
                next_record.data = data

                log.info(log_template.substitute(
                    filename=filename,
                    status='overwritten',
                    idx=idx,
                    pos=pos,
                    keyhash=keyhash
                ))

                return

            curr_record = next_record
            next_record = next_record.next_record
            pos += 1

        log.warning(log_template.substitute(
            filename=filename,
            status='hash collision',
            idx=idx,
            pos=0,
            keyhash=self._records[idx].keyhash
        ))

        curr_record.next_record = Record(keyhash, data)

        log.info(log_template.substitute(
            filename=filename,
            status='appended',
            idx=idx,
            pos=pos,
            keyhash=keyhash
        ))
