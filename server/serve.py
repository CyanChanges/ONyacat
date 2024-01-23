#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
from typing import Optional

from loguru import logger

from functools import partial
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
    logger.warning('{} disconnect', peer)


async def handshake():
    global csharp_event
    server = peer.layer
    logger.info('{} peer from {}:{}'.format(peer.type.name, *peer.addr))
    await server.send_package(Package(PackageType.handshake, [PeerType.server, pack_addr(peer.addr)]), peer.addr)
    if peer == PeerType.client:
        await csharp_event.wait()
        server.on_package(peer, partial(on_client_package, server))
    else:
        csharp_event.set(peer.addr)
        server.on_package(peer, partial(on_csharp_package, server))


async def main(host: str = '0.0.0.0', port: int = 5100):
    logger.info("Listening on {}:{}", host, port)
    server = UDPServer((host, port))
    server.on_handshake(handshake)
    await server.run()
