#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
from asyncio import AbstractEventLoop
from pathlib import Path
from typing import Any
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import typer
from loguru import logger

from settings import Settings
from structures import PeerType

app = typer.Typer()

def run_peer(peer_type: PeerType, settings: Settings) -> None:
    match peer_type:
        case PeerType.server:
            from server.serve import main
        case PeerType.csharp:
            from csharp.serve import main
        case _:
            raise ValueError(f"{peer_type} is not supported yet")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(
        lambda _, data: logger.opt(exception=data.get('exception')).warning('Error', data)
    )

    try:
        logger.info(f"Running {peer_type.name}...")
        return loop.run_until_complete(main(getattr(settings, peer_type.name)))
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
        logger.info(f"worker-{peer_type.name} stopped")


@app.command('run')
def main():
    settings = Settings(Path(typer.get_app_dir('onyacat')) / 'config.toml')

    futures = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        if settings.server:
            futures.append(executor.submit(run_peer, PeerType.server, settings))
        if settings.csharp:
            futures.append(executor.submit(run_peer, PeerType.csharp, settings))

    # raise exceptions
    exceptions = [future.exception() for future in futures if future.exception()]
    if len(exceptions):
        raise ExceptionGroup('Exceptions during running', exceptions)



if __name__ == "__main__":
    typer.run(main)
