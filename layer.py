#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
import random
from abc import ABC, abstractmethod
from asyncio import Task, Future, Queue, QueueEmpty
from collections import deque
from datetime import timedelta
from functools import partial
from io import BytesIO
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR, error as socket_error
from typing import Protocol, Callable, Awaitable, Any, Literal, Optional, Coroutine

from more_itertools import iter_except, take, first_true

from log import logger
from structures import Remote, Package, PackageType, Peer, PeerType, PeerIdentifier, PeerMeta, BoundedPeer
from util import pack_addr

HandlerType = Literal["handshake"] | Literal['disconnect']

QUEUE_SIZE_PER_REMOTE = 10


class IConnectionLayer(Protocol):
    peers: dict[PeerIdentifier, Peer]
    data_queues: Optional[dict[Remote, asyncio.StreamReader]]
    timeout: timedelta

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

    def on_package(self, peer: Peer, receiver: Callable[[Peer, Package], Awaitable], prepend: bool = False):
        pass


class UDPLayer(IConnectionLayer, ABC):
    def __init__(self, addr: Remote, timeout: timedelta = timedelta(seconds=5), loop: asyncio.AbstractEventLoop = None):
        self.loop = asyncio.get_running_loop() if loop is None else loop
        self.timeout = timeout
        self.addr = addr
        self.socket = socket(AF_INET, SOCK_DGRAM)
        self._running = False
        self.peers: dict[PeerIdentifier, Peer] = {}
        self._receivers: dict[Peer, deque[Callable[[Peer, Package], Awaitable]]] = {}
        self._handlers: dict[HandlerType, deque[Callable[[Peer], Awaitable] | Callable[[Peer, ...], Awaitable]]] = {}
        self.fut: Optional[Future] = None
        self.tasks = Queue(maxsize=40)
        self.data_queues: dict[Remote, asyncio.StreamReader] = {}
        self.awaitable = []

    def on_package(self, peer: Peer, receiver: Callable[[Peer, Package], Awaitable], prepend: bool = False):
        receivers = self._receivers.get(peer, deque())
        if prepend:
            receivers.appendleft(receiver)
        else:
            receivers.append(receiver)

    def on(self, handler_type: HandlerType):
        def _wrapper(func: Callable[[Peer], Awaitable]):
            self._handlers.setdefault(handler_type, deque())
            self._handlers[handler_type].append(func)
            return func

        return _wrapper

    def on_handshake(self, func: Callable[[Peer], Awaitable]):
        return self.on('disconnect')(func)

    def on_disconnect(self, func: Callable[[Peer], Awaitable]):
        return self.on('disconnect')(func)

    def emit(self, handle_type: HandlerType, peer: Peer, *args: Any, **kwargs: Any) -> Awaitable:
        handlers = self._handlers.get(handle_type, ())
        return asyncio.gather(*(handler(peer, *args, **kwargs) for handler in handlers))

    def package(self, peer: Peer, package: Package) -> Awaitable:
        receivers = self._receivers.get(peer, deque())
        return asyncio.gather(*(receiver(peer, package) for receiver in receivers))

    def _add_task(self, task: Task):
        return self.tasks.put(task)

    def _task(self, coro: Coroutine):
        task = asyncio.create_task(coro)
        return self._add_task(task)

    async def _process4one(self, remote: Remote):
        io = self.data_queues[remote]
        pack_bytes = await asyncio.wait_for(io.readuntil(b'\xff'), self.timeout.total_seconds() * 2)
        package = Package.from_bytes(pack_bytes, remote)
        peer = Peer(self, addr=remote)
        match package.pack_type:
            case PackageType.handshake:
                peer.handshake(package)
            case PackageType.peer_disconnected:
                peer.disconnect()
            case PackageType.heartbeat:
                peer.heartbeat()
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

    def _batch_tasks(self):
        cnt = 0
        tasks = deque()
        for remote in tuple(self.data_queues.keys()):
            if cnt > QUEUE_SIZE_PER_REMOTE:
                yield tasks
                tasks.clear()
            tasks.append(remote)
            cnt += 1

    async def process(self):
        while True:
            await asyncio.gather(*self._batch_tasks())

    async def recv_data(self, initial=b''):
        buffer = initial
        last_addr = None
        while not buffer.endswith(b'\xff'):
            try:
                data, addr = self.socket.recvfrom(4096)
                if last_addr is None or last_addr == addr:
                    buffer += data
                    last_addr = addr
                else:
                    await self._task(self.recv_data(data))
                    continue
            except socket_error:
                break

        reader = self.data_queues.get(last_addr)
        if not reader:
            reader = self.data_queues[last_addr] = asyncio.StreamReader(loop=self.loop)
        reader.feed_data(buffer)

    def _handle(self):
        if not self.tasks.full():
            self.tasks.put_nowait(self.recv_data())
        asyncio.get_event_loop().create_task(self.recv_data())

    async def send_package(self, package: Package, addr: Remote):
        await self.loop.sock_sendto(self.socket, package.encode(), addr)

    def send_all(self, package: Package):
        data = package.encode()
        return asyncio.gather(
            *(self.loop.sock_sendto(self.socket, data, client.addr) for client in self.peers.values()))

    async def heartbeat(self):
        while True:
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
        await self._task(self.process())
        await self._task(self.heartbeat())
        await self.accept()
        await self.initialize()

    def close(self):
        if self.fut:
            return
        self.fut.set_result(True)

    def start(self) -> Task:
        return asyncio.create_task(self._initial_task())

    async def run(self):
        await self.start()
        tasks = deque()
        while not self.fut.done():
            if not self.tasks.empty():
                await asyncio.gather(*(take(10, iter_except(lambda: self.tasks.get_nowait(), QueueEmpty))))
            else:
                await asyncio.sleep(0)


class UDPServer(UDPLayer):
    def bind(self):
        self.socket.bind(self.addr)

    async def initialize(self):
        self.bind()


class UDPClient(UDPLayer):
    def __init__(
            self, addr: Remote, peer_type: PeerType,
            timeout: timedelta = timedelta(seconds=5),
            loop: asyncio.AbstractEventLoop = None
    ):
        self.type = peer_type
        super().__init__(addr, timeout, loop)

    async def initialize(self):
        await self.send_package(Package(PackageType.handshake, self.type), self.addr)
        self.on_handshake(self.handshake)

    async def handshake(self, addr: Remote, peer_type: PeerType) -> None:
        logger.info("Handshake")
