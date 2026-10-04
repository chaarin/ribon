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


def channel_quality(window: SensorWindow) -> dict[str, float]:
    """기대 채널별 유효 샘플 비율 (채널이 없으면 0)."""
    scores = {}
    for name in SENSOR_CHANNELS:
        signal = window.signals.get(name)
        if signal is None or len(signal) == 0:
            scores[name] = 0.0
        else:
            scores[name] = float(np.isfinite(np.asarray(signal, dtype=float)).mean())
    return scores


def signal_quality(window: SensorWindow) -> float:
    """0~1 점수. 필수 채널이 하나라도 빠지면 판단을 믿을 수 없으므로 가장 나쁜 채널 기준으로 본다."""
    return min(channel_quality(window).values())
