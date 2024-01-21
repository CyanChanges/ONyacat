import asyncio
from asyncio import AbstractEventLoop, TaskGroup
from socket import socket, SOL_SOCKET, SO_KEEPALIVE

from log import logger

from structures import ClientType, PackageType, BASIC_PACK_SIZE, Remote
from util import send_pack_async, abort_bad_package, recv_pack_async, abort_timeout, pack_addr
from valued_event import ValuedEvent

logger.debug('handler')

ip_event = ValuedEvent()


async def handle(sock: socket, initial: bytes, addr: Remote):
    logger.debug(f"New connection from {addr}")

    # handshake, get client type
    try:
        pack_type = PackageType(initial[0])
        assert pack_type == PackageType.handshake, f"failed to handshake. {pack_type}"
    except (ValueError, AssertionError) as e:
        logger.warning(f"Invalid package type: {e}")
        await abort_bad_package(sock, addr)
        return
    try:
        client_type = ClientType(initial[1])
    except ValueError as e:
        logger.warning(f"Invalid client type: {e}")
        await abort_bad_package(sock, addr)
        return

    logger.debug(f"Client type: {repr(client_type)}")

    # peer
    if client_type == ClientType.csharp:
        await send_pack_async(sock, addr, PackageType.handshake, pack_addr(addr))
        ip_event.set(addr)
    else:
        peer_addr = await ip_event.wait()
        await send_pack_async(sock, addr, PackageType.peer_connected, pack_addr(peer_addr))
        logger.success("{}<->{}", pack_addr(peer_addr).decode(), pack_addr(addr).decode())
        ip_event.clear()

    await keepalive(sock, addr, client_type)


async def keepalive(sock: socket, addr: Remote, client_type: ClientType, loop: AbstractEventLoop = None) -> None:
    loop = asyncio.get_running_loop() if loop is None else loop
    async with TaskGroup() as tg:
        tg.create_task(heartbeat(sock, addr, loop=loop))
        tg.create_task(timeout(sock, addr, client_type, loop=loop))


async def heartbeat(sock: socket, addr: Remote, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    while True:
        await send_pack_async(sock, addr, PackageType.heartbeat, (1).to_bytes(), loop=loop)
        await asyncio.sleep(2)


async def timeout(sock: socket, addr: Remote, client_type: ClientType, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    while True:
        try:
            async with asyncio.timeout(3.5):
                while True:
                    pack_type, data = await recv_pack_async(addr, loop)
                    if pack_type != PackageType.heartbeat:
                        continue
                    break
        except TimeoutError:
            await abort_timeout(sock, addr, loop=loop)
            if client_type == ClientType.csharp:
                ip_event.clear()
            logger.warning("{} timed out", addr)
            break
