from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class FlowContext:
    apis: Dict[str, Any]
    operator_ns: str
    namespace: Optional[str]
    vars: Dict[str, str] = field(default_factory=dict)
