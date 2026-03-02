from abc import ABC, abstractmethod
from typing import Any


class DriverValidationResult(dict):
    pass


class DriverBase(ABC):
    name: str

    @abstractmethod
    def validate(self, spec: dict[str, Any], context: dict[str, Any]) -> DriverValidationResult:
        raise NotImplementedError

    @abstractmethod
    def render_runtime(
        self,
        spec: dict[str, Any],
        left_public_key: str,
        right_public_key: str,
    ) -> dict[str, str]:
        raise NotImplementedError
