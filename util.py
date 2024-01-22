#  Copyright (c) Cyan Changes 2024. All rights reserved.
import struct
from functools import cache
from typing import TYPE_CHECKING, AnyStr
from ctypes import sizeof, c_int, c_long, c_size_t

if TYPE_CHECKING:
    from structures import Remote

ENDING = b'\xff'


def data_pack(data_type: AnyStr | int):
    buffer = b''
    if isinstance(data_type, bytes):
        buffer += data_type
    elif isinstance(data_type, str):
        buffer += data_type.encode('u8')
    elif isinstance(data_type, int):
        if 0 <= data_type <= 255:
            buffer += data_type.to_bytes()
        elif 255 <= data_type <= 2**sizeof(c_int):
            buffer += struct.pack('i', data_type)
        elif 255 <= data_type <= 2**sizeof(c_long):
            buffer += struct.pack('l', data_type)
        elif 255 <= data_type <= 2**sizeof(c_size_t):
            buffer += struct.pack('q', data_type)
        else:
            raise ValueError(f"{data_type} is too large to pack!")
    return buffer


@cache
def pack_addr(addr: "Remote") -> str:
    return '{0}:{1}'.format(*addr)


