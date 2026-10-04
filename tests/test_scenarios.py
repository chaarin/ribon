"""팀 정의 Agent 테스트 케이스 (data/reference/agent_test_cases.csv) TC01~TC06."""
import csv

import numpy as np
import pytest

from src.config.settings import ROOT_DIR, SENSOR_CHANNELS
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, InspectionResult, SensorWindow
from src.simulation.production_sim import get_scenario
from tests.helpers import decide, make_wear

CASES = {
    row["Test_ID"]: row
    for row in csv.DictReader(open(ROOT_DIR / "data/reference/agent_test_cases.csv", encoding="utf-8"))
}


def ctx_of(test_id: str):
    return get_scenario(CASES[test_id]["Scenario_ID"])


def test_tc01_normal_wear_continues():
    wear = make_wear([0.08, 0.085, 0.082, 0.079], increments=[0.005] * 4)
    assert decide(wear, ctx=ctx_of("TC01")).action == Action.CONTINUE


def test_tc02_uneven_edge3_inspects_edge3():
    wear = make_wear([0.13, 0.13, 0.21, 0.13], increments=[0.005, 0.005, 0.03, 0.005])
    decision = decide(wear, ctx=ctx_of("TC02"))
    assert decision.action == Action.INSPECT_EDGE
    assert decision.target_edge == 3


def test_tc03_expensive_part_high_risk_replaces_now():
    ctx = ctx_of("TC03")
    assert ctx.part_value >= 20_000_000
    wear = make_wear([0.20, 0.22, 0.33, 0.21], uncertainty=0.01)
    assert decide(wear, ctx=ctx).action == Action.REPLACE_NOW


def test_tc04_no_stock_replaces_after_job():
    ctx = ctx_of("TC04")
    assert ctx.tool_stock == 0
    wear = make_wear([0.22, 0.23, 0.22, 0.21], uncertainty=0.01)
    assert decide(wear, ctx=ctx).action == Action.REPLACE_AFTER_JOB


def test_tc05_inspection_feedback_updates_decision():
    pipeline = MaintenancePipeline()
    ctx = ctx_of("TC05")
    vb = [0.15, 0.24, 0.15, 0.15]
    window = SensorWindow(
        tool_id="T01",
        cycle=1,
        sampling_rate_hz=1000,
        signals={ch: np.random.default_rng(0).normal(size=1000) for ch in SENSOR_CHANNELS},
        cumulative_cut_time_min=2.0,
        vb_label_mm=[v + 0.03 for v in vb],  # 더미 모델의 -0.03 과소추정을 상쇄
    )
    first = pipeline.run_cycle(window, ctx)
    assert first.action == Action.INSPECT_EDGE
    assert first.target_edge == 2

    # 검사 결과: Edge 2 손상 확인 (실측 VB가 교체 한계 초과)
    after = pipeline.apply_feedback(InspectionResult("T01", 2, vb_measured_mm=0.32))
    assert after.action == Action.REPLACE_NOW
    assert "여분 공구 없음" in after.reasons[0]  # S22는 재고 0


def test_tc06_missing_sensor_requests_remeasure():
    pipeline = MaintenancePipeline()
    signals = {ch: np.random.default_rng(0).normal(size=1000) for ch in SENSOR_CHANNELS}
    del signals["Fz"]
    window = SensorWindow("T01", 1, 1000, signals, cumulative_cut_time_min=2.0, vb_label_mm=[0.1] * 4)
    decision = pipeline.run_cycle(window, ctx_of("TC06"))
    assert decision.action == Action.REMEASURE
    assert any("Fz" in r for r in decision.reasons)


@pytest.mark.parametrize("test_id", sorted(CASES))
def test_every_case_has_expected_action(test_id):
    assert CASES[test_id]["Expected_Action"]
