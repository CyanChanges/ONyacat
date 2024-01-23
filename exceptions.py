#  Copyright (c) Cyan Changes 2024. All rights reserved.
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from structures import Remote, Peer, PeerIdentifier
from util import pack_addr


class InvalidPacakgeError(Exception):
    def __init__(self, data: bytes, addr: Optional["Remote"] = None):
        super().__init__(f'Invalid package {data!r} from {pack_addr(addr) if addr else "unknown"}')


class NoSuchPeerError(Exception):
    def __init__(self, info: str, peer: Optional["Peer"] = None):
        super().__init__(f'No such client {info!r} in {peer!r}')

    @classmethod
    def addr(cls, addr: "Remote", peer: Optional["Peer"] = None):
        return cls(pack_addr(addr), peer)

    @classmethod
    def identifier(cls, identifier: "PeerIdentifier", peer: Optional["Peer"] = None):
        return cls(str(identifier), peer)


class SkippedException(Exception):
    pass

