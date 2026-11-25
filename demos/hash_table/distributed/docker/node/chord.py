import hashlib
import logging
import os
import socket
import threading
from abc import ABC, abstractmethod
from typing import Final

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HOSTNAME: Final[str] = socket.gethostname()
HOST:     Final[str] = socket.gethostbyname(HOSTNAME)
PORT:     Final[str] = os.environ.get('PORT', '42000')
ADDRESS:  Final[str] = f'{HOST}:{PORT}'

NUM_BITS: Final[int] = 16
MODULO:   Final[int] = 2**NUM_BITS
HASH_ALG: Final[str] = 'sha1'




log = logging.getLogger('uvicorn')




def hashfunc(data: bytes) -> int:
    '''Hash a byte string using the specified hashing algorithm and return an
    integer in the range [0, MODULO).

    Args:
        data: The byte string to hash.

    Returns:
        An integer in the range [0, MODULO) representing the hash of the input.
    '''
    return int.from_bytes(
        hashlib.new(name=HASH_ALG, data=data, usedforsecurity=False).digest()
    ) % MODULO

def in_range(id: int, a: int, b: int) -> bool:
    '''Evaluate whether an id is within an interval [a, b] in the chord ring.

    Args:
        id: The id to check.
        a:  The start of the interval.
        b:  The end of the interval.

    Returns:
        True if id is in the interval [a, b], False otherwise.
    '''
    id_mod = id % MODULO
    a_mod  = a  % MODULO
    b_mod  = b  % MODULO

    if a_mod <= b_mod:
        return id_mod >= a_mod and id_mod <= b_mod
    else:
        return id_mod >= a_mod or  id_mod <= b_mod




class Address(BaseModel):
    '''Pydantic model representing the addresses of a node in the Chord
    network.
    '''
    address: str




class Node(ABC):
    '''Abstract base class representing a node in the Chord network.'''

    @property
    @abstractmethod
    def id(self) -> int:
        '''Return the unique identifier of the node.'''

    @property
    @abstractmethod
    def address(self) -> str:
        '''Return the network address of the node in the Chord ring.'''

    @property
    @abstractmethod
    def successor(self) -> 'Node':
        '''Return the successor node in the Chord ring.'''

    @property
    @abstractmethod
    def predecessor(self) -> 'Node | None':
        '''Return the predecessor node in the Chord ring, or None if there is
        no predecessor.
        '''

    @abstractmethod
    def closest_preceding_node(self, id: int) -> 'Node':
        '''Return the closest preceding node for a given id in the Chord ring.

        Arguments:
            id: The id for which to find the closest preceding node.

        Returns:
            The closest preceding node for the given id.
        '''

    @abstractmethod
    def find_successor(self, id: int) -> 'Node':
        '''Return the successor node for a given id in the Chord ring.

        Arguments:
            id: The id for which to find the successor node.

        Returns:
            The successor node for the given id.
        '''

    @abstractmethod
    def notify(self, n: 'Node') -> None:
        '''Notify the current node about a potential predecessor node.'''

    @classmethod
    @abstractmethod
    def from_dict(cls, d: dict, client: httpx.Client) -> 'Node':
        '''Create a Node instance from a dictionary representation.

        Args:
            d: The dictionary containing node information.
            client: An httpx Client for making requests to other nodes.

        Returns:
            A Node instance created from the provided dictionary.
        '''




class RemoteNode(Node):
    '''Represents a remote node in the Chord network, allowing interaction with
    it through HTTP requests.
    '''
    _address:    str
    _client: httpx.Client

    @property
    def id(self) -> int:
        return hashfunc(self.address.encode())

    @property
    def address(self) -> str:
        return self._address

    @property
    def successor(self) -> Node:
        url = f'http://{self.address}/chord/successor'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    @property
    def predecessor(self) -> Node | None:
        url = f'http://{self.address}/chord/predecessor'
        res = self._client.get(url)

        if res.status_code == status.HTTP_404_NOT_FOUND:
            return None

        return RemoteNode.from_dict(res.json(), self._client)

    def find_successor(self, id: int) -> Node:
        url = f'http://{self.address}/chord/find-successor/{id}'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    def closest_preceding_node(self, id: int) -> Node:
        url = f'http://{self.address}/chord/closest-preceding-node/{id}'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    def notify(self, n: Node) -> None:
        url = f'http://{self.address}/chord/notify'
        _   = self._client.put(url, json={'address': n.address})

    @classmethod
    def from_dict(cls, d: dict, client: httpx.Client) -> Node:
        n = cls()

        n._address= d['address']
        n._client = client

        return n




class SelfNode(Node):
    '''Represents the local node in the Chord network, managing its own state
    and interactions with other nodes.
    '''

    predecessor_failed:  threading.Event
    '''Event that is set when the predecessor node fails to respond to health
    checks, indicating that the predecessor is no longer reachable.
    '''

    predecessor_changed: threading.Event
    '''Event that is set when the predecessor node changes, indicating that the
    local node has a new predecessor in the Chord ring.
    '''

    _pred:    Node | None
    _client:  httpx.Client
    _fingers: list[Node]

    @property
    def id(self) -> int:
        return hashfunc(ADDRESS.encode())

    @property
    def address(self) -> str:
        return ADDRESS

    @property
    def successor(self) -> Node:
        return self._fingers[0]

    @property
    def predecessor(self) -> Node | None:
        return self._pred

    def _set_predecessor(self, n: Node | None) -> None:
        old = self._pred
        self._pred = n

        if n is None or n.address == self.address:
            return

        if old is None or old.address != n.address:
            log.info(f'Predecessor changed to {n.address}')
            self.predecessor_changed.set()

    def in_range(self, id: int) -> bool:
        '''Evaluate whether an id is within the range of this node's
        responsibility in the Chord ring.

        Args:
            id: The id to check.

        Returns:
            True if id is in the range of this node's responsibility, False.
        '''
        if self.predecessor is None:
            return True

        return in_range(id=id, a=self.predecessor.id + 1, b=self.id)

    def closest_preceding_node(self, id: int) -> Node:
        for i in range(NUM_BITS - 1, -1, -1):
            if in_range(id=self._fingers[i].id, a=self.id + 1, b=id - 1):
                return self._fingers[i]

        return self

    def find_successor(self, id: int) -> Node:
        if in_range(id=id, a=self.id + 1, b=self.successor.id):
            return self.successor
        else:
            try:
                return self.closest_preceding_node(id).find_successor(id)
            except httpx.HTTPError:
                return self.successor

    def notify(self, n: Node) -> None:
        if self.predecessor is None \
                or in_range(id=n.id, a=self.predecessor.id + 1, b=self.id - 1):
            self._set_predecessor(n)

    def create(self) -> None:
        '''Initialize a new Chord ring with this node as the only member.'''
        self._set_predecessor(None)
        self._fingers[0] = self

    def join(self, n: Node) -> None:
        '''Join an existing Chord ring by contacting a known node n.'''
        self._set_predecessor(None)
        self._fingers[0] = n.find_successor(self.id)

    def stabilize(self) -> None:
        '''Periodically verify and update the successor and predecessor
        pointers to maintain the correctness of the Chord ring.
        '''
        try:
            n = self.successor.predecessor
        except httpx.HTTPError:
            self._fingers[0] = self

            return

        if n is not None \
                and in_range(id=n.id, a=self.id + 1, b=self.successor.id - 1):
            self._fingers[0] = n

        self.successor.notify(self)

    def fix_finger(self, idx: int) -> None:
        '''Periodically refresh the finger at the specified index to ensure
        that it remains up-to-date.

        Args:
            idx: the index of the finger to refresh (0-based)
        '''
        id = (self.id + 2**idx) % MODULO

        try:
            self._fingers[idx] = self.find_successor(id)
        except httpx.HTTPError:
            self._fingers[idx] = self

    def check_predecessor(self) -> None:
        '''Periodically check if the predecessor is still alive. If not, set it
        to None.
        '''
        if self.predecessor is None:
            return

        url = f'http://{self.predecessor.address}/chord/health'

        try:
            res   = self._client.get(url)
            alive = res.status_code == status.HTTP_200_OK
        except httpx.HTTPError:
            alive = False

        if not alive:
            log.info(f'Predecessor {self.predecessor.address} failed')

            self._set_predecessor(None)
            self.predecessor_failed.set()

    @classmethod
    def from_dict(cls, d: dict, client: httpx.Client) -> Node:
        n = RemoteNode()

        n._address = d['address']
        n._client  = client

        return n




class Chord:
    '''Represents a Chord node with its associated HTTP server and state.'''

    node: SelfNode
    '''The local node in the Chord network.'''

    should_exit: threading.Event
    '''Event that is set when the Chord node should exit, signaling all loops
    to terminate.'''

    _router: APIRouter

    @property
    def hostname(self) -> str:
        '''Return the hostname of the machine running this Chord node.'''
        return HOSTNAME

    @property
    def modulo(self) -> int:
        '''Return the modulo value used for hashing in the Chord ring.'''
        return MODULO

    @property
    def router(self) -> APIRouter:
        '''Return the FastAPI router for this Chord node, which includes all
        the HTTP endpoints needed for the Chord protocol.
        '''
        return self._router

    def _stabilize_loop(self) -> None:
        while not self.should_exit.wait(timeout=1.0):
            self.node.stabilize()

    def _fix_fingers_loop(self) -> None:
        idx = 0

        while not self.should_exit.wait(timeout=1.0):
            self.node.fix_finger(idx)
            idx = (idx + 1) % NUM_BITS

    def _check_predecessor_loop(self) -> None:
        while not self.should_exit.wait(timeout=1.0):
            self.node.check_predecessor()

    def start(self) -> None:
        '''Start the background processes for the Chord node.'''
        threading.Thread(
            target=self._stabilize_loop, daemon=True).start()
        threading.Thread(
            target=self._fix_fingers_loop, daemon=True).start()
        threading.Thread(
            target=self._check_predecessor_loop, daemon=True).start()

        log.info(
            f'Chord running at {self.node.address} with id {self.node.id}')

    def shutdown(self) -> None:
        '''Stop the running background processes for the Chord node.'''
        self.should_exit.set()

        log.info('Chord shutting down')

    @classmethod
    def build(cls, join_addr: str | None = None) -> 'Chord':
        '''Build a Chord instance.

        Args:
            join_addr: The chord address of an existing node to join, or None
            to create a new ring.

        Returns:
            An instance of Chord.
        '''
        node   = SelfNode()
        client = httpx.Client(
            timeout = httpx.Timeout(timeout=1.0),
            limits  = httpx.Limits(
                max_connections=10, max_keepalive_connections=5
            )
        )

        node._pred    = None
        node._client  = client
        node._fingers = [node] * NUM_BITS
        node.predecessor_changed = threading.Event()
        node.predecessor_failed  = threading.Event()

        if join_addr is None:
            node.create()
        else:
            node.join(n=RemoteNode.from_dict({'address': join_addr}, client))

        router = APIRouter()

        @router.get('/chord/health')
        def health() -> JSONResponse:
            content = {'status': 'ok'}

            return JSONResponse(content, status.HTTP_200_OK)

        @router.get('/chord/successor')
        def successor() -> Address:
            return Address(address=node.successor.address)

        @router.get('/chord/predecessor')
        def predecessor() -> Address:
            pred = node.predecessor

            if pred is None:
                detail = 'No predecessor'

                raise HTTPException(status.HTTP_404_NOT_FOUND, detail)

            return Address(address=pred.address)

        @router.get('/chord/find-successor/{id}')
        def find_successor(id: int) -> Address:
            succ = node.find_successor(id)

            return Address(address=succ.address)

        @router.get('/chord/closest-preceding-node/{id}')
        def closest_preceding_node(id: int) -> Address:
            n = node.closest_preceding_node(id)

            return Address(address=n.address)

        @router.put('/chord/notify')
        def notify(body: Address) -> JSONResponse:
            n = RemoteNode.from_dict({'address': body.address}, client)

            node.notify(n)

            content = {'status': 'ok'}

            return JSONResponse(content, status.HTTP_200_OK)

        chord = cls()

        chord.node        = node
        chord.should_exit = threading.Event()
        chord._router     = router

        return chord
