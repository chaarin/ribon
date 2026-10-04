"""Cycle 단위 특징 추출. (Track A에서 확장: 주파수 대역 에너지, 날 통과 주파수 성분 등)"""
import numpy as np

from src.schemas import SensorWindow


def extract_features(signals: dict[str, np.ndarray], window: SensorWindow) -> dict[str, float]:
    features: dict[str, float] = {"cut_time_min": window.cumulative_cut_time_min}
    for name, x in signals.items():
        if len(x) == 0:
            continue
        rms = float(np.sqrt(np.mean(x**2)))
        std = float(x.std())
        peak = float(np.max(np.abs(x)))
        features[f"{name}_rms"] = rms
        features[f"{name}_std"] = std
        features[f"{name}_peak"] = peak
        features[f"{name}_crest"] = peak / rms if rms > 0 else 0.0
        features[f"{name}_kurtosis"] = float(np.mean((x - x.mean()) ** 4) / std**4) if std > 0 else 0.0
    return features
