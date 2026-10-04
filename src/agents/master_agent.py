"""Master Agent: 전문 Agent 결과를 종합해 최종 행동을 결정한다. (Track E)

판단 규칙 (위에서부터 먼저 맞는 규칙을 적용):
1. 센서 신호 품질이 낮거나 예측 불확실성이 크면 → 센서 재측정
2. 품질 위험 HIGH 또는 VBmax가 한계값 이상 → 즉시 교체
3. 편마모이고 최대 마모 날의 불확실성이 크면 → 해당 날 검사
   (이미 실측한 날은 그 뒤 예측 VB가 reinspect_delta_mm 이상 늘었을 때만)
4. 품질 위험 MEDIUM → 즉시 교체 / 공정 후 교체 중 기대 비용이 작은 쪽
5. 그 외 → 계속 가공
"""
from src.agents.base import BaseAgent
from src.schemas import Action, Decision, EconomicsReport, QualityReport, RiskLevel, ToolState, WearReport


class MasterAgent(BaseAgent):
    name = "master"

    def analyze(
        self,
        wear: WearReport,
        quality: QualityReport,
        economics: EconomicsReport,
        state: ToolState,
    ) -> Decision:
        wear_th = self.thresholds["wear"]
        can_recheck = state.rechecks_this_cycle < self.thresholds["decision"]["max_rechecks_per_cycle"]
        worst = wear.edge(wear.worst_edge)
        evidence = [
            f"Edge별 VBmax(mm): {', '.join(f'E{e.edge_id} {e.vb_max_mm:.3f}' for e in wear.edges)}",
            f"편마모 지수 {wear.uneven_index:.2f} ({'편마모' if wear.uneven_flag else '정상'})",
            *quality.reasons,
            *economics.reasons,
        ]

        def decide(action: Action, reason: str, target_edge: int | None = None) -> Decision:
            return Decision(
                tool_id=wear.tool_id,
                cycle=wear.cycle,
                action=action,
                target_edge=target_edge,
                reasons=[reason, *evidence],
                confidence=self._confidence(wear),
            )

        if can_recheck and wear.signal_quality < wear_th["min_signal_quality"]:
            return decide(Action.REMEASURE, f"센서 신호 품질 낮음 ({wear.signal_quality:.2f})")
        if can_recheck and wear.mean_uncertainty >= wear_th["remeasure_uncertainty_mm"]:
            return decide(Action.REMEASURE, f"예측 불확실성 큼 (평균 {wear.mean_uncertainty:.3f} mm)")

        if quality.risk_level == RiskLevel.HIGH or wear.vb_max >= wear_th["vb_limit_mm"]:
            reason = f"Edge {worst.edge_id} 마모 한계 도달 (VBmax {worst.vb_max_mm:.3f} mm, 품질 위험 {quality.risk_level.value})"
            if not economics.tool_available:
                reason += " - 재고 없음, 공구 긴급 확보 필요"
            return decide(Action.REPLACE_NOW, reason)

        if (
            can_recheck
            and wear.uneven_flag
            and not worst.measured
            and worst.uncertainty_mm >= wear_th["inspect_uncertainty_mm"]
            and self._needs_inspection(worst.edge_id, worst.vb_max_mm, state)
        ):
            return decide(
                Action.INSPECT_EDGE,
                f"Edge {worst.edge_id} 편마모 의심, 예측 불확실성 {worst.uncertainty_mm:.3f} mm → 실측 필요",
                target_edge=worst.edge_id,
            )

        if quality.risk_level == RiskLevel.MEDIUM:
            if not economics.tool_available:
                return decide(Action.REPLACE_AFTER_JOB, "품질 위험 MEDIUM, 재고가 없어 공정 후 교체")
            if economics.cost_replace_now <= economics.cost_replace_after_job:
                return decide(Action.REPLACE_NOW, "품질 위험 MEDIUM, 남은 부품의 불량 위험보다 즉시 교체가 저렴")
            return decide(Action.REPLACE_AFTER_JOB, "품질 위험 MEDIUM, 남은 부품이 적어 공정 후 교체가 저렴")

        return decide(Action.CONTINUE, "마모·품질 위험 낮음")

    def _needs_inspection(self, edge_id: int, vb_mm: float, state: ToolState) -> bool:
        last = state.edges[edge_id - 1].last_measured_vb_mm
        return last is None or vb_mm - last >= self.thresholds["wear"]["reinspect_delta_mm"]

    def _confidence(self, wear: WearReport) -> float:
        limit = self.thresholds["wear"]["remeasure_uncertainty_mm"]
        return round(1.0 - 0.5 * min(1.0, wear.mean_uncertainty / limit), 2)
