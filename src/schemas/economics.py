"""Economics / Production Agent 입출력 형식."""
from dataclasses import dataclass, field

from src.schemas.decision import Action
from src.schemas.quality import RiskLevel


@dataclass
class ProductionContext:
    """생산·비용 상황. data/reference/의 시뮬레이션 시나리오 또는 사용자 입력값 (실제 기업 데이터 아님)."""

    scenario_id: str
    # Economic_Context_Sim
    tool_price: float  # 원
    change_time_min: float  # 공구 교체에 걸리는 시간
    downtime_cost_per_min: float  # 설비 정지 비용 (원/분)
    part_value: float  # 부품 1개 가치 (원)
    tool_stock: int  # 여분 공구 재고
    # Production_Context_Sim
    remaining_parts: int  # 현재 공정에서 남은 가공 수량
    process_progress_pct: float  # 현재 공정 진행률
    due_slack_min: float  # 납기 여유 시간
    production_priority: str  # "Low" / "High"
    inspection_available: bool  # 현장 검사 가능 여부

    @property
    def immediate_change_cost(self) -> float:
        return self.tool_price + self.change_time_min * self.downtime_cost_per_min

    @property
    def remaining_production_value(self) -> float:
        return self.part_value * self.remaining_parts


@dataclass
class EconomicsReport:
    cost_replace_now: float
    cost_replace_after_job: float
    cost_continue: float
    production_pressure: RiskLevel
    tool_available: bool
    inspection_available: bool
    recommended: Action  # 비용만 놓고 봤을 때 가장 싼 행동
    reasons: list[str] = field(default_factory=list)
