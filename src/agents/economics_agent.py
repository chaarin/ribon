"""Economics / Production Agent: 행동별 기대 비용과 생산 압박을 분석한다. (Track D)

비용은 새 공구 대비 '추가로' 생기는 불량 위험으로 계산한다.
(새 공구도 불량 확률이 0은 아니므로, 위험 LOW일 때 계속 사용의 추가 위험 비용은 0)
"""
from src.agents.base import BaseAgent
from src.schemas import Action, EconomicsReport, ProductionContext, QualityReport, RiskLevel

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


class EconomicsAgent(BaseAgent):
    name = "economics"

    def analyze(self, quality: QualityReport, ctx: ProductionContext) -> EconomicsReport:
        th = self.thresholds["economics"]
        p_defect = th["defect_probability"]
        excess_defect = p_defect[quality.risk_level.value] - p_defect[RiskLevel.LOW.value]

        pressure = self._production_pressure(ctx)
        downtime_cost = ctx.change_time_min * ctx.downtime_cost_per_min
        risk_cost = ctx.remaining_parts * excess_defect * ctx.part_value

        # 즉시 교체: 공정 중간에 멈추므로 생산 압박만큼 정지 비용이 커진다
        cost_now = ctx.tool_price + downtime_cost * th["downtime_multiplier"][pressure.value]
        # 공정 후 교체: 남은 부품을 현재 공구로 가공하는 추가 위험 + 작업 전환과 겹쳐 줄어든 교체 비용
        cost_after_job = ctx.tool_price + downtime_cost * th["after_job_downtime_ratio"] + risk_cost
        # 계속 사용: 교체 비용은 뒤로 미루고 추가 위험만 진다
        cost_continue = risk_cost

        costs = {
            Action.REPLACE_NOW: cost_now,
            Action.REPLACE_AFTER_JOB: cost_after_job,
            Action.CONTINUE: cost_continue,
        }
        recommended = min(costs, key=costs.get)

        reasons = [
            f"[{ctx.scenario_id}] 기대 비용(원): 즉시 교체 {cost_now:,.0f} / 공정 후 교체 {cost_after_job:,.0f} / 계속 사용 {cost_continue:,.0f}",
            f"남은 부품 {ctx.remaining_parts}개 (부품가치 {ctx.part_value:,.0f}원), 공정 진행률 {ctx.process_progress_pct:.0f}%, "
            f"납기 여유 {ctx.due_slack_min:.0f}분, 우선순위 {ctx.production_priority} → 생산 압박 {pressure.value}",
        ]
        if ctx.tool_stock <= 0:
            reasons.append("여분 공구 재고 없음")
        if not ctx.inspection_available:
            reasons.append("현장 검사 불가")

        return EconomicsReport(
            cost_replace_now=cost_now,
            cost_replace_after_job=cost_after_job,
            cost_continue=cost_continue,
            production_pressure=pressure,
            tool_available=ctx.tool_stock > 0,
            inspection_available=ctx.inspection_available,
            recommended=recommended,
            reasons=reasons,
        )

    def _production_pressure(self, ctx: ProductionContext) -> RiskLevel:
        slack = self.thresholds["economics"]["pressure_slack_min"]
        if ctx.due_slack_min < slack["high"]:
            idx = 2
        elif ctx.due_slack_min < slack["medium"]:
            idx = 1
        else:
            idx = 0
        if ctx.production_priority.lower() == "high":
            idx = min(idx + 1, 2)
        return LEVELS[idx]
