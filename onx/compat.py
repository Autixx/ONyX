from __future__ import annotations

try:
    from enum import StrEnum as StrEnum  # Python 3.11+
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass


def enum_values(enum_cls):
    return [item.value for item in enum_cls]


def enum_names(enum_cls):
    return [item.name for item in enum_cls]
