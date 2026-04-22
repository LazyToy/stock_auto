from __future__ import annotations

import math
import os
from typing import Callable, TypeVar

T = TypeVar("T", int, float)


def _read_env_number(name: str, default: T, parser: Callable[[str], T]) -> T:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = parser(raw_value)
        if parser is float and not math.isfinite(value):
            raise ValueError(raw_value)
        return value
    except ValueError as exc:
        raise ValueError(f"Invalid value for {name}: {raw_value!r}") from exc


def read_env_float(name: str, default: float) -> float:
    return _read_env_number(name, default, float)



def read_env_int(name: str, default: int) -> int:
    return _read_env_number(name, default, int)
