"""Quality Agent 출력 형식."""
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class QualityReport:
    risk_level: RiskLevel
    ra_estimated_um: float
    basis_edge: int  # 판단 기준이 된 날 (가장 많이 마모된 날)
    basis_vb_mm: float
    reasons: list[str] = field(default_factory=list)
