#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
from typing import Optional

from loguru import logger

from functools import partial

from config import ServerConfig
from layer import UDPServer, UDPLayer
from structures import PeerType, Remote, Package, PackageType, Peer
from util import pack_addr
from valued_event import ValuedEvent
from globals import peer, package

# csharp_addr: Optional[Remote] = None
csharp_event = ValuedEvent()


async def on_csharp_package():
    logger.info(f'package received {package}')


async def on_client_package():
    pass


async def on_disconnect():
    logger.info('{} disconnect', peer)


async def on_heartbeat():
    logger.trace(f'heartbeat received {peer}')


async def on_handshake():
    global csharp_event
    server = peer.layer
    logger.info('{} handshake'.format(peer, *peer.addr))
    await server.send_package(Package(PackageType.handshake, [PeerType.server, pack_addr(peer.addr)]), peer.addr)
    if peer == PeerType.client:
        await csharp_event.wait()
        server.on_package(peer, partial(on_client_package, server))
    else:
        csharp_event.set(peer.addr)
        server.on_package(peer, partial(on_csharp_package, server))


async def main(config: ServerConfig):
    logger.info("Listening on {}:{}", config.bind.host, config.bind.port)
    server = UDPServer((config.bind.host, config.bind.port))
    server.on_handshake(on_handshake)
    server.on_disconnect(on_disconnect)
    server.on_heartbeat(on_heartbeat)
    await server.run()
