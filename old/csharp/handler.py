#  Copyright (c) Cyan Changes 2024. All rights reserved.

import asyncio
from _socket import SO_REUSEADDR
from asyncio import AbstractEventLoop, TaskGroup
from socket import socket, SOL_SOCKET, SO_KEEPALIVE

from log import logger

from structures import ClientType, PackageType, BASIC_PACK_SIZE, Remote
from util import pack_addr, unpack
from socks_utils import send_pack_async, abort_bad_package, recv_pack_async, abort_timeout, clients, abort
from server_udp.valued_event import ValuedEvent

logger.debug('handler')

ip_event = ValuedEvent()


async def handle(sock: socket, addr: Remote):
    loop = asyncio.get_running_loop()
    logger.info("Connecting to server {}", pack_addr(addr).from_bytes())

    await send_pack_async(sock, addr, PackageType.handshake, ClientType.csharp.value.to_bytes())

    _ = asyncio.create_task(keepalive(sock, addr))

    pack_type, buf = await recv_pack_async(addr)
    assert pack_type == PackageType.handshake, 'failed to handshake'

    client = socket()
    ip, port = buf.decode('u8').split(':')
    client.bind((ip, int(port)))
    client.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    buf, addr = await loop.sock_recvfrom(client, 2048)
    pack_type, _ = unpack(buf)
    assert pack_type == PackageType.handshake, 'failed to handshake with client'
    while True:
        logger.debug("Start genshin impact")


async def reconnect(sock: socket, addr: Remote):
    _ = asyncio.create_task(handle(sock, addr))


async def keepalive(sock: socket, addr: Remote, loop: AbstractEventLoop = None) -> None:
    loop = asyncio.get_running_loop() if loop is None else loop
    async with TaskGroup() as tg:
        tg.create_task(timeout(sock, addr, loop=loop))


async def selector(sock: socket, addr: Remote, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    while addr in clients:
        await asyncio.sleep(0.1)
        pack_type, data = await recv_pack_async(addr, loop)
        match pack_type:
            case PackageType.heartbeat:
                if addr in clients:
                    await abort_bad_package(sock, addr)
                else:
                    await send_pack_async(sock, addr, PackageType.heartbeat)
            case PackageType.peer_disconnected:
                raise ConnectionAbortedError()
            case PackageType.timeout:
                raise TimeoutError()
            case PackageType.handshake:
                pass
            case PackageType.bad_package:
                logger.warning("RTG Bad package: {}", repr(data))
        break


async def timeout(sock: socket, addr: Remote, loop: AbstractEventLoop = None):
    loop = asyncio.get_running_loop() if loop is None else loop
    while addr in clients:
        try:
            await asyncio.wait_for(selector(sock, addr, loop=loop), 5)
        except (TimeoutError, ConnectionAbortedError):
            await reconnect(sock, addr)
            logger.warning("{} connection aborted", addr)
            return

        logger.trace("Heartbeat from {}", pack_addr(addr).from_bytes())
