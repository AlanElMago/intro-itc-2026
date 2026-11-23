import hashlib
import logging
import os
import socket
import threading
from abc import ABC, abstractmethod
from typing import Final

import httpx
import mylogging
import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HOSTNAME: Final[str] = socket.gethostname()
HOST:     Final[str] = socket.gethostbyname(HOSTNAME)
PORT:     Final[str] = os.environ.get('CHORD_PORT', '8081')
ADDRESS:  Final[str] = f'{HOST}:{PORT}'

NUM_BITS: Final[int] = 16
MODULO:   Final[int] = 2**NUM_BITS
HASH_ALG: Final[str] = 'sha1'




log = logging.getLogger('chord')




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




class Addresses(BaseModel):
    '''Pydantic model representing the addresses of a node in the Chord
    network.
    '''
    chord_address:    str
    frontend_address: str | None = None




class Node(ABC):
    '''Abstract base class representing a node in the Chord network.'''

    @property
    @abstractmethod
    def id(self) -> int:
        '''Return the unique identifier of the node.'''

    @property
    @abstractmethod
    def chord_address(self) -> str:
        '''Return the network address of the node in the Chord ring, which is
        used for inter-node communication.
        '''

    @property
    @abstractmethod
    def frontend_address(self) -> str | None:
        '''Return the frontend address of the node, which is used for client
        interactions.
        '''

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
    _chord_address:    str
    _frontend_address: str | None

    _client: httpx.Client

    @property
    def id(self) -> int:
        return hashfunc(self._chord_address.encode())

    @property
    def chord_address(self) -> str:
        return self._chord_address

    @property
    def frontend_address(self) -> str | None:
        return self._frontend_address

    @property
    def successor(self) -> Node:
        url = f'http://{self.chord_address}/successor'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    @property
    def predecessor(self) -> Node | None:
        url = f'http://{self.chord_address}/predecessor'
        res = self._client.get(url)

        if res.status_code == status.HTTP_404_NOT_FOUND:
            return None

        return RemoteNode.from_dict(res.json(), self._client)

    def find_successor(self, id: int) -> Node:
        url = f'http://{self.chord_address}/find-successor/{id}'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    def closest_preceding_node(self, id: int) -> Node:
        url = f'http://{self.chord_address}/closest-preceding-node/{id}'
        res = self._client.get(url)

        return RemoteNode.from_dict(res.json(), self._client)

    def notify(self, n: Node) -> None:
        url = f'http://{self.chord_address}/notify'
        _   = self._client.put(url, json={
            'chord_address':    n.chord_address,
            'frontend_address': n.frontend_address
        })

    @classmethod
    def from_dict(cls, d: dict, client: httpx.Client) -> Node:
        n = cls()

        n._chord_address    = d['chord_address']
        n._frontend_address = d['frontend_address']
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

    _frontend_address: str | None

    _pred:    Node | None
    _client:  httpx.Client
    _fingers: list[Node]

    @property
    def id(self) -> int:
        return hashfunc(ADDRESS.encode())

    @property
    def chord_address(self) -> str:
        return ADDRESS

    @property
    def frontend_address(self) -> str | None:
        return self._frontend_address

    @property
    def successor(self) -> Node:
        return self._fingers[0]

    @property
    def predecessor(self) -> Node | None:
        return self._pred

    def _set_predecessor(self, n: Node | None) -> None:
        old = self._pred
        self._pred = n

        if n is None or n.chord_address == self.chord_address:
            return

        if old is None or old.chord_address != n.chord_address:
            log.info(f'Predecessor changed to {n.chord_address}')
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

        url = f'http://{self.predecessor.chord_address}/health'

        try:
            res   = self._client.get(url)
            alive = res.status_code == status.HTTP_200_OK
        except httpx.HTTPError:
            alive = False

        if not alive:
            log.info(f'Predecessor {self.predecessor.chord_address} failed')

            self._set_predecessor(None)
            self.predecessor_failed.set()

    @classmethod
    def from_dict(cls, d: dict, client: httpx.Client) -> Node:
        n = RemoteNode()

        n._chord_address    = d['chord_address']
        n._frontend_address = d['frontend_address']
        n._client  = client

        return n




class Chord:
    '''Represents a Chord node with its associated HTTP server and state.'''

    node: SelfNode
    '''The local node in the Chord network.'''

    should_exit: threading.Event
    '''Event that is set when the Chord node should exit, signaling all loops
    to terminate.'''

    _server: uvicorn.Server

    @property
    def hostname(self) -> str:
        '''Return the hostname of the machine running this Chord node.'''
        return HOSTNAME

    @property
    def modulo(self) -> int:
        '''Return the modulo value used for hashing in the Chord ring.'''
        return MODULO

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

    def serve(self) -> None:
        '''Start the Uvicorn server for the Chord node.'''
        threading.Thread(
            target=self._server.run, daemon=True).start()
        threading.Thread(
            target=self._stabilize_loop, daemon=True).start()
        threading.Thread(
            target=self._fix_fingers_loop, daemon=True).start()
        threading.Thread(
            target=self._check_predecessor_loop, daemon=True).start()

        log.info(f'Chord running at {self.node.chord_address} ' \
                 f'with id {self.node.id}')

    def shutdown(self) -> None:
        '''Stop the Uvicorn server for the Chord node.'''
        self.should_exit.set()
        self._server.should_exit = True

        log.info('Chord shutting down')

    @classmethod
    def build(
        cls,
        join_address:     str | None = None,
        frontend_address: str | None = None
    ) -> 'Chord':
        '''Build a Chord instance.

        Args:
            join_chord: The chord address of an existing node to join, or None
            to create a new ring.
            join_front: The frontend address of the existing node to join, or
            None if not applicable.
            frontend_address: The frontend address for client interactions.

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
        node._frontend_address   = frontend_address
        node.predecessor_changed = threading.Event()
        node.predecessor_failed  = threading.Event()

        if join_address is None:
            node.create()
        else:
            node.join(n=RemoteNode.from_dict({
                'chord_address':    join_address,
                'frontend_address': None
            }, client))

        router = APIRouter()

        @router.get('/health')
        def health() -> JSONResponse:
            content = {'status': 'ok'}

            return JSONResponse(content, status.HTTP_200_OK)

        @router.get('/addresses')
        def addresses() -> Addresses:
            return Addresses(
                chord_address    = node.chord_address,
                frontend_address = node.frontend_address
            )

        @router.get('/successor')
        def successor() -> Addresses:
            return Addresses(
                chord_address    = node.successor.chord_address,
                frontend_address = node.successor.frontend_address
            )

        @router.get('/predecessor')
        def predecessor() -> Addresses:
            pred = node.predecessor

            if pred is None:
                detail = 'No predecessor'

                raise HTTPException(status.HTTP_404_NOT_FOUND, detail)

            return Addresses(
                chord_address    = pred.chord_address,
                frontend_address = pred.frontend_address
            )

        @router.get('/find-successor/{id}')
        def find_successor(id: int) -> Addresses:
            succ = node.find_successor(id)

            return Addresses(
                chord_address    = succ.chord_address,
                frontend_address = succ.frontend_address
            )

        @router.get('/closest-preceding-node/{id}')
        def closest_preceding_node(id: int) -> Addresses:
            n = node.closest_preceding_node(id)

            return Addresses(
                chord_address    = n.chord_address,
                frontend_address = n.frontend_address
            )

        @router.put('/notify')
        def notify(body: Addresses) -> JSONResponse:
            n = RemoteNode.from_dict({
                'chord_address':    body.chord_address,
                'frontend_address': body.frontend_address
            }, client)

            node.notify(n)

            content = {'status': 'ok'}

            return JSONResponse(content, status.HTTP_200_OK)

        app = FastAPI()
        app.include_router(router)
        app.add_middleware(
            mylogging.AccessLog, log=logging.getLogger('chord.access'))

        server = uvicorn.Server(
            config = uvicorn.Config(
                    app        = app,
                    host       = '0.0.0.0',
                    port       = int(PORT),
                    log_config = None,
                    access_log = False
            )
        )

        chord = cls()

        chord.node        = node
        chord._server     = server
        chord.should_exit = threading.Event()

        return chord
