"""Economics / Production Agent: 행동별 기대 손실 시간과 생산 압박을 분석한다. (Track D)

손실은 가공 시간(분)으로 계산한다 (윙 리브 1개 = 10 Cycle, MVP 가정).
- 지금 교체: 교체 시간
- 윙 리브를 끝내고 교체: 작업 전환과 겹쳐 줄어든 교체 시간 + 남은 Cycle 동안의 추가 불량 위험
- 계속 가공: 남은 Cycle 동안의 추가 불량 위험 (교체 시간은 뒤로 미룸)
추가 불량 위험 = 남은 Cycle 수 × (현재 위험 등급의 불량 확률 − 새 공구 수준의 불량 확률) × 불량 1건당 잃는 시간
불량 1건당 잃는 시간은 정삭이면 윙 리브 전체 가공 시간, 황삭이면 한 Cycle 재가공 시간이다.

검사 정보의 가치 = P(실제 최대 VB ≥ 주의 기준) × 윙 리브 1개 동안 막을 수 있는 추가 불량 손실.
예측이 정규분포(예측값, 불확실성)를 따른다고 보고 확률을 구한다. 이 값이 검사 시간보다 클 때만 검사할 가치가 있다.
→ 정삭(불량 1건 85분)은 주의 구간 근처에서 검사가 이득이고, 황삭(8.5분)은 검사보다 그냥 가공하는 편이 낫다.
"""
import math

from src.agents.base import BaseAgent
from src.schemas import Action, EconomicsReport, ProductionContext, QualityReport, RiskLevel, WearReport

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


def cycles_left_in_rib(ctx: ProductionContext, cycles_per_rib: int) -> int:
    """지금 가공 중인 윙 리브에 남은 Cycle 수."""
    return max(0, round((100 - ctx.process_progress_pct) / 100 * cycles_per_rib))


def defect_loss_min(tool_purpose: str, thresholds: dict) -> float:
    prod = thresholds["production"]
    if thresholds["tool_purpose"][tool_purpose]["defect_loss"] == "rib":
        return prod["cycles_per_rib"] * prod["cycle_time_min"]
    return prod["cycle_time_min"]


class EconomicsAgent(BaseAgent):
    name = "economics"

    def analyze(self, quality: QualityReport, ctx: ProductionContext, wear: WearReport | None = None) -> EconomicsReport:
        prod = self.thresholds["production"]
        p_defect = self.thresholds["economics"]["defect_probability"]
        excess_defect = p_defect[quality.risk_level.value] - p_defect[RiskLevel.LOW.value]

        cycles_left = cycles_left_in_rib(ctx, prod["cycles_per_rib"])
        per_defect = defect_loss_min(ctx.tool_purpose, self.thresholds)
        risk_rest = cycles_left * excess_defect * per_defect

        loss_now = ctx.change_time_min
        loss_after = ctx.change_time_min * prod["after_rib_change_ratio"] + risk_rest
        loss_continue = risk_rest
        losses = {Action.REPLACE_NOW: loss_now, Action.REPLACE_AFTER_JOB: loss_after, Action.CONTINUE: loss_continue}
        recommended = min(losses, key=losses.get)

        medium_excess = p_defect[RiskLevel.MEDIUM.value] - p_defect[RiskLevel.LOW.value]
        next_rib_risk = prod["cycles_per_rib"] * excess_defect * per_defect
        p_caution = self._prob_caution(wear, quality.caution_vb_mm) if wear is not None else 0.0
        inspection_value = p_caution * prod["cycles_per_rib"] * medium_excess * per_defect

        delay = max(0.0, ctx.change_time_min - ctx.due_slack_min)
        pressure = self._production_pressure(ctx)
        purpose = self.thresholds["tool_purpose"][ctx.tool_purpose]["label"]

        reasons = [
            f"기대 손실 시간: 지금 교체 {loss_now:.1f}분 / 윙 리브 마친 뒤 교체 {loss_after:.1f}분 / 계속 가공 {loss_continue:.1f}분 "
            f"(윙 리브 남은 {cycles_left} Cycle, {purpose} 불량 1건당 {per_defect:.0f}분 손실)",
            f"남은 윙 리브 {ctx.remaining_parts}개, 진행률 {ctx.process_progress_pct:.0f}%, 납기 여유 {ctx.due_slack_min:.0f}분, "
            f"우선순위 {ctx.production_priority} → 생산 압박 {pressure.value}",
        ]
        if wear is not None and not any(e.measured for e in wear.edges):
            reasons.append(
                f"검사 정보의 가치 {inspection_value:.1f}분 (주의 구간일 확률 {p_caution:.0%}) vs 검사 시간 {prod['inspection_time_min']}분"
            )
        if delay > 0:
            reasons.append(f"지금 교체하면 납기 {delay:.0f}분 지연 (교체 {ctx.change_time_min:.0f}분 > 납기 여유 {ctx.due_slack_min:.0f}분)")
        if ctx.tool_stock <= 0:
            reasons.append("여분 공구 재고 없음")
        if not ctx.inspection_available:
            reasons.append("현장 검사 불가")

        return EconomicsReport(
            loss_replace_now_min=loss_now,
            loss_replace_after_rib_min=loss_after,
            loss_continue_min=loss_continue,
            cycles_left_in_rib=cycles_left,
            delay_if_replace_now_min=delay,
            next_rib_risk_min=next_rib_risk,
            inspection_value_min=inspection_value,
            inspection_time_min=prod["inspection_time_min"],
            production_pressure=pressure,
            tool_available=ctx.tool_stock > 0,
            inspection_available=ctx.inspection_available,
            recommended=recommended,
            reasons=reasons,
        )

    @staticmethod
    def _prob_caution(wear: WearReport, caution_vb_mm: float) -> float:
        """실제 최대 VB가 주의 기준 이상일 확률 (예측 ~ 정규분포(예측값, 불확실성))."""
        worst = wear.edge(wear.worst_edge)
        if worst.uncertainty_mm <= 0:
            return 1.0 if worst.vb_max_mm >= caution_vb_mm else 0.0
        z = (caution_vb_mm - worst.vb_max_mm) / worst.uncertainty_mm
        return 0.5 * (1 - math.erf(z / math.sqrt(2)))

    def _production_pressure(self, ctx: ProductionContext) -> RiskLevel:
        slack = self.thresholds["production"]["pressure_slack_min"]
        if ctx.due_slack_min < slack["high"]:
            idx = 2
        elif ctx.due_slack_min < slack["medium"]:
            idx = 1
        else:
            idx = 0
        if ctx.production_priority.lower() == "high":
            idx = min(idx + 1, 2)
        return LEVELS[idx]
