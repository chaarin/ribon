"""Economics / Production Agent: 행동별 기대 비용과 생산 압박을 분석한다. (Track D)"""
from src.agents.base import BaseAgent
from src.schemas import Action, EconomicsReport, ProductionContext, QualityReport, RiskLevel


class EconomicsAgent(BaseAgent):
    name = "economics"

    def analyze(self, quality: QualityReport, ctx: ProductionContext) -> EconomicsReport:
        th = self.thresholds["economics"]
        level = quality.risk_level.value
        p_defect = th["defect_probability"][level]
        p_break = th["breakage_probability"][level]

        pressure = self._production_pressure(ctx)
        multiplier = th["downtime_multiplier"][pressure.value]

        downtime_cost = ctx.change_time_min * ctx.downtime_cost_per_min
        risk_cost = ctx.remaining_parts * p_defect * ctx.part_value + p_break * ctx.breakage_cost

        # 즉시 교체: 공정 중간에 멈추므로 생산 압박만큼 정지 비용이 커진다
        cost_now = ctx.tool_price + downtime_cost * multiplier
        # 공정 후 교체: 남은 부품을 현재 공구로 가공하는 위험 + 작업 전환과 겹쳐 줄어든 교체 비용
        cost_after_job = ctx.tool_price + downtime_cost * th["after_job_downtime_ratio"] + risk_cost
        # 계속 사용: 교체 비용은 뒤로 미루고 위험만 진다
        cost_continue = risk_cost

        costs = {
            Action.REPLACE_NOW: cost_now,
            Action.REPLACE_AFTER_JOB: cost_after_job,
            Action.CONTINUE: cost_continue,
        }
        recommended = min(costs, key=costs.get)

        reasons = [
            f"기대 비용(원): 즉시 교체 {cost_now:,.0f} / 공정 후 교체 {cost_after_job:,.0f} / 계속 사용 {cost_continue:,.0f}",
            f"남은 부품 {ctx.remaining_parts}개, 납기까지 {ctx.due_hours:.1f}시간 → 생산 압박 {pressure.value}",
        ]
        if ctx.tool_stock <= 0:
            reasons.append("교체용 공구 재고 없음")

        return EconomicsReport(
            cost_replace_now=cost_now,
            cost_replace_after_job=cost_after_job,
            cost_continue=cost_continue,
            production_pressure=pressure,
            tool_available=ctx.tool_stock > 0,
            recommended=recommended,
            reasons=reasons,
        )

    def _production_pressure(self, ctx: ProductionContext) -> RiskLevel:
        work_hours = ctx.remaining_parts * ctx.cycle_time_min / 60
        if work_hours <= 0:
            return RiskLevel.LOW
        slack = ctx.due_hours / work_hours
        ratio = self.thresholds["economics"]["pressure_slack_ratio"]
        if slack < ratio["high"]:
            return RiskLevel.HIGH
        if slack < ratio["medium"]:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
