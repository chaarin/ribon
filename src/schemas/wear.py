"""Wear Agent 출력 형식."""
from dataclasses import dataclass, field

from src.config.settings import N_EDGES


@dataclass
class EdgeWear:
    edge_id: int  # 1~4
    vb_max_mm: float  # 보정된 VBmax (실측되면 실측값)
    uncertainty_mm: float
    increment_mm: float = 0.0  # 직전 Cycle 대비 VBmax 증가량
    raw_vb_mm: float = 0.0  # 보정 전 모델 예측값
    measured: bool = False  # 현장 실측값으로 갱신됐는지 여부


@dataclass
class WearReport:
    tool_id: str
    cycle: int
    edges: list[EdgeWear]
    signal_quality: float = 1.0  # 0~1, 가장 나쁜 센서 채널의 유효 샘플 비율
    uneven_threshold: float = 0.3
    uneven_min_vb_mm: float = 0.05
    notes: list[str] = field(default_factory=list)  # 센서 누락 등 이상 사항

    def __post_init__(self):
        if len(self.edges) != N_EDGES:
            raise ValueError(f"edges는 {N_EDGES}개여야 합니다: {len(self.edges)}개")

    @property
    def vb_values(self) -> list[float]:
        return [e.vb_max_mm for e in self.edges]

    @property
    def vb_mean(self) -> float:
        return sum(self.vb_values) / N_EDGES

    @property
    def vb_max(self) -> float:
        return max(self.vb_values)

    @property
    def vb_min(self) -> float:
        return min(self.vb_values)

    @property
    def wear_difference_mm(self) -> float:
        return self.vb_max - self.vb_min

    @property
    def worst_edge(self) -> int:
        return max(self.edges, key=lambda e: e.vb_max_mm).edge_id

    @property
    def fastest_edge(self) -> int:
        """직전 Cycle 대비 증가량이 가장 큰 날."""
        return max(self.edges, key=lambda e: e.increment_mm).edge_id

    @property
    def uneven_index(self) -> float:
        """편마모 지수 = (최대 - 최소) / 평균."""
        if self.vb_mean <= 0:
            return 0.0
        return self.wear_difference_mm / self.vb_mean

    @property
    def uneven_flag(self) -> bool:
        return self.vb_mean >= self.uneven_min_vb_mm and self.uneven_index >= self.uneven_threshold

    @property
    def mean_uncertainty(self) -> float:
        return sum(e.uncertainty_mm for e in self.edges) / N_EDGES

    def edge(self, edge_id: int) -> EdgeWear:
        return self.edges[edge_id - 1]
