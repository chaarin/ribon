"""Master Agent: 전문 Agent 결과를 종합해 최종 행동을 결정한다. (Track E)

판단 규칙 (위에서부터 먼저 맞는 규칙을 적용):
1. 센서 신호 품질이 낮거나 예측 불확실성이 크면 → 센서 재측정
2. VBmax가 교체 한계값 이상 → 즉시 교체
3. 편마모이고 최대 마모 날의 예측이 불확실하며 현장 검사가 가능하면 → 해당 날 검사
   (이미 실측한 날은 그 뒤 예측 VB가 reinspect_delta_mm 이상 늘었을 때만)
4. 품질 위험 HIGH → 즉시 교체
5. 품질 위험 MEDIUM → 즉시 교체 / 공정 후 교체 중 기대 비용이 작은 쪽 (재고가 없으면 공정 후 교체)
6. 그 외 → 계속 가공

검사(3)를 품질 위험 HIGH(4)보다 먼저 보는 이유: 편마모로 위험이 올라간 경우
예측이 틀렸을 수 있으므로, 검사가 가능하면 실측으로 확인한 뒤 교체 여부를 다시 판단한다.
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
            f"Edge별 VBmax(mm): {', '.join(f'E{e.edge_id} {e.vb_max_mm:.3f}{"(실측)" if e.measured else ""}' for e in wear.edges)}",
            f"날 간 차이 {wear.wear_difference_mm:.3f} mm, 편마모 지수 {wear.uneven_index:.2f} ({'편마모' if wear.uneven_flag else '정상'}), "
            f"최근 증가 최대 Edge {wear.fastest_edge}",
            *wear.notes,
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

        signal_bad = wear.signal_quality < wear_th["min_signal_quality"]
        if can_recheck and signal_bad:
            return decide(Action.REMEASURE, f"센서 신호 이상 (신호 품질 {wear.signal_quality:.2f}) → 재측정")
        if can_recheck and wear.mean_uncertainty >= wear_th["remeasure_uncertainty_mm"]:
            return decide(Action.REMEASURE, f"예측 불확실성 큼 (평균 {wear.mean_uncertainty:.3f} mm) → 재측정")
        caveat = " (센서 이상이 해결되지 않은 상태의 판단)" if signal_bad else ""

        if wear.vb_max >= wear_th["vb_limit_mm"]:
            reason = f"Edge {worst.edge_id} 교체 한계 도달 (VBmax {worst.vb_max_mm:.3f} mm ≥ {wear_th['vb_limit_mm']} mm)"
            return decide(Action.REPLACE_NOW, reason + self._stock_warning(economics) + caveat)

        if (
            can_recheck
            and wear.uneven_flag
            and not worst.measured
            and worst.uncertainty_mm >= wear_th["inspect_uncertainty_mm"]
            and self._needs_inspection(worst.edge_id, worst.vb_max_mm, state)
        ):
            if economics.inspection_available:
                return decide(
                    Action.INSPECT_EDGE,
                    f"Edge {worst.edge_id} 편마모 의심, 예측 불확실성 {worst.uncertainty_mm:.3f} mm → 실측 필요",
                    target_edge=worst.edge_id,
                )
            caveat += " (편마모 의심이나 현장 검사 불가 → 예측값 기준 판단)"

        if quality.risk_level == RiskLevel.HIGH:
            return decide(Action.REPLACE_NOW, "품질 위험 HIGH" + self._stock_warning(economics) + caveat)

        if quality.risk_level == RiskLevel.MEDIUM:
            if not economics.tool_available:
                return decide(Action.REPLACE_AFTER_JOB, "품질 위험 MEDIUM, 여분 공구가 없어 현재 공정 후 교체" + caveat)
            if economics.cost_replace_now <= economics.cost_replace_after_job:
                return decide(Action.REPLACE_NOW, "품질 위험 MEDIUM, 남은 부품의 추가 불량 위험보다 즉시 교체가 저렴" + caveat)
            return decide(Action.REPLACE_AFTER_JOB, "품질 위험 MEDIUM, 남은 부품이 적어 공정 후 교체가 저렴" + caveat)

        return decide(Action.CONTINUE, "마모·품질 위험 낮음" + caveat)

    def _stock_warning(self, economics: EconomicsReport) -> str:
        return "" if economics.tool_available else " - 여분 공구 없음, 긴급 확보 필요"

    def _needs_inspection(self, edge_id: int, vb_mm: float, state: ToolState) -> bool:
        last = state.edges[edge_id - 1].last_measured_vb_mm
        return last is None or vb_mm - last >= self.thresholds["wear"]["reinspect_delta_mm"]

    def _confidence(self, wear: WearReport) -> float:
        limit = self.thresholds["wear"]["remeasure_uncertainty_mm"]
        confidence = 1.0 - 0.5 * min(1.0, wear.mean_uncertainty / limit)
        if wear.signal_quality < self.thresholds["wear"]["min_signal_quality"]:
            confidence *= 0.5
        return round(confidence, 2)
