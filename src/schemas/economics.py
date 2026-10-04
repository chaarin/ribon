"""Economics / Production Agent 입출력 형식.

손실은 금액이 아니라 **가공 시간(분)**으로 계산한다. 부품 가격처럼 근거 없는 값을 쓰지 않기 위해서다.
"""
from dataclasses import dataclass, field

from src.schemas.decision import Action
from src.schemas.quality import RiskLevel


@dataclass
class ProductionContext:
    """생산 상황. data/reference/의 시뮬레이션 시나리오, 시연 프리셋, 또는 사용자 입력값 (실제 기업 데이터 아님)."""

    scenario_id: str
    # Economic_Context_Sim
    tool_price: float  # 원 (판단에는 쓰지 않고, 결과의 공구 사용량 환산에만 쓴다)
    change_time_min: float  # 공구 교체에 걸리는 시간
    downtime_cost_per_min: float  # 설비 정지 비용 (원/분, 손실 시간을 금액으로 바꿀 때만 사용)
    part_value: float  # 원 (윙 리브로 부품을 고정해 판단에는 쓰지 않음)
    tool_stock: int  # 여분 공구 재고
    # Production_Context_Sim
    remaining_parts: int  # 남은 윙 리브 수 (지금 가공 중인 것 포함)
    process_progress_pct: float  # 지금 가공 중인 윙 리브의 진행률
    due_slack_min: float  # 납기 여유 시간 (계획된 작업을 마치고 남는 시간으로 해석)
    production_priority: str  # "Low" / "High"
    inspection_available: bool  # 현장 검사 가능 여부
    # 시연 프리셋에서 추가
    tool_purpose: str = "finishing"  # "finishing"(정삭) / "roughing"(황삭)
    name: str = ""  # 화면 표시용 이름


@dataclass
class EconomicsReport:
    loss_replace_now_min: float  # 지금 교체할 때의 기대 손실 시간
    loss_replace_after_rib_min: float  # 이 윙 리브를 끝내고 교체할 때
    loss_continue_min: float  # 교체하지 않고 이 윙 리브를 끝까지 가공할 때 (교체 시간은 뒤로 미룸)
    cycles_left_in_rib: int
    delay_if_replace_now_min: float  # 지금 교체하면 납기를 넘기는 시간 (0이면 지연 없음)
    next_rib_risk_min: float  # 다음 윙 리브 전체를 지금 공구로 가공할 때의 추가 불량 위험 (윙 리브 경계에서 교체 판단용)
    inspection_value_min: float  # 4날 검사로 얻는 정보의 가치 = 주의 구간일 확률 × 그때 막을 수 있는 불량 손실
    inspection_time_min: float
    production_pressure: RiskLevel
    tool_available: bool
    inspection_available: bool
    recommended: Action  # 손실 시간만 놓고 봤을 때 가장 작은 행동
    reasons: list[str] = field(default_factory=list)
