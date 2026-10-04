from src.agents.economics_agent import EconomicsAgent
from src.agents.quality_agent import QualityAgent
from src.schemas import Action, RiskLevel, ToolState
from tests.helpers import decide, make_wear, scenario


def test_quality_uses_worst_edge_not_mean():
    # 평균(0.16 mm)으로는 LOW지만 Edge 3(0.22 mm) 기준으로는 MEDIUM 이상
    wear = make_wear([0.14, 0.14, 0.22, 0.14])
    report = QualityAgent().analyze(wear)
    assert report.basis_edge == 3
    assert report.risk_level != RiskLevel.LOW
    assert QualityAgent().analyze(make_wear([wear.vb_mean] * 4)).risk_level == RiskLevel.LOW


def test_quality_levels_by_vb():
    agent = QualityAgent()
    assert agent.analyze(make_wear([0.15] * 4)).risk_level == RiskLevel.LOW
    assert agent.analyze(make_wear([0.25] * 4)).risk_level == RiskLevel.MEDIUM
    assert agent.analyze(make_wear([0.31] * 4)).risk_level == RiskLevel.HIGH


def test_uneven_or_rapid_wear_escalates_only_from_medium():
    agent = QualityAgent()
    # LOW 구간의 편마모는 등급을 올리지 않는다 (검사는 Master가 판단)
    assert agent.analyze(make_wear([0.10, 0.10, 0.16, 0.10])).risk_level == RiskLevel.LOW
    assert agent.analyze(make_wear([0.15, 0.15, 0.25, 0.15])).risk_level == RiskLevel.HIGH
    rapid = make_wear([0.25] * 4, increments=[0.0, 0.0, 0.03, 0.0])
    assert agent.analyze(rapid).risk_level == RiskLevel.HIGH


def test_quality_cites_reference_data():
    report = QualityAgent().analyze(make_wear([0.13] * 4))
    assert report.reference_ra_range_um is not None
    assert any("Nguyen" in r for r in report.reasons)


def test_low_wear_continues():
    assert decide(make_wear([0.05, 0.05, 0.05, 0.05])).action == Action.CONTINUE


def test_vb_limit_replaces_now():
    assert decide(make_wear([0.10, 0.10, 0.31, 0.10], uncertainty=0.005)).action == Action.REPLACE_NOW


def test_uneven_wear_triggers_inspection_of_worst_edge():
    decision = decide(make_wear([0.10, 0.10, 0.16, 0.10]))
    assert decision.action == Action.INSPECT_EDGE
    assert decision.target_edge == 3


def test_no_inspection_when_unavailable():
    ctx = scenario(inspection_available=False)
    assert decide(make_wear([0.10, 0.10, 0.16, 0.10]), ctx=ctx).action == Action.CONTINUE


def test_measured_edge_is_not_reinspected_until_wear_grows():
    state = ToolState("T01")
    state.edges[2].last_measured_vb_mm = 0.12
    assert decide(make_wear([0.10, 0.10, 0.16, 0.10]), state=state).action == Action.CONTINUE
    assert decide(make_wear([0.10, 0.10, 0.18, 0.10]), state=state).action == Action.INSPECT_EDGE


def test_bad_signal_requests_remeasure_until_limit():
    wear = make_wear([0.05] * 4, signal_quality=0.5)
    assert decide(wear).action == Action.REMEASURE
    exhausted = decide(wear, state=ToolState("T01", rechecks_this_cycle=2))
    assert exhausted.action == Action.CONTINUE
    assert "센서 이상" in exhausted.reasons[0]
    assert exhausted.confidence < 0.5


def test_medium_risk_cost_tradeoff():
    wear = make_wear([0.22] * 4, uncertainty=0.005)
    # 고가 부품이 많이 남으면 즉시 교체
    assert decide(wear).action == Action.REPLACE_NOW
    # 재고가 없으면 공정 후 교체
    assert decide(wear, ctx=scenario(tool_stock=0)).action == Action.REPLACE_AFTER_JOB
    # 저가 부품 1개만 남고 납기가 급하면 공정 후 교체가 더 저렴
    cheap = scenario("S01", part_value=50_000, tool_stock=1, due_slack_min=30, production_priority="High")
    assert decide(wear, ctx=cheap).action == Action.REPLACE_AFTER_JOB


def test_low_risk_has_no_extra_cost():
    quality = QualityAgent().analyze(make_wear([0.05] * 4))
    report = EconomicsAgent().analyze(quality, scenario())
    assert report.cost_continue == 0
    assert report.recommended == Action.CONTINUE


def test_production_pressure():
    agent = EconomicsAgent()
    quality = QualityAgent().analyze(make_wear([0.05] * 4))
    assert agent.analyze(quality, scenario(due_slack_min=720, production_priority="Low")).production_pressure == RiskLevel.LOW
    assert agent.analyze(quality, scenario(due_slack_min=120, production_priority="Low")).production_pressure == RiskLevel.MEDIUM
    assert agent.analyze(quality, scenario(due_slack_min=120, production_priority="High")).production_pressure == RiskLevel.HIGH
