#  Copyright (c) Cyan Changes 2024. All rights reserved.
from typing import Annotated, Generic, TypeVar

from pydantic import (
    BaseModel,
    Field,
    IPvAnyAddress
)


class PeerBaseConfig(BaseModel):
    enabled: bool = False


class BasicConfig(BaseModel):
    pass


T = TypeVar('T', bound=str)


class HostPortConfig(BaseModel, Generic[T]):
    host: Annotated[str, str | IPvAnyAddress]
    port: int = Field(gt=0, lt=65536, default=5100)


class ServerConfig(PeerBaseConfig):
    bind: HostPortConfig[IPvAnyAddress] = HostPortConfig(host='0.0.0.0', port=5100)
    peer_limit: int = Field(ge=0, default=None)


class CSharpConfig(PeerBaseConfig):
    server: HostPortConfig = HostPortConfig(host='r.cyans.me', port=5100)


class ClientConfig(PeerBaseConfig):
    server: HostPortConfig
