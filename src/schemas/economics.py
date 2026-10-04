"""Economics / Production Agent 입출력 형식."""
from dataclasses import dataclass, field

from src.schemas.decision import Action
from src.schemas.quality import RiskLevel


@dataclass
class ProductionContext:
    """생산·비용 상황. MVP에서는 시뮬레이터 또는 사용자 입력값을 사용한다."""

    tool_price: float  # 원
    change_time_min: float  # 공구 교체에 걸리는 시간
    downtime_cost_per_min: float  # 설비 정지 비용 (원/분)
    part_value: float  # 부품 1개 가치 (원)
    remaining_parts: int  # 현재 공정(job)에서 남은 부품 수
    cycle_time_min: float  # 부품 1개 가공 시간
    tool_stock: int  # 교체용 공구 재고
    due_hours: float  # 납기까지 남은 시간
    breakage_cost: float  # 공구 파손 시 추가 손실 (부품·설비 손상 등)


@dataclass
class EconomicsReport:
    cost_replace_now: float
    cost_replace_after_job: float
    cost_continue: float
    production_pressure: RiskLevel
    tool_available: bool
    recommended: Action  # 비용만 놓고 봤을 때 가장 싼 행동
    reasons: list[str] = field(default_factory=list)
