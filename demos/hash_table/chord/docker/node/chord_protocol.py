import hashlib
import random
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Node:
    id:      int
    address: str

    @classmethod
    def from_dict(cls, obj: dict) -> 'Node':
        return cls(id=obj['id'], address=obj['address'])


@dataclass(frozen=False)
class Finger:
    start: int
    end:   int
    node:  Node


def is_id_in_range(id: int, start: int, end: int, modulo: int) -> bool:
    '''
    Evaluate whether an id is within an interval [start, end]
    '''
    id_mod    = id    % modulo
    start_mod = start % modulo
    end_mod   = end   % modulo

    if start_mod <= end_mod:
        return id_mod >= start_mod and id_mod <= end_mod
    else:
        return id_mod >= start_mod or  id_mod <= end_mod


class Chord:
    _num_bits: int
    _modulo:   int
    _hash_alg: str
    _node:     Node
    _pred:     Node | None
    _fingers:  list[Finger]

    @property
    def address(self) -> str:
        return self._node.address

    @property
    def id(self) -> int:
        return self._node.id

    @property
    def predecessor(self) -> Node | None:
        return self._pred

    @property
    def successor(self) -> Node:
        return self._fingers[0].node

    def set_predecessor(self, address: str) -> None:
        id = self.hashfunc(address.encode())

        self._pred = Node(id, address)

    def hashfunc(self, data: bytes) -> int:
        return int.from_bytes(
            hashlib.new(
                name = self._hash_alg,
                data = data,
                usedforsecurity = False
            ).digest()
        ) % self._modulo

    def closest_preceding_finger(self, target_id: int) -> Node:
        for i in range(self._num_bits - 1, -1, -1):
            if is_id_in_range(
                id     = self._fingers[i].node.id,
                start  = self.id + 1,
                end    = target_id - 1,
                modulo = self._modulo
            ):
                return self._fingers[i].node

        return self._node

    async def find_predecessor(
        self,
        target_id: int,
        client:    httpx.AsyncClient
    ) -> Node:
        pred_node      = self._node
        pred_node_succ = self.successor

        while not is_id_in_range(
            id     = target_id,
            start  = pred_node.id + 1,
            end    = pred_node_succ.id,
            modulo = self._modulo
        ):
            if pred_node.address == self.address:
                pred_node = self.closest_preceding_finger(target_id)
            else:
                url = f'http://{pred_node.address}/chord/closest-preceding-finger/{target_id}'
                res = await client.get(url)
                pred_node = Node.from_dict(res.json())

            if pred_node.address == self.address:
                pred_node_succ = self.successor
            else:
                url = f'http://{pred_node.address}/chord/successor'
                res = await client.get(url)
                pred_node_succ = Node.from_dict(res.json())

        return pred_node

    async def find_successor(
        self,
        target_id: int,
        client:    httpx.AsyncClient
    ) -> Node:
        pred_node = await self.find_predecessor(target_id, client)

        if pred_node.address == self.address:
            return self.successor
        else:
            url = f'http://{pred_node.address}/chord/successor'
            res = await client.get(url)

            return Node.from_dict(res.json())

    def notify(self, address: str) -> None:
        id = self.hashfunc(address.encode())

        if (self.predecessor is None) or is_id_in_range(
            id     = id,
            start  = self.predecessor.id + 1,
            end    = self.id - 1,
            modulo = self._modulo
        ):
            self._pred = Node(id, address)

    async def check_predecessor(self, client: httpx.AsyncClient) -> None:
        if self.predecessor == None:
            return

        url = f'http://{self.predecessor.address}/health'

        try:
            res = await client.get(url)

            if res.status_code != 200:
                self._pred = None
        except httpx.TimeoutException:
            self._pred = None

    async def stabilize(self, client: httpx.AsyncClient) -> None:
        url = f'http://{self.successor.address}/chord/predecessor'

        try:
            res = await client.get(url)
        except httpx.TimeoutException:
            if self.predecessor is not None \
                    and self.predecessor.address == self.successor.address:
                self._pred = None

            self._fingers[0].node = Node(self.id, self.address)

            return

        data = res.json()

        if data:
            x = Node.from_dict(data)

            if is_id_in_range(
                id     = x.id,
                start  = self.id + 1,
                end    = self.successor.id - 1,
                modulo = self._modulo
            ):
                self._fingers[0].node = x

        url = f'http://{self.successor.address}/chord/notify'
        _   = await client.put(url, json={'address': self.address})

    async def fix_fingers(self, client: httpx.AsyncClient) -> None:
        i = random.randint(1, self._num_bits - 1)

        target_id = self._fingers[i].start

        self._fingers[i].node = await self.find_successor(target_id, client)

    async def join_ring(
        self,
        address: str,
        client:  httpx.AsyncClient
    ) -> None:
        if address == self.address:
            return

        url = f'http://{address}/chord/find-successor/{self.id}'
        res = await client.get(url)
        self._fingers[0].node = Node.from_dict(res.json())

    async def leave_ring(self, client: httpx.AsyncClient) -> None:
        raise NotImplementedError

    @classmethod
    def build(
        cls,
        ip_addr:  str,
        port:     str,
        num_bits: int,
        hash_alg: str='sha1'
    ) -> 'Chord':
        chord = cls()

        modulo  = 2**num_bits
        address = f'{ip_addr}:{port}'

        chord._num_bits = num_bits
        chord._modulo   = modulo
        chord._hash_alg = hash_alg

        id      = chord.hashfunc(address.encode())
        node    = Node(id, address)
        fingers = [
            Finger(
                start = (id + 2**k) % modulo,
                end   = (id + 2**(k + 1) - 1) % modulo,
                node  = node
            ) for k in range(num_bits)
        ]

        chord._node    = node
        chord._pred    = None
        chord._fingers = fingers

        return chord
