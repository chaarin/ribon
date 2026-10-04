"""Agent 실행 순서와 재판단 루프를 관리한다. (Track E)

센서 데이터 → Wear → Quality → Economics/Production → Master → 행동
검사 결과 Feedback → 상태 갱신 → Quality부터 재판단
"""
from src.agents.economics_agent import EconomicsAgent
from src.agents.master_agent import MasterAgent
from src.agents.quality_agent import QualityAgent
from src.agents.wear_agent import WearAgent
from src.feedback.feedback_handler import apply_inspection
from src.memory.history_store import HistoryStore
from src.memory.tool_state import ToolStateStore
from src.schemas import Decision, InspectionResult, ProductionContext, SensorWindow, WearReport


class MaintenancePipeline:
    def __init__(
        self,
        wear_agent: WearAgent | None = None,
        quality_agent: QualityAgent | None = None,
        economics_agent: EconomicsAgent | None = None,
        master_agent: MasterAgent | None = None,
        state_store: ToolStateStore | None = None,
        history: HistoryStore | None = None,
    ):
        self.wear_agent = wear_agent or WearAgent()
        self.quality_agent = quality_agent or QualityAgent()
        self.economics_agent = economics_agent or EconomicsAgent()
        self.master_agent = master_agent or MasterAgent()
        self.state_store = state_store or ToolStateStore()
        self.history = history or HistoryStore()
        self._last: dict[str, tuple[WearReport, ProductionContext]] = {}

    def run_cycle(self, window: SensorWindow, ctx: ProductionContext) -> Decision:
        """새 Cycle의 센서 데이터로 판단한다. 같은 Cycle을 다시 넣으면 재측정으로 간주한다."""
        state = self.state_store.get(window.tool_id)
        if window.cycle == state.cycle:
            state.rechecks_this_cycle += 1
        else:
            state.cycle = window.cycle
            state.rechecks_this_cycle = 0

        wear = self.wear_agent.analyze(window, state)
        self.state_store.update_from_wear(state, wear, window.cumulative_cut_time_min)
        self.history.append("wear", wear)
        return self._decide(wear, ctx)

    def apply_feedback(self, inspection: InspectionResult) -> Decision:
        """검사 결과를 반영해 같은 Cycle을 재판단한다."""
        if inspection.tool_id not in self._last:
            raise ValueError(f"{inspection.tool_id}: 판단 이력이 없어 Feedback을 반영할 수 없습니다")
        state = self.state_store.get(inspection.tool_id)
        wear, ctx = self._last[inspection.tool_id]
        wear = apply_inspection(inspection, wear, state)
        state.rechecks_this_cycle += 1
        self.history.append("feedback", inspection)
        return self._decide(wear, ctx)

    def confirm_replacement(self, tool_id: str) -> None:
        """현장에서 공구 교체를 완료했을 때 호출한다."""
        self.state_store.reset(tool_id)
        self._last.pop(tool_id, None)
        self.history.append("replacement", {"tool_id": tool_id})

    def _decide(self, wear: WearReport, ctx: ProductionContext) -> Decision:
        state = self.state_store.get(wear.tool_id)
        self._last[wear.tool_id] = (wear, ctx)
        quality = self.quality_agent.analyze(wear)
        economics = self.economics_agent.analyze(quality, ctx)
        decision = self.master_agent.analyze(wear, quality, economics, state)
        self.history.append("decision", decision)
        return decision
