#  Copyright (c) Cyan Changes 2024. All rights reserved.

from contextvars import ContextVar
from typing import cast, TYPE_CHECKING

from contextlocal import LocalProxy

if TYPE_CHECKING:
    from structures import Peer, Package, Remote

_cv_peer: ContextVar["Peer"] = ContextVar('onlyacat233.peer')
_cv_package: ContextVar["Package"] = ContextVar('onlyacat233.package')
package = cast("Package", LocalProxy(
    _cv_package
))
peer = cast("Peer", LocalProxy(
    _cv_peer
))
remote = cast("Remote", LocalProxy(
    _cv_peer, name='addr'
))
