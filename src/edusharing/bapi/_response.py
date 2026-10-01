"""Checks shared by the proxy and template response parsers.

Errors name the field, never its value: gateway data can contain private text.
These checks do not infer a decision or an input/vector association.
"""

from __future__ import annotations

import math
from typing import Any

from ..errors import EduSharingError


def _invalid(route: str, field: str, expected: str) -> EduSharingError:
    return EduSharingError(
        f"The b-api /{route} response has invalid {field}: expected {expected}.")


def _object(value: Any, route: str, field: str = "response") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(route, field, "an object")
    return value


def _items(value: Any, route: str, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _invalid(route, field, "a list")
    return value


def _text(value: Any, route: str, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _invalid(route, field, "text or null")
    return value


def _boolean(value: Any, route: str, field: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid(route, field, "an explicit boolean")
    return value


def _whole(value: Any, route: str, field: str) -> int:
    # ``type`` rather than ``isinstance``: ``True`` is an int to Python and a
    # boolean to the sender.
    if type(value) is not int:
        raise _invalid(route, field, "a whole number")
    return value


def _number(value: Any, route: str, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(route, field, "a finite number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise _invalid(route, field, "a finite number") from exc
    if not math.isfinite(result):
        raise _invalid(route, field, "a finite number")
    return result


def _vectors(answer: dict[str, Any], count: int) -> list[list[float]]:
    entries = _items(answer.get("data"), "embeddings", "data")
    if len(entries) != count:
        raise _invalid("embeddings", "data", f"one vector per input ({count})")
    indexed: dict[int, list[float]] = {}
    dimensions = 0
    for position, item in enumerate(entries):
        field = f"data[{position}]"
        entry = _object(item, "embeddings", field)
        index = entry.get("index")
        if (type(index) is not int or not 0 <= index < count or index in indexed):
            raise _invalid("embeddings", f"{field}.index", "unique input indices")
        vector = _items(entry.get("embedding"), "embeddings", f"{field}.embedding")
        if not vector or (dimensions and len(vector) != dimensions):
            raise _invalid("embeddings", f"{field}.embedding", "non-empty vectors of equal length")
        dimensions = len(vector)
        indexed[index] = [_number(v, "embeddings", f"{field}.embedding[{i}]")
                          for i, v in enumerate(vector)]
    return [indexed[i] for i in range(count)]
