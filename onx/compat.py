from __future__ import annotations

try:
    from onx.compat import StrEnum as StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


def enum_values(enum_cls):
    return [item.value for item in enum_cls]


def enum_names(enum_cls):
    return [item.name for item in enum_cls]
