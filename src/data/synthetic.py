"""데이터 없이 파이프라인을 돌려보기 위한 합성 데이터 생성기.

Edge 3에 절삭 시간 10분 이후 마모가 빨라지는 편마모 패턴을 넣는다.
실제 데이터가 아니므로 모델 학습이나 성능 평가에는 사용하지 않는다.
"""
import numpy as np

from src.config.settings import SENSOR_CHANNELS
from src.schemas import SensorWindow

BASE_RATE_MM_MIN = 0.008
EDGE_RATE_FACTOR = (1.0, 1.05, 1.0, 0.97)
UNEVEN_EDGE = 3
UNEVEN_START_MIN = 10.0
UNEVEN_EXTRA_RATE = 0.006


def true_vb(t_min: float) -> list[float]:
    vb = [BASE_RATE_MM_MIN * f * t_min for f in EDGE_RATE_FACTOR]
    vb[UNEVEN_EDGE - 1] += UNEVEN_EXTRA_RATE * max(0.0, t_min - UNEVEN_START_MIN)
    return vb


def generate_tool_run(
    tool_id: str = "T01",
    n_cycles: int = 20,
    cycle_cut_time_min: float = 2.0,
    sampling_rate_hz: float = 1000.0,
    seconds: float = 1.0,
    seed: int = 0,
) -> list[SensorWindow]:
    rng = np.random.default_rng(seed)
    n = int(sampling_rate_hz * seconds)
    windows = []
    for cycle in range(1, n_cycles + 1):
        t = cycle * cycle_cut_time_min
        vb = true_vb(t)
        amplitude = 1.0 + 3.0 * float(np.mean(vb))  # 마모가 커질수록 신호 진폭 증가
        signals = {ch: amplitude * rng.normal(size=n) for ch in SENSOR_CHANNELS}
        windows.append(
            SensorWindow(
                tool_id=tool_id,
                cycle=cycle,
                sampling_rate_hz=sampling_rate_hz,
                signals=signals,
                cumulative_cut_time_min=t,
                vb_label_mm=vb,
            )
        )
    return windows
