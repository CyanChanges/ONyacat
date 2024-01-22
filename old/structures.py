#  Copyright (c) Cyan Changes 2024. All rights reserved.
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import AnyStr

BASIC_PACK_SIZE = 2
Remote = tuple[str, int]


class PackageType(IntEnum):
    handshake = 0x0
    wave_hand = 0x1
    peer_connected = 0x2
    peer_disconnected = 0x3
    heartbeat = 0x4
    bad_package = 0x5
    timeout = 0x6
    service_temporary_unavailable = 0x7


class ClientType(IntEnum):
    csharp = 0x1
    client = 0x2
    server = 0x3


@dataclass
class Package:
    pack_type: PackageType
    data: AnyStr | bytes

    def encode(self, encoding: str = 'utf-8') -> bytes:
        data = self.data if isinstance(self.data, bytes) else self.data.encode(encoding)
        return struct.pack('csx', self.pack_type.value.to_bytes(), data)
