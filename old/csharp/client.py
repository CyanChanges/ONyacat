#  Copyright (c) Cyan Changes 2024. All rights reserved.

import asyncio
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_REUSEADDR

from csharp.socks_utils import receiver
from hmr import hmr
import csharp.handler as handler
from structures import Remote

handler = hmr(handler)


async def accept(sock: socket, addr: Remote, buf: bytes):
    loop = asyncio.get_event_loop()
    _ = loop.create_task(handler.recv_data())


async def listen(sock: socket):
    await receiver(sock, accept)


async def main(host: str, port: int = 5100):
    server = socket(AF_INET, SOCK_DGRAM)
    server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    await handler.recv_data()
