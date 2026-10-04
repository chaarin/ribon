"""공구 상태 형식. Memory가 관리하고 Agent들이 참조한다."""
from dataclasses import dataclass, field

from src.config.settings import N_EDGES


@dataclass
class EdgeState:
    edge_id: int
    vb_mm: float = 0.0
    raw_pred_mm: float = 0.0  # 마지막 보정 전 모델 예측값 (bias 계산용)
    uncertainty_mm: float = 0.0
    wear_rate_mm_min: float = 0.0
    bias_mm: float = 0.0  # 실측 - 예측. 다음 예측에 더해진다
    measured: bool = False  # 현재 Cycle에서 실측됐는지
    last_measured_vb_mm: float | None = None  # 가장 최근 실측값 (Cycle이 바뀌어도 유지)


@dataclass
class ToolState:
    tool_id: str
    edges: list[EdgeState] = field(default_factory=lambda: [EdgeState(i + 1) for i in range(N_EDGES)])
    cut_time_min: float = 0.0
    cycle: int = 0
    rechecks_this_cycle: int = 0
