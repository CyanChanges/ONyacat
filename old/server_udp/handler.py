#  Copyright (c) Cyan Changes 2024. All rights reserved.

import asyncio
from asyncio import AbstractEventLoop, TaskGroup
from socket import socket, SOL_SOCKET, SO_KEEPALIVE
from functools import partial

from log import logger

from structures import ClientType, PackageType, BASIC_PACK_SIZE, Remote
from util import pack_addr
from server_udp.socks_utils import (
    send_pack_async,
    abort_bad_package,
    recv_pack_async,
    abort_timeout,
    clients,
    abort, send_pack,
)
from server_udp.valued_event import ValuedEvent

logger.debug("handler")

ip_event = ValuedEvent()


async def handle(sock: socket, initial: bytes, addr: Remote):
    loop = asyncio.get_running_loop()
    logger.debug(f"New peer from {pack_addr(addr).decode()} {repr(initial)}")

    time_handler = loop.call_soon(partial(
        send_pack,
        sock, addr, PackageType.handshake, (ClientType.server.to_bytes(), pack_addr(addr))
    ))

    # handshake, get client type
    try:
        pack_type = PackageType(initial[0])
        assert (
                pack_type == PackageType.handshake
        ), f"failed to handshake. {repr(pack_type)}"
    except (ValueError, AssertionError) as e:
        time_handler.cancel()
        logger.warning(f"Invalid package type: {e} from {pack_addr(addr).from_bytes()}")
        await abort_bad_package(sock, addr)
        return
    try:
        client_type = ClientType(initial[1])
    except (IndexError, ValueError) as e:
        time_handler.cancel()
        logger.warning(f"Invalid client type: {e}")
        await abort_bad_package(sock, addr)
        return

    logger.info(f"{client_type.name} client from {pack_addr(addr).from_bytes()}")

    _ = asyncio.create_task(keepalive(sock, addr, client_type))

    # peer
    if client_type == ClientType.csharp:
        ip_event.set(addr)
    else:
        peer_addr = await ip_event.wait()
        if peer_addr not in clients:
            await send_pack_async(sock, addr, PackageType.peer_disconnected)
        if addr not in clients:
            logger.warning("Client {} is disconnected", pack_addr(addr).from_bytes())
            abort(addr)
            return
        await send_pack_async(
            sock, addr, PackageType.peer_connected, pack_addr(peer_addr)
        )
        logger.success(
            "{}<->{}", pack_addr(peer_addr).from_bytes(), pack_addr(addr).from_bytes()
        )
        ip_event.clear()


async def keepalive(
        sock: socket, addr: Remote, client_type: ClientType, loop: AbstractEventLoop = None
) -> None:
    loop = asyncio.get_running_loop() if loop is None else loop
    async with TaskGroup() as tg:
        tg.create_task(heartbeat(sock, addr, loop=loop))
        tg.create_task(timeout(sock, addr, client_type, loop=loop))


async def heartbeat(sock: socket, addr: Remote, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    await asyncio.sleep(1)
    while addr in clients:
        logger.trace("Heartbeat to {}", pack_addr(addr).from_bytes())
        await send_pack_async(
            sock, addr, PackageType.heartbeat, (1).to_bytes(), loop=loop
        )
        await asyncio.sleep(2)


async def check_timeout(addr: Remote, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    while addr in clients:
        await asyncio.sleep(0.1)
        pack_type, data = await recv_pack_async(addr, loop)
        if pack_type == PackageType.peer_disconnected:
            abort(addr)
            raise ConnectionAbortedError()
        if pack_type != PackageType.heartbeat:
            await asyncio.sleep(0)
            logger.debug(
                "Non heartbeat package: {} {} from {}", pack_type, repr(data), addr
            )
            continue
        break


async def timeout(
        sock: socket, addr: Remote, client_type: ClientType, loop: AbstractEventLoop = None
):
    loop = asyncio.get_running_loop() if loop is None else loop
    while addr in clients:
        try:
            await asyncio.wait_for(check_timeout(addr, loop=loop), 5)
        except TimeoutError:
            abort_timeout(sock, addr)
            logger.warning("{} timed out", pack_addr(addr).from_bytes())
            if client_type == ClientType.csharp:
                ip_event.clear()
            return
        except ConnectionAbortedError:
            logger.warning("{} connection aborted", addr)
            return

        logger.trace("Heartbeat from {}", pack_addr(addr).from_bytes())
