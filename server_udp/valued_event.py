from asyncio import Event
from typing import Generic, TypeVar

T = TypeVar('T')


class ValuedEvent(Event, Generic[T]):
    def __init__(self):
        super().__init__()
        self._value = None

    def set(self, value: T):
        if not self._value:
            self._value = value

            for fut in self._waiters:
                if not fut.done():
                    fut.set_result(self._value)

    def clear(self):
        """Reset the internal flag to false. Subsequently, coroutines calling
        wait() will block until set() is called to set the internal flag
        to true again."""
        self._value = None

    async def wait(self) -> T:
        """Block until the internal flag is true.

        If the internal flag is true on entry, return True
        immediately.  Otherwise, block until another coroutine calls
        set() to set the flag to true, then return True.
        """
        if self._value is not None:
            return self._value

        fut = self._get_loop().create_future()
        self._waiters.append(fut)
        try:
            return await fut
        finally:
            self._waiters.remove(fut)
