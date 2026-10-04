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
    basis_edge: int  # 판단 기준이 된 날 (가장 많이 마모된 날)
    basis_vb_mm: float
    caution_vb_mm: float = 0.2  # 이 공구 용도의 주의 구간 시작 (MEDIUM 경계)
    tool_purpose: str = "finishing"
    drivers: list[str] = field(default_factory=list)  # 등급을 결정한 요인 (VB 구간, 편마모, 급속 마모)
    reference_ra_range_um: tuple[float, float] | None = None  # 참조 논문에서 비슷한 VB의 Ra 범위 (참고용)
    reasons: list[str] = field(default_factory=list)
