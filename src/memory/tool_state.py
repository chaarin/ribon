"""공구별 현재 상태 저장소."""
from src.schemas import ToolState, WearReport


class ToolStateStore:
    def __init__(self):
        self._states: dict[str, ToolState] = {}

    def get(self, tool_id: str) -> ToolState:
        if tool_id not in self._states:
            self._states[tool_id] = ToolState(tool_id)
        return self._states[tool_id]

    def update_from_wear(self, state: ToolState, wear: WearReport, cut_time_min: float) -> None:
        for edge_state, edge in zip(state.edges, wear.edges):
            edge_state.vb_mm = edge.vb_max_mm
            edge_state.raw_pred_mm = edge.raw_vb_mm
            edge_state.uncertainty_mm = edge.uncertainty_mm
            edge_state.measured = False
        state.cut_time_min = cut_time_min

    def reset(self, tool_id: str) -> ToolState:
        """공구 교체 후 새 공구 상태로 초기화한다."""
        self._states[tool_id] = ToolState(tool_id)
        return self._states[tool_id]
