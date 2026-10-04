from dataclasses import replace

from src.agents.economics_agent import EconomicsAgent
from src.agents.master_agent import MasterAgent
from src.agents.quality_agent import QualityAgent
from src.schemas import Action, RiskLevel, ToolState
from src.simulation.production_sim import default_context
from tests.helpers import make_wear


def decide(wear, ctx=None, state=None):
    ctx = ctx or default_context()
    quality = QualityAgent().analyze(wear)
    economics = EconomicsAgent().analyze(quality, ctx)
    return MasterAgent().analyze(wear, quality, economics, state or ToolState("T01"))


def test_quality_uses_worst_edge_not_mean():
    # 평균(0.155 mm)으로는 LOW지만 Edge 3(0.225 mm) 기준으로는 MEDIUM
    wear = make_wear([0.13, 0.135, 0.225, 0.13])
    report = QualityAgent().analyze(wear)
    assert report.basis_edge == 3
    assert report.risk_level == RiskLevel.MEDIUM
    assert QualityAgent().analyze(make_wear([wear.vb_mean] * 4)).risk_level == RiskLevel.LOW


def test_low_wear_continues():
    assert decide(make_wear([0.05, 0.05, 0.05, 0.05])).action == Action.CONTINUE


def test_vb_limit_replaces_now():
    assert decide(make_wear([0.10, 0.10, 0.31, 0.10], uncertainty=0.005)).action == Action.REPLACE_NOW


def test_uneven_wear_triggers_inspection_of_worst_edge():
    decision = decide(make_wear([0.10, 0.10, 0.16, 0.10]))
    assert decision.action == Action.INSPECT_EDGE
    assert decision.target_edge == 3


def test_measured_edge_is_not_reinspected_until_wear_grows():
    state = ToolState("T01")
    state.edges[2].last_measured_vb_mm = 0.14
    assert decide(make_wear([0.10, 0.10, 0.16, 0.10]), state=state).action == Action.CONTINUE
    assert decide(make_wear([0.10, 0.10, 0.20, 0.10]), state=state).action == Action.INSPECT_EDGE


def test_bad_signal_requests_remeasure_until_limit():
    wear = make_wear([0.05] * 4, signal_quality=0.5)
    assert decide(wear).action == Action.REMEASURE
    exhausted = ToolState("T01", rechecks_this_cycle=2)
    assert decide(wear, state=exhausted).action == Action.CONTINUE


def test_medium_risk_without_stock_replaces_after_job():
    wear = make_wear([0.22, 0.22, 0.22, 0.22], uncertainty=0.005)
    ctx = replace(default_context(), tool_stock=0)
    assert decide(wear, ctx=ctx).action == Action.REPLACE_AFTER_JOB


def test_medium_risk_depends_on_parts_left_and_due_pressure():
    wear = make_wear([0.22, 0.22, 0.22, 0.22], uncertainty=0.005)
    # 남은 부품이 많으면 불량 위험이 커서 즉시 교체
    assert decide(wear).action == Action.REPLACE_NOW
    # 마지막 부품 1개 + 납기 임박이면 공정을 마치고 교체
    ctx = replace(default_context(), remaining_parts=1, due_hours=0.03)
    assert decide(wear, ctx=ctx).action == Action.REPLACE_AFTER_JOB


def test_production_pressure():
    agent = EconomicsAgent()
    quality = QualityAgent().analyze(make_wear([0.05] * 4))
    assert agent.analyze(quality, default_context()).production_pressure == RiskLevel.LOW
    urgent = replace(default_context(), due_hours=1.1)
    assert agent.analyze(quality, urgent).production_pressure == RiskLevel.HIGH
