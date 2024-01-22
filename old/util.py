#  Copyright (c) Cyan Changes 2024. All rights reserved.

from functools import cache
from typing import Sequence
from log import logger

from structures import PackageType, Remote

ENDING = b'\xff'


@cache
def pack(pack_type: PackageType, data: bytes | Sequence[bytes]) -> bytes:
    if isinstance(data, bytes):
        data = [data]
    return (bytes([pack_type]) + b''.join(data)) + ENDING


@cache
def pack_addr(addr: Remote) -> bytes:
    return ('{0}:{1}'.format(*addr)).encode('u8')


@cache
def unpack(data: bytes) -> tuple[PackageType, int | bytes]:
    try:
        pack_type = PackageType(data[0])
    except ValueError:
        logger.warning(f"Invalid package type: {data[0]}")
        raise

    return pack_type, data[1:-1]
