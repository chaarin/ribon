"""현장 검사 결과 형식."""
from dataclasses import dataclass


@dataclass
class InspectionResult:
    tool_id: str
    edge_id: int
    vb_measured_mm: float
    ra_measured_um: float | None = None
