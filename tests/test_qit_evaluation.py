"""실제 QIT-CEMC 특징으로 모델, 재생, 비용 평가를 확인한다 (data/features/qit_cemc_features.csv 사용)."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.config.settings import N_EDGES
from src.evaluation.policies import baseline_replace_cycles, evaluate
from src.evaluation.replay import out_of_sample_model, qit_windows, run_system
from src.feedback.feedback_handler import apply_inspection
from src.models.tool_wear_model import blocked_cv_predictions, load_features, train_tool_wear_model, worst_edge_vb
from src.schemas import Action, InspectionResult, ToolState
from src.simulation.production_sim import get_scenario
from tests.helpers import make_wear


@pytest.fixture(scope="module")
def df():
    return load_features()


@pytest.fixture(scope="module")
def model(df):
    return out_of_sample_model(df)


def test_features_cover_all_cycles(df):
    assert df["cycle"].tolist() == list(range(1, 69))
    assert df[[c for c in df.columns if c.startswith(("Fx", "Fy", "Fz", "Mz"))]].notna().all().all()


def test_tool_model_predicts_same_value_for_all_edges(df):
    model = train_tool_wear_model(df)
    window = qit_windows(df)[30]
    vb, unc = model.predict(window.features, window)
    assert vb.shape == (N_EDGES,) and len(set(vb)) == 1
    assert 0 < model.sigma_mm < 0.2


def test_blocked_cv_does_not_use_own_label(df):
    changed = df.copy()
    changed.loc[changed["cycle"] == 40, "edge1_vbmax_mm"] = 5.0  # 자기 라벨을 크게 바꿔도
    assert blocked_cv_predictions(changed)[40] == pytest.approx(blocked_cv_predictions(df)[40])  # 자기 예측은 그대로


def test_replay_inspects_and_replaces_without_remeasure(df, model):
    result = run_system(df, get_scenario("S15"), model=model)
    assert result.replace_cycle is not None
    assert result.inspection_cycles  # 검사 가능한 시나리오에서는 검사로 날별 상태를 확인한다
    # 진동이 없는 Cycle(2, 21, ...)이 있어도 힘/토크 모델이라 재측정을 요구하지 않는다
    assert all(d.action != Action.REMEASURE for d in result.decisions)
    # 교체 전까지 실제 최대 날이 한계(0.3 mm)를 넘은 상태로 가공하지 않는다
    assert worst_edge_vb(df)[: result.replace_cycle].max() < 0.3


def test_replay_without_inspection_never_inspects(df, model):
    ctx = replace(get_scenario("S15"), inspection_available=False)
    result = run_system(df, ctx, model=model)
    assert result.inspection_cycles == []
    assert result.replace_cycle is not None


def test_baselines_match_label_facts(df, model):
    preds = np.array([model.predictions[c] for c in df["cycle"]])
    base = baseline_replace_cycles(df, preds)
    assert base["평균 VB ≥ 0.3 (매 Cycle 검사)"] == 53
    assert base["최대 날 VB ≥ 0.3 (매 Cycle 검사)"] == 31
    assert base["최대 날 VB ≥ 주의 기준 (매 Cycle 검사, 이상적)"] == 11


def test_lifecycle_loss_formula():
    df = pd.DataFrame({"cycle": [1, 2, 3], **{f"edge{i}_vbmax_mm": [0.1, 0.25, 0.35] for i in range(1, 5)}})
    ctx = replace(get_scenario("S15"), change_time_min=10, tool_purpose="finishing")
    th = {
        "tool_purpose": {"finishing": {"vb_medium_mm": 0.2, "vb_high_mm": 0.3, "defect_loss": "rib"}},
        "production": {"cycles_per_rib": 10, "cycle_time_min": 2.0, "inspection_time_min": 5},
        "economics": {"defect_probability": {"LOW": 0.01, "MEDIUM": 0.05, "HIGH": 0.3}},
    }
    o = evaluate("t", 2, n_inspections=1, df=df, ctx=ctx, thresholds=th)
    # 공구 수명 1회: 교체 10 + 검사 5 + 불량 (0.01 + 0.05) × 윙 리브 20분 = 16.2분, 2 Cycle → 윙 리브(10 Cycle)당 5배
    assert o.loss_min_per_rib == pytest.approx(16.2 * 5)
    assert o.tools_per_rib == pytest.approx(5.0)
    assert o.over_limit_cycles == 0
    assert evaluate("t", None, 0, df, ctx, th).over_limit_cycles == 1


def test_presets_lead_to_different_decisions(df, model):
    from src.simulation.production_sim import PRESETS

    outcomes = {pid: run_system(df, p.context(), model=model) for pid, p in PRESETS.items()}
    actions = {pid: (r.replace_cycle, r.decisions[-1].action) for pid, r in outcomes.items()}
    assert actions["finishing"][1] == Action.REPLACE_NOW
    assert actions["no_stock"][1] == Action.REPLACE_AFTER_JOB
    assert actions["due_tight"][1] == Action.REPLACE_AFTER_JOB
    assert actions["roughing"][0] > actions["finishing"][0]  # 황삭은 더 오래 쓴다
    assert outcomes["roughing"].inspection_cycles == []  # 황삭은 검사 가치가 검사 시간보다 작다
    assert outcomes["no_inspection"].inspection_cycles == []


def test_increment_after_inspection_compares_measurements():
    state = ToolState("T01")
    state.edges[0].last_measured_vb_mm, state.edges[0].last_measured_cycle = 0.10, 5
    wear = make_wear([0.30, 0.1, 0.1, 0.1], increments=[0.2, 0, 0, 0], cycle=10)
    out = apply_inspection(InspectionResult("T01", 1, 0.20), wear, state)
    # 실측 - 직전 예측(0.3)이 아니라 실측끼리: (0.20 - 0.10) / 5 Cycle
    assert out.edge(1).increment_mm == pytest.approx(0.02)
