#  Copyright (c) Cyan Changes 2024. All rights reserved.
import asyncio
import inspect
import struct
from contextvars import copy_context
from functools import cache, partial, wraps
from typing import TYPE_CHECKING, AnyStr, ParamSpec, TypeVar, Callable, Coroutine, Any
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
        elif 255 <= data_type <= 2 ** sizeof(c_int):
            buffer += struct.pack('i', data_type)
        elif 255 <= data_type <= 2 ** sizeof(c_long):
            buffer += struct.pack('l', data_type)
        elif 255 <= data_type <= 2 ** sizeof(c_size_t):
            buffer += struct.pack('q', data_type)
        else:
            raise ValueError(f"{data_type} is too large to pack!")
    return buffer


@cache
def pack_addr(addr: "Remote") -> str:
    return '{0}:{1}'.format(*addr)


P = ParamSpec("P")
R = TypeVar("R")


def run_sync(call: Callable[P, R]) -> Callable[P, Coroutine[None, None, R]]:
    """一个用于包装 sync function 为 async function 的装饰器

    参数:
        call: 被装饰的同步函数
    """

    @wraps(call)
    async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        loop = asyncio.get_running_loop()
        pfunc = partial(call, *args, **kwargs)
        context = copy_context()
        result = await loop.run_in_executor(None, partial(context.run, pfunc))
        return result

    return _wrapper


def is_coroutine_callable(call: Callable[..., Any]) -> bool:
    """检查 call 是否是一个 callable 协程函数"""
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    func_ = getattr(call, "__call__", None)
    return inspect.iscoroutinefunction(func_)
