from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict, Optional
import time


class NodeResult(BaseModel):
    success: bool
    output_key: str
    output_value: Any
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class BaseNode(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def _execute(self, state: Dict[str, Any]) -> NodeResult:
        pass

    def execute(self, state: Dict[str, Any]) -> NodeResult:
        start = time.time()
        try:
            result = self._execute(state)
        except Exception as e:
            return self.handle_failure(e)
        result.execution_time_ms = round((time.time() - start) * 1000, 2)
        return result

    def handle_failure(self, error: Exception) -> NodeResult:
        return NodeResult(
            success=False,
            output_key="error",
            output_value=None,
            error=str(error)
        )