"""Master Agent: 전문 Agent 결과를 종합해 최종 행동을 결정한다. (Track E)

판단 규칙 (위에서부터 먼저 맞는 규칙을 적용):
1. 센서 신호 품질이 낮거나 예측 불확실성이 크면 → 센서 재측정
2. VBmax가 교체 한계값 이상 → 즉시 교체
3. 편마모이고 최대 마모 날의 예측이 불확실하며 현장 검사가 가능하면 → 해당 날 검사
   (이미 실측한 날은 그 뒤 예측 VB가 reinspect_delta_mm 이상 늘었을 때만)
3b. 검사 정보의 가치(Economics Agent)가 검사 시간보다 크고 날별 실측이 없으면 → 4개 날 모두 검사
   (센서 특징으로는 어느 날이 닳았는지 구분할 수 없으므로 검사로 날별 상태를 확인한다.
    마지막 검사 이후 최대 VB가 reinspect_delta_mm 이상 늘었을 때만 다시 검사)
4. 품질 위험 HIGH → 즉시 교체
5. 품질 위험 MEDIUM →
   이 윙 리브를 끝까지 가공할 때의 추가 불량 위험이 교체 시간보다 크면:
     여분 공구가 없으면 윙 리브를 마친 뒤 교체 (그동안 공구 확보)
     지금 교체하면 납기를 넘기고 생산 압박이 HIGH면 윙 리브를 마친 뒤 교체
     그 외에는 지금 교체
   윙 리브가 막 끝났고 다음 윙 리브의 위험이 경계 교체 시간보다 크면 → 지금(경계에서) 교체
   그 외 → 계속 가공 (위험이 교체 시간보다 작음. 0.3 mm 한계 전까지 매 Cycle 다시 평가)
6. 그 외 → 계속 가공
(0.3 mm 한계와 품질 위험 HIGH는 재고·납기와 상관없이 항상 즉시 교체)

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
        edge_texts = [f"E{e.edge_id} {e.vb_max_mm:.3f}" + ("(실측)" if e.measured else "") for e in wear.edges]
        evidence = [
            f"Edge별 VBmax(mm): {', '.join(edge_texts)}",
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

        if (
            can_recheck
            and economics.inspection_available
            and not any(e.measured for e in wear.edges)
            and worst.uncertainty_mm >= wear_th["inspect_uncertainty_mm"]
            and economics.inspection_value_min >= economics.inspection_time_min
            and self._needs_tool_inspection(wear.vb_max, state)
        ):
            return decide(
                Action.INSPECT_EDGE,
                f"센서 예측 최대 VBmax {wear.vb_max:.3f}±{worst.uncertainty_mm:.3f} mm, 주의 구간({quality.caution_vb_mm} mm) 근접. "
                f"검사 가치 {economics.inspection_value_min:.1f}분 > 검사 시간 {economics.inspection_time_min:.0f}분 → 4개 날 실측",
                target_edge=None,
            )

        if quality.risk_level == RiskLevel.HIGH:
            return decide(Action.REPLACE_NOW, "품질 위험 HIGH" + self._stock_warning(economics) + caveat)

        if quality.risk_level == RiskLevel.MEDIUM:
            ratio = self.thresholds["production"]["after_rib_change_ratio"]
            if economics.loss_continue_min < economics.loss_replace_now_min:
                if economics.cycles_left_in_rib == 0 and economics.next_rib_risk_min > economics.loss_replace_now_min * ratio:
                    return decide(
                        Action.REPLACE_AFTER_JOB,
                        f"품질 위험 MEDIUM, 윙 리브를 마친 시점. 다음 윙 리브의 추가 불량 위험({economics.next_rib_risk_min:.1f}분)이 "
                        f"작업 전환 중 교체({economics.loss_replace_now_min * ratio:.1f}분)보다 커서 지금 교체" + caveat,
                    )
                return decide(
                    Action.CONTINUE,
                    f"품질 위험 MEDIUM이지만 남은 {economics.cycles_left_in_rib} Cycle의 추가 불량 위험({economics.loss_continue_min:.1f}분)이 "
                    f"교체 시간({economics.loss_replace_now_min:.0f}분)보다 작아 계속 가공 (0.3 mm 한계 전까지 매 Cycle 재평가)" + caveat,
                )
            if not economics.tool_available:
                return decide(Action.REPLACE_AFTER_JOB, "품질 위험 MEDIUM, 여분 공구가 없어 이 윙 리브를 마친 뒤 교체 (그동안 공구 확보)" + caveat)
            if economics.delay_if_replace_now_min > 0 and economics.production_pressure == RiskLevel.HIGH:
                return decide(
                    Action.REPLACE_AFTER_JOB,
                    f"품질 위험 MEDIUM, 지금 교체하면 납기 {economics.delay_if_replace_now_min:.0f}분 지연 + 생산 압박 HIGH "
                    "→ 이 윙 리브를 마친 뒤 교체" + caveat,
                )
            return decide(
                Action.REPLACE_NOW,
                f"품질 위험 MEDIUM, 남은 {economics.cycles_left_in_rib} Cycle의 추가 불량 위험({economics.loss_continue_min:.1f}분)이 "
                f"교체 시간({economics.loss_replace_now_min:.0f}분)보다 커서 지금 교체" + caveat,
            )

        return decide(Action.CONTINUE, "마모·품질 위험 낮음" + caveat)

    def _stock_warning(self, economics: EconomicsReport) -> str:
        return "" if economics.tool_available else " - 여분 공구 없음, 긴급 확보 필요"

    def _needs_inspection(self, edge_id: int, vb_mm: float, state: ToolState) -> bool:
        last = state.edges[edge_id - 1].last_measured_vb_mm
        return last is None or vb_mm - last >= self.thresholds["wear"]["reinspect_delta_mm"]

    def _needs_tool_inspection(self, vb_max_mm: float, state: ToolState) -> bool:
        measured = [e.last_measured_vb_mm for e in state.edges if e.last_measured_vb_mm is not None]
        return not measured or vb_max_mm - max(measured) >= self.thresholds["wear"]["reinspect_delta_mm"]

    def _confidence(self, wear: WearReport) -> float:
        limit = self.thresholds["wear"]["remeasure_uncertainty_mm"]
        confidence = 1.0 - 0.5 * min(1.0, wear.mean_uncertainty / limit)
        if wear.signal_quality < self.thresholds["wear"]["min_signal_quality"]:
            confidence *= 0.5
        return round(confidence, 2)
