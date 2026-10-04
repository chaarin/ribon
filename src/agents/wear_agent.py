"""Wear Agent: 센서 데이터로 Edge 1~4의 VBmax, 마모 속도, 편마모 수준을 산출한다. (Track B)"""
from src.agents.base import BaseAgent
from src.data.features import extract_features
from src.data.preprocess import preprocess, signal_quality
from src.models.wear_model import WearModel, load_wear_model
from src.schemas import EdgeWear, SensorWindow, ToolState, WearReport


class WearAgent(BaseAgent):
    name = "wear"

    def __init__(self, model: WearModel | None = None, thresholds: dict | None = None):
        super().__init__(thresholds)
        self.model = model or load_wear_model()

    def analyze(self, window: SensorWindow, state: ToolState) -> WearReport:
        features = extract_features(preprocess(window), window)
        raw_vb, uncertainty = self.model.predict(features, window)
        dt = window.cumulative_cut_time_min - state.cut_time_min

        edges = []
        for i, edge_state in enumerate(state.edges):
            # 이전 실측으로 구한 bias를 더해 날별 예측 오차를 보정한다
            vb = max(0.0, float(raw_vb[i]) + edge_state.bias_mm)
            rate = (vb - edge_state.vb_mm) / dt if dt > 0 else edge_state.wear_rate_mm_min
            edges.append(
                EdgeWear(
                    edge_id=i + 1,
                    vb_max_mm=vb,
                    uncertainty_mm=float(uncertainty[i]),
                    wear_rate_mm_min=rate,
                    raw_vb_mm=float(raw_vb[i]),
                )
            )

        return WearReport(
            tool_id=window.tool_id,
            cycle=window.cycle,
            edges=edges,
            signal_quality=signal_quality(window),
            uneven_threshold=self.thresholds["wear"]["uneven_index_threshold"],
            uneven_min_vb_mm=self.thresholds["wear"]["uneven_min_vb_mm"],
        )
