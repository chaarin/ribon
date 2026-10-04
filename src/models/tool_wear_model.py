"""공구 단위 마모 예측 모델. (Track B)

Cycle 단위 특징은 4개 날의 신호를 합친 통계라서 '어느 날'에 대한 정보가 없다 (docs/track_b_results.md).
그래서 센서로는 공구 전체의 위험 수준인 **가장 많이 닳은 날의 VBmax**와 그 불확실성을 예측하고,
어느 날이 문제인지는 현장 검사(Feedback)로 확인한다.

진동은 8개 Cycle(마모가 가장 심한 65~68 포함)에 없으므로 힘/토크만 쓴다.
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

from src.config.settings import N_EDGES, ROOT_DIR
from src.schemas import SensorWindow

FEATURES_PATH = ROOT_DIR / "data" / "features" / "qit_cemc_features.csv"
FORCE_CHANNELS = ("Fx", "Fy", "Fz", "Mz")
# 힘/토크 4채널의 rms·std·peak (12개). 누적 절삭시간을 더하면 오히려 나빠져서 뺐다 (docs/track_b_results.md)
FEATURE_COLUMNS = [f"{ch}_{stat}" for ch in FORCE_CHANNELS for stat in ("rms", "std", "peak")]
LABEL_COLUMNS = [f"edge{i}_vbmax_mm" for i in range(1, N_EDGES + 1)]
RIDGE_ALPHA = 10.0
# 시간 순서 데이터라 바로 옆 Cycle은 거의 같은 값을 갖는다. 교차검증 때 앞뒤 이 범위를 학습에서 뺀다
BLOCK_GAP = 5


def load_features(path: Path = FEATURES_PATH) -> pd.DataFrame:
    return pd.read_csv(path).sort_values("cycle").reset_index(drop=True)


def worst_edge_vb(df: pd.DataFrame) -> np.ndarray:
    return df[LABEL_COLUMNS].max(axis=1).to_numpy()


def make_regressor(alpha: float = RIDGE_ALPHA) -> Pipeline:
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


def blocked_cv_predictions(df: pd.DataFrame, columns: list[str] = FEATURE_COLUMNS, gap: int = BLOCK_GAP) -> pd.Series:
    """각 Cycle을, 그 Cycle 앞뒤 gap 범위를 뺀 나머지로 학습한 모델로 예측한다 (Cycle → 예측 최대 VBmax)."""
    X, y, cycles = df[columns].to_numpy(), worst_edge_vb(df), df["cycle"].to_numpy()
    preds = {}
    for i, c in enumerate(cycles):
        train = np.abs(cycles - c) > gap
        preds[int(c)] = float(make_regressor().fit(X[train], y[train]).predict(X[i : i + 1])[0])
    return pd.Series(preds, name="pred_vb_max_mm")


@dataclass
class ToolWearModel:
    """학습된 공구 단위 모델. Edge 1~4 모두에 '가장 많이 닳은 날' 예측값을 넣는다 (어느 날일지 모르므로 보수적으로)."""

    regressor: Pipeline
    sigma_mm: float  # 예측 불확실성 (블록 교차검증 잔차의 표준편차)
    feature_columns: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    required_channels: tuple[str, ...] = FORCE_CHANNELS

    def predict_vb_max(self, features: dict[str, float]) -> float:
        x = np.array([[features[c] for c in self.feature_columns]])
        return max(0.0, float(self.regressor.predict(x)[0]))

    def predict(self, features: dict[str, float], window: SensorWindow) -> tuple[np.ndarray, np.ndarray]:
        return np.full(N_EDGES, self.predict_vb_max(features)), np.full(N_EDGES, self.sigma_mm)


def train_tool_wear_model(df: pd.DataFrame, columns: list[str] = FEATURE_COLUMNS) -> ToolWearModel:
    residuals = blocked_cv_predictions(df, columns).to_numpy() - worst_edge_vb(df)
    regressor = make_regressor().fit(df[columns].to_numpy(), worst_edge_vb(df))
    return ToolWearModel(regressor=regressor, sigma_mm=float(np.std(residuals)), feature_columns=list(columns))


@dataclass
class PrecomputedWearModel:
    """미리 계산한 Cycle별 예측값을 돌려주는 모델. 평가 때 각 Cycle을 그 Cycle을 학습에 쓰지 않은 예측으로 재생한다."""

    predictions: dict[int, float]
    sigma_mm: float
    required_channels: tuple[str, ...] = FORCE_CHANNELS

    def predict(self, features: dict[str, float], window: SensorWindow) -> tuple[np.ndarray, np.ndarray]:
        return np.full(N_EDGES, max(0.0, self.predictions[window.cycle])), np.full(N_EDGES, self.sigma_mm)
