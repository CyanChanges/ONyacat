#  Copyright (c) Cyan Changes 2024. All rights reserved.
import inspect
from typing import Callable, Any, ForwardRef

from loguru import logger
from pydantic.typing import evaluate_forwardref
from pydantic.fields import ModelField

from dependencies.exceptions import TypeMismatchError


def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    """获取可调用对象签名"""

    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=get_typed_annotation(param, globalns),
        )
        for param in signature.parameters.values()
    ]
    return inspect.Signature(typed_params)


def get_typed_annotation(param: inspect.Parameter, globalns: dict[str, Any]) -> Any:
    """获取参数的类型注解"""

    annotation = param.annotation
    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        try:
            annotation = evaluate_forwardref(annotation, globalns, globalns)
        except Exception as e:
            logger.opt(colors=True, exception=e).warning(
                f'Unknown ForwardRef["{param.annotation}"] for parameter {param.name}'
            )
            return inspect.Parameter.empty
    return annotation


def check_field_type(field: ModelField, value: Any) -> Any:
    """检查字段类型是否匹配"""

    v, errs_ = field.validate(value, {}, loc=())
    if errs_:
        raise TypeMismatchError(field, value)
    return v
