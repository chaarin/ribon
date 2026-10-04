"""센서 신호 전처리와 신호 품질 평가."""
import numpy as np

from src.config.settings import SENSOR_CHANNELS
from src.schemas import SensorWindow


def preprocess(window: SensorWindow) -> dict[str, np.ndarray]:
    """결측값을 0으로 채우고 DC 성분(평균)을 제거한다."""
    cleaned = {}
    for name, signal in window.signals.items():
        x = np.asarray(signal, dtype=float)
        finite = np.isfinite(x)
        x = np.where(finite, x, 0.0)
        if finite.any():
            x = x - x[finite].mean()
        cleaned[name] = x
    return cleaned


def signal_quality(window: SensorWindow) -> float:
    """0~1 점수. 기대 채널마다 유효 샘플 비율을 구해 평균낸다 (채널이 없으면 0)."""
    scores = []
    for name in SENSOR_CHANNELS:
        signal = window.signals.get(name)
        if signal is None or len(signal) == 0:
            scores.append(0.0)
        else:
            scores.append(float(np.isfinite(np.asarray(signal, dtype=float)).mean()))
    return float(np.mean(scores))
