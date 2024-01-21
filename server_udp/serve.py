import asyncio
import atexit
import sys
from signal import SIGINT, SIGILL, SIGTERM
from socket import socket, SO_REUSEADDR, SOL_SOCKET, SOCK_DGRAM, AF_INET

from log import logger
import server.handler as handler

from hmr import hmr
from structures import BASIC_PACK_SIZE, Remote
from util import receiver

handler = hmr(handler)

interrupt_handler = lambda: None


async def accept(sock: socket, addr: Remote, buf: bytes):
    loop = asyncio.get_event_loop()
    _ = loop.create_task(handler.handle(sock, buf, addr))


async def listen(sock: socket):
    await receiver(sock, accept)


async def serve(host: str, port: int = 5100):
    global interrupt_handler
    loop = asyncio.new_event_loop()
    s = socket(AF_INET, SOCK_DGRAM)
    s.bind((host, port))
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    task = asyncio.create_task(listen(s))

    def handler_interrupt(self, *args, **kwargs):
        print("Interrupt")
        task.cancel()
        task.exception()
        s.close()
        loop.close()

    interrupt_handler = type('InterruptHandler', (), {
        "__call__": handler_interrupt
    })()

    loop.add_signal_handler(SIGINT, interrupt_handler)
    loop.add_signal_handler(SIGILL, interrupt_handler)
    loop.add_signal_handler(SIGTERM, interrupt_handler)
    loop.set_exception_handler(interrupt_handler)
    s.setblocking(False)
    atexit.register(interrupt_handler)
    logger.success(f"Listening on {host}:{port}")
    await task


def main():
    loop = asyncio.get_event_loop()
    try:
        sys.exit(loop.run_until_complete(serve('0.0.0.0')))
    except KeyboardInterrupt as e:
        print("Attempting graceful shutdown, press Ctrl+C again to exit…", flush=True)

        # Do not show `asyncio.CancelledError` exceptions during shutdown
        # (a lot of these may be generated, skip this if you prefer to see them)
        def shutdown_exception_handler(loop, context):
            if "exception" not in context \
                    or not isinstance(context["exception"], asyncio.CancelledError):
                loop.default_exception_handler(context)

        loop.set_exception_handler(shutdown_exception_handler)

        # Handle shutdown gracefully by waiting for all tasks to be cancelled
        tasks = asyncio.gather(*asyncio.Task.all_tasks(loop=loop), loop=loop, return_exceptions=True)
        tasks.add_done_callback(lambda t: loop.stop())
        tasks.cancel()

        # Keep the event loop running until it is either destroyed or all
        # tasks have really terminated
        while not tasks.done() and not loop.is_closed():
            loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


main()
