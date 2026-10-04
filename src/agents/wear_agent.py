"""Wear Agent: 센서 데이터로 Edge 1~4의 VBmax, 증가량, 편마모 수준을 산출한다. (Track B)"""
import math

from src.agents.base import BaseAgent
from src.config.settings import SENSOR_CHANNELS
from src.data.features import extract_features
from src.feedback.feedback_handler import MEASURED_UNCERTAINTY_MM
from src.data.preprocess import channel_quality, preprocess
from src.models.wear_model import WearModel, load_wear_model
from src.schemas import EdgeWear, SensorWindow, ToolState, WearReport


class WearAgent(BaseAgent):
    name = "wear"

    def __init__(self, model: WearModel | None = None, thresholds: dict | None = None):
        super().__init__(thresholds)
        self.model = model or load_wear_model()

    def analyze(self, window: SensorWindow, state: ToolState) -> WearReport:
        required = getattr(self.model, "required_channels", SENSOR_CHANNELS)
        if window.features is not None:
            features = window.features
            quality = {ch: _feature_quality(features, ch) for ch in required}
        else:
            features = extract_features(preprocess(window), window)
            quality = channel_quality(window, required)
        raw_vb, uncertainty = self.model.predict(features, window)
        # 누적 절삭 시간이 늘었으면 새 Cycle, 같으면 같은 Cycle의 재측정
        is_new_cycle = window.cumulative_cut_time_min > state.cut_time_min

        decay = self.thresholds["wear"]["bias_decay_per_cycle"]
        edges = []
        for i, edge_state in enumerate(state.edges):
            # 최근 실측으로 구한 bias를 더해 날별 차이를 반영한다. 실측에서 멀어질수록 bias는 줄고 불확실성은 다시 커진다
            weight = decay ** (window.cycle - edge_state.bias_cycle) if edge_state.bias_cycle is not None else 0.0
            vb = max(0.0, float(raw_vb[i]) + edge_state.bias_mm * weight)
            edges.append(
                EdgeWear(
                    edge_id=i + 1,
                    vb_max_mm=vb,
                    uncertainty_mm=float(uncertainty[i]) * (1 - weight) + MEASURED_UNCERTAINTY_MM * weight,
                    increment_mm=vb - edge_state.vb_mm if is_new_cycle else 0.0,
                    raw_vb_mm=float(raw_vb[i]),
                )
            )

        min_quality = self.thresholds["wear"]["min_signal_quality"]
        bad_channels = [name for name, q in quality.items() if q < min_quality]
        notes = [f"센서 이상 채널: {', '.join(bad_channels)}"] if bad_channels else []

        return WearReport(
            tool_id=window.tool_id,
            cycle=window.cycle,
            edges=edges,
            signal_quality=min(quality.values()),
            uneven_threshold=self.thresholds["wear"]["uneven_index_threshold"],
            uneven_min_vb_mm=self.thresholds["wear"]["uneven_min_vb_mm"],
            notes=notes,
        )


def _feature_quality(features: dict[str, float], channel: str) -> float:
    """미리 추출한 특징에서 채널 특징이 모두 유효하면 1, 하나라도 없거나 NaN이면 0."""
    values = [v for k, v in features.items() if k.startswith(f"{channel}_")]
    return 1.0 if values and all(isinstance(v, (int, float)) and math.isfinite(v) for v in values) else 0.0
