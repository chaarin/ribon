import pytest

from src.data.synthetic import generate_tool_run
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, InspectionResult
from src.simulation.production_sim import get_scenario


def test_feedback_corrects_prediction_and_reruns_decision():
    pipeline = MaintenancePipeline()
    windows = generate_tool_run("T01", n_cycles=10)
    ctx = get_scenario()

    decision = None
    for window in windows:
        decision = pipeline.run_cycle(window, ctx)
        if decision.action == Action.INSPECT_EDGE:
            break
    assert decision.action == Action.INSPECT_EDGE

    edge = decision.target_edge
    measured = window.vb_label_mm[edge - 1]
    after = pipeline.apply_feedback(InspectionResult("T01", edge, measured))
    assert after.action != Action.INSPECT_EDGE

    state = pipeline.state_store.get("T01")
    assert state.edges[edge - 1].bias_mm > 0  # 더미 모델은 과소추정하므로 양의 보정
    assert len(pipeline.history.records("feedback")) == 1

    # 다음 Cycle 예측에 보정값이 반영된다
    next_window = windows[window.cycle]
    pipeline.run_cycle(next_window, ctx)
    corrected = state.edges[edge - 1].vb_mm
    assert corrected == pytest.approx(next_window.vb_label_mm[edge - 1], abs=0.02)


def test_full_run_ends_with_replacement():
    pipeline = MaintenancePipeline()
    ctx = get_scenario()
    actions = []
    for window in generate_tool_run("T01", n_cycles=25):
        decision = pipeline.run_cycle(window, ctx)
        while decision.action == Action.INSPECT_EDGE:
            measured = window.vb_label_mm[decision.target_edge - 1]
            decision = pipeline.apply_feedback(InspectionResult("T01", decision.target_edge, measured))
        actions.append(decision.action)
        if decision.action in (Action.REPLACE_NOW, Action.REPLACE_AFTER_JOB):
            pipeline.confirm_replacement("T01")
            break
    assert actions[-1] in (Action.REPLACE_NOW, Action.REPLACE_AFTER_JOB)
    assert pipeline.state_store.get("T01").cut_time_min == 0.0


def test_feedback_without_history_raises():
    with pytest.raises(ValueError):
        MaintenancePipeline().apply_feedback(InspectionResult("T99", 1, 0.1))
