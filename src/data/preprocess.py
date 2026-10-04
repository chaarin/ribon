"""센서 신호 전처리와 신호 품질 평가."""
import numpy as np

from src.config.settings import SENSOR_CHANNELS
from src.schemas import SensorWindow


# 느린 성분 제거 창. QIT-CEMC 스핀들 회전 주파수(약 23 Hz) 기준 약 2바퀴.
# 회전 동력계의 영점 드리프트(Cycle 안에서 수십 N씩 밀림)를 걸러내고, 날이 맞물릴 때의 출렁임만 남긴다.
DETREND_WINDOW_S = 0.1


def detrend(x: np.ndarray, window: int) -> np.ndarray:
    """이동평균을 빼서 느린 드리프트를 제거한다."""
    if window <= 1 or len(x) <= window:
        return x - x.mean()
    cumsum = np.concatenate(([0.0], np.cumsum(x)))
    half = window // 2
    lo = np.clip(np.arange(len(x)) - half, 0, len(x))
    hi = np.clip(np.arange(len(x)) + half + 1, 0, len(x))
    return x - (cumsum[hi] - cumsum[lo]) / (hi - lo)


def preprocess(window: SensorWindow) -> dict[str, np.ndarray]:
    """결측값을 0으로 채우고 느린 드리프트(이동평균)를 제거한다."""
    win = int(DETREND_WINDOW_S * window.sampling_rate_hz)
    cleaned = {}
    for name, signal in window.signals.items():
        x = np.asarray(signal, dtype=float)
        finite = np.isfinite(x)
        x = np.where(finite, x, 0.0)
        cleaned[name] = detrend(x, win) if finite.any() else x
    return cleaned


def channel_quality(window: SensorWindow, channels: tuple[str, ...] = SENSOR_CHANNELS) -> dict[str, float]:
    """채널별 유효 샘플 비율 (채널이 없으면 0)."""
    scores = {}
    for name in channels:
        signal = window.signals.get(name)
        if signal is None or len(signal) == 0:
            scores[name] = 0.0
        else:
            scores[name] = float(np.isfinite(np.asarray(signal, dtype=float)).mean())
    return scores


def signal_quality(window: SensorWindow) -> float:
    """0~1 점수. 필수 채널이 하나라도 빠지면 판단을 믿을 수 없으므로 가장 나쁜 채널 기준으로 본다."""
    return min(channel_quality(window).values())
