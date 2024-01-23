#  Copyright (c) Cyan Changes 2024. All rights reserved.
from typing import Any

from pydantic.fields import ModelField

from exceptions import SkippedException


class TypeMismatchError(SkippedException):
    def __init__(self, param: ModelField, value: Any) -> None:
        self.param: ModelField = param
        self.value: Any = value

    def __repr__(self) -> str:
        return (
            f"TypeMisMatch(param={self.param.name}, "
            f"type={self.param._type_display()}, value={self.value!r}>"
        )
