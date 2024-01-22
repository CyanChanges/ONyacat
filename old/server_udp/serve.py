#  Copyright (c) Cyan Changes 2024. All rights reserved.

import asyncio
import sys
from asyncio import CancelledError, AbstractEventLoop
from socket import socket, SO_REUSEADDR, SOL_SOCKET, SOCK_DGRAM, AF_INET

import server_udp.handler as handler
from hmr import hmr
from log import logger
from server_udp.socks_utils import receiver
import structures
from util import pack

structures = hmr(structures)

handler = hmr(handler)


async def accept(sock: socket, addr: structures.Remote, buf: bytes):
    loop = asyncio.get_event_loop()
    _ = loop.create_task(handler.recv_data())


async def listen(sock: socket):
    await receiver(sock, accept)


async def serve(host: str, port: int = 5100):
    loop = asyncio.new_event_loop()
    s = socket(AF_INET, SOCK_DGRAM)
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    s.bind((host, port))
    task = asyncio.create_task(listen(s))

    s.setblocking(False)
    logger.info(f"Listening on {host}:{port}")
    try:
        await task
    except CancelledError:
        logger.info(f"Broadcast to clients...")
        await loop.sock_sendall(s, pack(structures.PackageType.peer_disconnected, structures.ClientType.server))
        raise


def main(host="0.0.0.0", port=5100):
    loop = asyncio.get_event_loop()
    try:
        sys.exit(loop.run_until_complete(serve(host, port)))
    except KeyboardInterrupt:
        logger.info("Attempting graceful shutdown, press Ctrl+C again to force exit…", flush=True)

        # Do not show `asyncio.CancelledError` exceptions during shutdown
        # (a lot of these may be generated, skip this if you prefer to see them)
        def shutdown_exception_handler(loop: AbstractEventLoop, context: Any):
            if "exception" not in context or not isinstance(
                    context["exception"], asyncio.CancelledError
            ):
                loop.default_exception_handler(context)

        loop.set_exception_handler(shutdown_exception_handler)

        # Handle shutdown gracefully by waiting for all tasks to be cancelled
        tasks = asyncio.gather(
            *asyncio.all_tasks(loop=loop), return_exceptions=True
        )
        tasks.add_done_callback(lambda t: loop.stop())
        tasks.cancel()

        # Keep the event loop running until it is either destroyed or all
        # tasks have really terminated
        while not tasks.done() and not loop.is_closed():
            loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.success("Server stopped")


if __name__ == "__main__":
    main()
