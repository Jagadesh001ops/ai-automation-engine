from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict

class NodeResult(BaseModel):
    success: bool
    output_key: str
    output_value: Any
    error: str = None

class BaseNode(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, state: Dict[str, Any]) -> NodeResult:
        pass

    def handle_failure(self, error: Exception) -> NodeResult:
        return NodeResult(
            success=False,
            output_key="error",
            output_value=None,
            error=str(error)
        )