#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
import random
from abc import ABC, abstractmethod
from asyncio import Task, Future, Queue
from collections import deque
from datetime import timedelta
from functools import partial
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, error as socket_error
from typing import Protocol, Callable, Awaitable, Any, Literal, Optional, Coroutine
from globals import (
    _cv_peer,
    _cv_package
)

from log import logger
from structures import Remote, Package, PackageType, Peer, PeerType, PeerIdentifier, BoundedPeer
from util import pack_addr

HandlerType = Literal["handshake"] | Literal['disconnect']

QUEUE_SIZE_PER_REMOTE = 10
MAX_PACK_SIZE = 20480


class IConnectionLayer(Protocol):
    timeout: timedelta
    peers: dict[PeerIdentifier, Peer]
    data_queues: Optional[dict[Remote, asyncio.StreamReader]]

    @property
    def type(self) -> PeerType:
        raise NotImplementedError

    def send_all(self, package: Package) -> Task:
        pass

    async def send_package(self, package: Package, addr: Remote):
        pass

    async def recv_package(self, addr: Remote):
        pass

    def emit(self, handle_type: HandlerType, peer: Peer, *args: Any, **kwargs: Any) -> Awaitable:
        pass

    def on(self, handler_type: HandlerType) -> Callable[[Callable], Callable]:
        pass

    def package(self, peer: Peer, package: Package) -> Any:
        pass

    def on_package(self, peer: Peer, receiver: Callable[[], Awaitable], prepend: bool = False):
        pass


class UDPLayer(IConnectionLayer, ABC):
    def __init__(self, addr: Remote, timeout: timedelta = timedelta(seconds=5), loop: asyncio.AbstractEventLoop = None):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self.timeout = timeout
        self.addr = addr
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self._running = False
        self.peers: dict[PeerIdentifier, Peer] = {}
        self._receivers: dict[Peer, deque[Callable[[], Awaitable]]] = {}
        self._handlers: dict[HandlerType, deque[Callable[[], Awaitable] | Callable[[...], Awaitable]]] = {}
        self.fut: Optional[Future] = None
        self.processors: list[Coroutine] = []
        self.tasks = Queue(maxsize=40)
        self.data_queues: dict[Remote, asyncio.StreamReader] = {}
        self.awaitable = []

    @property
    @abstractmethod
    def type(self) -> PeerType:
        pass

    def on_package(self, peer: Peer, receiver: Callable[[], Awaitable], prepend: bool = False):
        receivers = self._receivers.get(peer, deque())
        if prepend:
            receivers.appendleft(receiver)
        else:
            receivers.append(receiver)

    def on(self, handler_type: HandlerType):
        def _wrapper(func: Callable[[], Awaitable]):
            self._handlers.setdefault(handler_type, deque())
            self._handlers[handler_type].append(func)
            return func

        return _wrapper

    def on_handshake(self, func: Callable[[], Awaitable]):
        return self.on('handshake')(func)

    def on_disconnect(self, func: Callable[[], Awaitable]):
        return self.on('disconnect')(func)

    def emit(self, handle_type: HandlerType, peer: Peer, *args: Any, **kwargs: Any) -> Awaitable:
        _cv_peer.set(peer)
        handlers = self._handlers.get(handle_type, ())
        return asyncio.gather(*(handler(*args, **kwargs) for handler in handlers))

    def package(self, peer: Peer, package: Package) -> Awaitable:
        receivers = self._receivers.get(peer, deque())
        return asyncio.gather(*(receiver() for receiver in receivers))

    def _add_task(self, task: Task | Future):
        return self.tasks.put(task)

    def _add_processor(self, coro: Coroutine):
        self.processors.append(coro)

    def _task(self, coro: Coroutine):
        task = asyncio.create_task(coro)
        return self._add_task(task)

    async def _process4one(self, remote: Remote):
        io = self.data_queues[remote]

        peer = Peer(self, addr=remote)
        _cv_peer.set(peer)

        pack_bytes = await asyncio.wait_for(io.readuntil(b'\xff'), self.timeout.total_seconds() * 2)

        package = Package.from_bytes(pack_bytes, remote)
        _cv_package.set(package)

        match package.pack_type:
            case PackageType.handshake:
                await self._add_task(peer.to_handshake(package))
            case PackageType.peer_disconnected:
                await self._add_task(peer.to_disconnect())
            case PackageType.heartbeat:
                peer.update_heartbeat()
                logger.trace("Heartbeat from {}", pack_addr(remote))
            case _:
                await self.package(peer, package)
        await asyncio.sleep(0)

    @property
    def peer(self) -> BoundedPeer:
        return partial(Peer, self)

    async def _peer_data(self, remote: Remote):
        try:
            await self._process4one(remote)
        except TimeoutError:
            await self.peer(addr=remote).timeout()

    def _batch_process(self):
        cnt = 0
        tasks = deque()
        for remote in tuple(self.data_queues.keys()):
            if cnt > QUEUE_SIZE_PER_REMOTE:
                cnt = 0
                yield from tuple(tasks)
                tasks.clear()
            tasks.append(self._peer_data(remote))
            cnt += 1
        if len(tasks) != 0:
            yield from tuple(tasks)

    async def handle(self):
        while not self.fut.done():
            await asyncio.gather(*self._batch_process())
            await asyncio.sleep(0)

    async def _data(self, initial=b''):
        buffer = initial
        last_addr = None
        sz = 0

        while sz < MAX_PACK_SIZE and not buffer.endswith(b'\xff'):
            try:
                data, addr = self.socket.recvfrom(4096)
                sz += len(data)
                if last_addr is None or last_addr == addr:
                    buffer += data
                    last_addr = addr
                else:
                    await self._task(self._data(data))
                    continue
            except socket_error:
                await asyncio.sleep(0.1)
                continue

        if not last_addr:
            return

        reader = self.data_queues.get(last_addr)
        if not reader:
            reader = self.data_queues[last_addr] = asyncio.StreamReader(loop=self.loop)
        reader.feed_data(buffer)

    def _handle(self):
        if not self.tasks.full():
            self.tasks.put_nowait(self._data())
        asyncio.get_event_loop().create_task(self._data())

    async def send_package(self, package: Package, addr: Remote):
        await self.loop.sock_sendto(self.socket, package.encode(), addr)

    def send_all(self, package: Package):
        data = package.encode()
        return asyncio.gather(
            *(self.loop.sock_sendto(self.socket, data, client.addr) for client in self.peers.values())
        )

    async def heartbeat(self):
        while not self.fut.done():
            await self.send_all(Package(
                PackageType.heartbeat, random.randint(0, 255)
            ))
            await asyncio.sleep(self.timeout.total_seconds() / 2)

    async def accept(self):
        if self._running:
            return
        self._running = True
        self.loop.add_reader(self.socket, self._handle)

    @abstractmethod
    async def initialize(self):
        pass

    async def _initial_task(self):
        self.socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.socket.setblocking(False)
        self.fut = self.loop.create_future()

        await self.accept()
        await self.initialize()
        self._add_processor(self.handle())
        self._add_processor(self.heartbeat())
        await self.process()

    async def process(self):
        async with asyncio.TaskGroup() as tg:
            for coro in self.processors:
                tg.create_task(coro)

    def close(self):
        if not self.fut:
            return
        self.fut.set_result(True)

    def start(self) -> Task:
        return asyncio.create_task(self._initial_task())

    def run(self):
        return self.start()


class UDPServer(UDPLayer):
    def bind(self):
        self.socket.bind(self.addr)

    @property
    def type(self) -> PeerType:
        return PeerType.client

    async def initialize(self):
        self.bind()


class UDPClient(UDPLayer):
    def __init__(
            self, addr: Remote,
            timeout: timedelta = timedelta(seconds=5),
            loop: asyncio.AbstractEventLoop = None
    ):
        super().__init__(addr, timeout, loop)

    @property
    def type(self) -> PeerType:
        return PeerType.client

    async def initialize(self):
        await self.send_package(Package(PackageType.handshake, self.type), self.addr)
        self.on_handshake(self.handshake)

    async def handshake(self, peer: Peer, package: Package) -> None:
        logger.info("Handshake")
