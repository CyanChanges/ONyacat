#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
import struct
import uuid
import weakref
from asyncio import Future, Task
from dataclasses import InitVar
from datetime import datetime, timedelta
from enum import IntEnum
from typing import AnyStr, Self, Optional, Sequence, Literal, Never, Protocol, Any, Awaitable, Callable, TypeVar, \
    Coroutine
from uuid import UUID

from more_itertools import first_true
from pydantic import GetCoreSchemaHandler, BaseModel, Field
from pydantic.dataclasses import dataclass
from pydantic_core import CoreSchema, core_schema

from exceptions import InvalidPacakgeError, NoSuchPeerError
from globals import (
    _cv_package
)
from util import pack_addr, data_pack

BASIC_PACK_SIZE = 2
Remote = tuple[str, int]


class PackageType(IntEnum):
    # protocol
    handshake = 0x0
    wave_hand = 0x1
    _reserved1 = 0x3
    userdata = 0x4
    # broadcast
    peer_connected = 0x5
    peer_disconnected = 0x6
    # keepalive
    heartbeat = 0x7
    timeout = 0x8
    bad_package = 0x9
    # service
    service_temporary_unavailable = 0xa
    # Network
    sign = 0xb
    join_network = 0xc
    leave_network = 0xd
    peer_update = 0xe


class PeerType(IntEnum):
    csharp = 0x1  # the client listen for the client to connect
    client = 0x2  # the client connect to csharp
    server = 0x3  # the server broadcast ip address of peers


HandlerType = Literal["handshake", 'disconnect', 'heartbeat']

PeerIdentifier = UUID


class ConnectionLayerModel(BaseModel):
    timeout: timedelta
    peers: dict[PeerIdentifier, "Peer"]
    data_queues: Optional[dict[Remote, Any]]


class ConnectionLayer(Protocol):
    timeout: timedelta
    peers: dict[PeerIdentifier, "Peer"]
    data_queues: Optional[dict[Remote, asyncio.StreamReader]]

    @classmethod
    def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
    ):
        return core_schema.no_info_after_validator_function(cls, handler(ConnectionLayerModel))

    @property
    def type(self) -> PeerType:
        raise NotImplementedError

    def send_all(self, package: "Package") -> Task:
        pass

    async def send_package(self, package: "Package", addr: Remote):
        pass

    async def recv_package(self, addr: Remote):
        pass

    def emit(self, handle_type: HandlerType, peer: "Peer", *args: Any, **kwargs: Any) -> Future:
        pass

    def on(self, handler_type: HandlerType) -> Callable[[Callable], Callable]:
        pass

    def package(self, peer: "Peer", package: "Package") -> Any:
        pass

    def on_package(self, peer: "Peer", receiver: Callable[[], Awaitable], prepend: bool = False):
        pass

    _T1 = TypeVar("_T1", Task, Future)

    def task(self, task: _T1) -> _T1:
        pass


@dataclass
class PeerMeta:
    type: PeerType = None
    disconnected: bool = None
    last_heartbeat: datetime = None
    networks: Sequence["Network"] = None

    def setup(self) -> Self:
        self.networks = []
        self.last_heartbeat = datetime.now()
        return self


class PeerModel(BaseModel):
    identifier: PeerIdentifier
    addr: Remote
    meta: PeerMeta

    @classmethod
    def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(cls))


class Network(BaseModel):
    layer: ConnectionLayer
    peers: Sequence["Peer"] = Field(default_factory=set)


_SKIP_INIT = '__skip_init'
_MERGE_META = '__merge_meta'


async def _await_in_order(t1: Awaitable, t2: Awaitable = None):
    await t1,
    if t2 is not None:
        await t2


def to_task(coro: Coroutine):
    return asyncio.create_task(coro)


class Peer:
    def __new__(
            cls,
            layer: ConnectionLayer,
            identifier: PeerIdentifier = None,
            addr: Remote = None,
            meta: PeerMeta = None,
            *args,
            **kwargs
    ) -> "Peer":
        obj = None
        if identifier is not None:
            obj = layer.peers.get(identifier, False)
            if addr is None:
                raise NoSuchPeerError.identifier(identifier)
        if addr is not None:
            obj = first_true(layer.peers.values(), False, lambda x: x.addr == addr)
        if obj is None or obj is False:
            obj = object.__new__(cls)
        else:
            setattr(obj, _SKIP_INIT, True)
            setattr(obj, _MERGE_META, meta)
        return obj

    @classmethod
    def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(PeerModel))

    def __init__(
            self,
            layer: ConnectionLayer,
            identifier: PeerIdentifier = None,
            addr: Remote = None,
            meta: PeerMeta = None
    ):
        self.meta = meta
        self.merge(meta)
        if getattr(self, _SKIP_INIT, None):
            merge_meta: Optional[PeerMeta] = getattr(self, _MERGE_META, None)
            if not merge_meta:
                return
            self.merge(merge_meta)
            return
        if addr and identifier is None:
            identifier = uuid.uuid4()
        self.layer = layer
        self.identifier = identifier
        if not addr:
            raise NoSuchPeerError.identifier(identifier, self)
        self.addr = addr
        if meta is None:
            self.meta.setup()
        self.layer.peers.update({self.identifier: self})

    # noinspection SpellCheckingInspection
    def weakref(self):
        return weakref.ref(self)

    @property
    def type(self):
        return self.meta.type

    def merge(self, meta: PeerMeta):
        if not self.meta:
            self.meta = PeerMeta()
        if not meta:
            return
        for key in vars(meta).keys():
            if key is not None:
                setattr(self.meta, key, getattr(meta, key))

    def to_handshake(self, package: "Package"):
        assert package.pack_type == PackageType.handshake, 'non handshake package'
        self.merge(PeerMeta(type=PeerType(package.data[0])))
        self.update_heartbeat()
        _cv_package.set(package)
        return self.layer.task(to_task(_await_in_order(
            self.layer.emit('handshake', self)
        )))

    def mark_disconnect(self):
        self.meta.disconnected = True
        return self.layer.emit("disconnect", self)

    def remove(self) -> Future:
        future = asyncio.ensure_future(self.mark_disconnect())
        try:
            if self.addr in self.layer.data_queues:
                self.layer.data_queues.pop(self.addr)
        finally:
            if self.identifier in self.layer.peers:
                self.layer.peers.pop(self.identifier)
        return future

    def __hash__(self):
        return hash(self.identifier)

    def update_heartbeat(self):
        self.meta.last_heartbeat = datetime.now()

    def to_heartbeat(self):
        self.update_heartbeat()
        return to_task(_await_in_order(
            self.layer.emit("heartbeat", self)
        ))

    def is_alive(self, timeout: timedelta) -> bool:
        return (not self.meta.disconnected) and datetime.now() - self.meta.last_heartbeat < timeout

    def __repr__(self):
        return f'Peer({getattr(self.meta.type, "name", "Unknown")}, {pack_addr(getattr(self, "addr", "???"))})'

    def bad_package(self, reason: AnyStr):
        return self.layer.send_package(Package(PackageType.bad_package, reason), self.addr)

    def timeout(self):
        return self.layer.task(to_task(_await_in_order(
            self.remove(),
            self.layer.send_package(Package(PackageType.timeout), self.addr)
        )))

    def to_disconnect(self):
        """
        peer ask for disconnecting
        :return: disconnect task
        """
        return self.layer.task(to_task(_await_in_order(
            self.mark_disconnect(),
            self.layer.send_package(Package(PackageType.wave_hand, self.layer.type), self.addr)
        )))


Network.model_rebuild()
PeerModel.model_rebuild()


class BoundedPeer(Protocol):
    def __call__(
            self,
            identifier: PeerIdentifier = None,
            addr: Remote = None,
            meta: PeerMeta = None
    ) -> Peer:
        pass


DataPack = AnyStr | int


@dataclass(repr=True)
class Package:
    pack_type: PackageType
    data: DataPack = Field(init_var=False, default=0)
    _peer: Optional[Peer] = None

    def __post_init__(self):
        _data = self.data
        self.data = b''
        if isinstance(_data, bytes):
            self.data = _data
            return
        if isinstance(_data, list | tuple):
            for b in _data:
                self.data += data_pack(b)
        else:
            b = _data
            self.data += data_pack(b)

    def bind(self, peer: Peer) -> None:
        self._peer = peer

    def encode(self) -> bytes:
        return struct.pack('csc', self.pack_type.value.to_bytes(), self.data, b'\xff')

    @classmethod
    def check_header(cls, data: bytes) -> Literal[True] | Never:
        if len(data) >= BASIC_PACK_SIZE:
            raise InvalidPacakgeError(data)
        return True

    @classmethod
    def from_bytes(cls, data: bytes, addr: Optional[Remote] = None) -> Self:
        if len(data) < BASIC_PACK_SIZE:
            raise InvalidPacakgeError(data, addr)
        if data[:-2:-1] != b'\xff':
            raise InvalidPacakgeError(data, addr)
        type_byte = data[0]
        data_bytes = data[1:-1]
        return cls(PackageType(type_byte), data_bytes)


class Packages:
    pack = Package
