"""마모 예측 모델 인터페이스와 합성 데이터용 모델. (Track B)"""
from typing import Protocol

import numpy as np

from src.config.settings import N_EDGES, SENSOR_CHANNELS
from src.schemas import SensorWindow


class WearModel(Protocol):
    required_channels: tuple[str, ...]  # 예측에 필요한 센서 채널 (신호 품질은 이 채널만 본다)

    def predict(self, features: dict[str, float], window: SensorWindow) -> tuple[np.ndarray, np.ndarray]:
        """Edge 1~4의 (VBmax 예측값, 불확실성)을 mm 단위로 반환한다. 각각 shape (N_EDGES,)."""
        ...


class DummyWearModel:
    """합성 데이터 데모(python -m src.main --data synthetic)와 테스트용 모델. 실제 데이터에는 tool_wear_model을 쓴다.

    라벨이 있으면 라벨에 일정한 과소추정 오차와 노이즈를 섞어 예측을 흉내 내고,
    없으면 누적 절삭 시간으로 평균 마모를 추정한다. 성능 평가에 사용하지 않는다.
    """

    required_channels = SENSOR_CHANNELS

    def __init__(
        self,
        bias_mm: float = -0.03,
        noise_mm: float = 0.005,
        uncertainty_mm: float = 0.03,
        fallback_rate_mm_min: float = 0.0085,
        seed: int = 0,
    ):
        self.bias_mm = bias_mm
        self.noise_mm = noise_mm
        self.uncertainty_mm = uncertainty_mm
        self.fallback_rate_mm_min = fallback_rate_mm_min
        self.rng = np.random.default_rng(seed)

    def predict(self, features: dict[str, float], window: SensorWindow) -> tuple[np.ndarray, np.ndarray]:
        if window.vb_label_mm is not None:
            base = np.asarray(window.vb_label_mm, dtype=float)
        else:
            base = np.full(N_EDGES, self.fallback_rate_mm_min * features["cut_time_min"])
        vb = np.clip(base + self.bias_mm + self.rng.normal(0.0, self.noise_mm, N_EDGES), 0.0, None)
        return vb, np.full(N_EDGES, self.uncertainty_mm)


def load_wear_model() -> WearModel:
    """모델을 지정하지 않았을 때의 기본값 (합성 데이터용). 실제 데이터 재생은 src.evaluation.replay가 학습 모델을 넣는다."""
    return DummyWearModel()
