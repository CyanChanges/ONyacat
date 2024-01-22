#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
import sys
from asyncio import AbstractEventLoop
from typing import Literal, Any

from loguru import logger


def main(type: Literal['server'] | Literal['client'] = 'server', host="0.0.0.0", port=5100):
    if type == "server":
        from server.serve import main
    else:
        from csharp.serve import main
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(
        lambda _, data: logger.opt(exception=data.get('exception')).warning('Error', data)
    )
    try:
        sys.exit(loop.run_until_complete(main(host, port)))
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


main()
