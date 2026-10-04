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
    # 급속 마모는 실측끼리 비교한 증가량으로만 본다 (센서 예측끼리의 차이는 노이즈)
    rapid_measured = make_wear([0.25] * 4, increments=[0.0, 0.0, 0.03, 0.0], measured=True)
    assert agent.analyze(rapid_measured).risk_level == RiskLevel.HIGH
    rapid_predicted = make_wear([0.25] * 4, increments=[0.0, 0.0, 0.03, 0.0])
    assert agent.analyze(rapid_predicted).risk_level == RiskLevel.MEDIUM


def test_roughing_tool_tolerates_more_wear():
    agent = QualityAgent()
    wear = make_wear([0.22] * 4)
    assert agent.analyze(wear, "finishing").risk_level == RiskLevel.MEDIUM
    assert agent.analyze(wear, "roughing").risk_level == RiskLevel.LOW


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
    state.edges[2].last_measured_vb_mm = 0.14
    assert decide(make_wear([0.10, 0.10, 0.16, 0.10]), state=state).action == Action.CONTINUE
    assert decide(make_wear([0.10, 0.10, 0.18, 0.10]), state=state).action == Action.INSPECT_EDGE


def test_bad_signal_requests_remeasure_until_limit():
    wear = make_wear([0.05] * 4, signal_quality=0.5)
    assert decide(wear).action == Action.REMEASURE
    exhausted = decide(wear, state=ToolState("T01", rechecks_this_cycle=2))
    assert exhausted.action == Action.CONTINUE
    assert "센서 이상" in exhausted.reasons[0]
    assert exhausted.confidence < 0.5


def test_medium_risk_decisions_depend_on_rib_position_stock_and_due():
    wear = make_wear([0.22] * 4, uncertainty=0.005, measured=True)  # 실측으로 확인된 MEDIUM (정삭)
    early_in_rib = scenario(process_progress_pct=20)  # 남은 8 Cycle: 위험 27분 > 교체 15분
    assert decide(wear, ctx=early_in_rib).action == Action.REPLACE_NOW
    assert decide(wear, ctx=scenario(process_progress_pct=20, tool_stock=0)).action == Action.REPLACE_AFTER_JOB
    due_tight = scenario(process_progress_pct=20, due_slack_min=5, production_priority="High")
    assert decide(wear, ctx=due_tight).action == Action.REPLACE_AFTER_JOB
    # 윙 리브 끝 무렵: 남은 2 Cycle의 위험(6.8분) < 교체 15분 → 계속 가공
    assert decide(wear, ctx=scenario(process_progress_pct=80)).action == Action.CONTINUE
    # 윙 리브를 막 마친 시점: 다음 윙 리브 위험(34분) > 작업 전환 중 교체(7.5분) → 경계에서 교체
    assert decide(wear, ctx=scenario(process_progress_pct=100)).action == Action.REPLACE_AFTER_JOB


def test_roughing_keeps_cutting_at_medium_until_limit():
    ctx = scenario(process_progress_pct=20, tool_purpose="roughing")
    assert decide(make_wear([0.27] * 4, uncertainty=0.005, measured=True), ctx=ctx).action == Action.CONTINUE
    assert decide(make_wear([0.30] * 4, uncertainty=0.005, measured=True), ctx=ctx).action == Action.REPLACE_NOW


def test_low_risk_has_no_extra_loss():
    quality = QualityAgent().analyze(make_wear([0.05] * 4))
    report = EconomicsAgent().analyze(quality, scenario())
    assert report.loss_continue_min == 0
    assert report.recommended == Action.CONTINUE


def test_inspection_only_when_worth_more_than_its_time():
    wear = make_wear([0.18] * 4, uncertainty=0.04)
    assert decide(wear).action == Action.INSPECT_EDGE  # 정삭: 불량 1건 85분 → 검사 가치 큼
    assert decide(wear, ctx=scenario(tool_purpose="roughing")).action != Action.INSPECT_EDGE  # 황삭: 8.5분 → 검사보다 가공


def test_production_pressure():
    agent = EconomicsAgent()
    quality = QualityAgent().analyze(make_wear([0.05] * 4))
    assert agent.analyze(quality, scenario(due_slack_min=720, production_priority="Low")).production_pressure == RiskLevel.LOW
    assert agent.analyze(quality, scenario(due_slack_min=120, production_priority="Low")).production_pressure == RiskLevel.MEDIUM
    assert agent.analyze(quality, scenario(due_slack_min=120, production_priority="High")).production_pressure == RiskLevel.HIGH


def test_tool_level_prediction_triggers_all_edge_inspection():
    # 센서 모델은 4날 모두 같은 값(최대 마모 예측)을 준다 → 편마모는 모르지만 주의 구간이면 4날 검사
    decision = decide(make_wear([0.18] * 4, uncertainty=0.04))
    assert decision.action == Action.INSPECT_EDGE
    assert decision.target_edge is None


def test_tool_inspection_not_repeated_until_wear_grows():
    state = ToolState("T01")
    for e in state.edges:
        e.last_measured_vb_mm = 0.15
    state.edges[3].last_measured_vb_mm = 0.19
    assert decide(make_wear([0.20] * 4, uncertainty=0.04), state=state).action != Action.INSPECT_EDGE
    assert decide(make_wear([0.23] * 4, uncertainty=0.04), state=state).action == Action.INSPECT_EDGE


def test_confident_prediction_needs_no_tool_inspection():
    assert decide(make_wear([0.22] * 4, uncertainty=0.005)).action != Action.INSPECT_EDGE


def test_no_tool_inspection_below_caution_zone():
    assert decide(make_wear([0.12] * 4, uncertainty=0.04)).action == Action.CONTINUE
