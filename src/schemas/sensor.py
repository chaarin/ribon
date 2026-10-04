"""센서 입력 형식. 데이터 로더/시뮬레이터가 만들고 Wear Agent가 소비한다."""
from dataclasses import dataclass

import numpy as np


@dataclass
class CuttingCondition:
    spindle_speed_rpm: float
    feed_rate_mm_min: float
    axial_depth_mm: float
    radial_depth_mm: float


@dataclass
class SensorWindow:
    """한 Cycle 동안 측정된 센서 신호."""

    tool_id: str
    cycle: int
    sampling_rate_hz: float
    signals: dict[str, np.ndarray]  # 채널명(settings.SENSOR_CHANNELS) -> 1차원 신호
    cumulative_cut_time_min: float  # 이 Cycle 종료 시점까지의 누적 절삭 시간
    condition: CuttingCondition | None = None
    vb_label_mm: list[float] | None = None  # 데이터셋의 Edge 1~4 VBmax 라벨 (학습·평가용)
    features: dict[str, float] | None = None  # 미리 추출한 특징 (있으면 signals 대신 사용, 실제 데이터 재생용)
