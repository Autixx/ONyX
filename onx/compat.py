from __future__ import annotations

try:
    from onx.compat import StrEnum as StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        pass
