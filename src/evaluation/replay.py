"""실제 QIT-CEMC 68 Cycle을 Multi-Agent 시스템에 순서대로 재생한다. (Step 3)

- 각 Cycle은 미리 추출한 특징(data/features/qit_cemc_features.csv)으로 재생한다.
- 시스템이 검사를 지시하면 그 Cycle의 실제 라벨(Edge 1~4 VBmax)을 현장 실측값으로 넣는다.
"""
import math
from dataclasses import dataclass, field

import pandas as pd

from src.config.settings import N_EDGES
from src.memory.history_store import HistoryStore
from src.models.tool_wear_model import LABEL_COLUMNS, PrecomputedWearModel, blocked_cv_predictions, worst_edge_vb
from src.agents.wear_agent import WearAgent
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, Decision, InspectionResult, ProductionContext, SensorWindow

TOOL_ID = "QIT-CEMC"


def qit_windows(df: pd.DataFrame) -> list[SensorWindow]:
    windows = []
    for row in df.to_dict("records"):
        features = {k: v for k, v in row.items() if isinstance(v, (int, float)) and k not in LABEL_COLUMNS}
        windows.append(
            SensorWindow(
                tool_id=TOOL_ID,
                cycle=int(row["cycle"]),
                sampling_rate_hz=10_000.0,
                signals={},
                cumulative_cut_time_min=float(row["cut_time_min"]),
                vb_label_mm=[float(row[c]) for c in LABEL_COLUMNS],
                features=features,
            )
        )
    return windows


def out_of_sample_model(df: pd.DataFrame) -> PrecomputedWearModel:
    """각 Cycle을 그 Cycle(과 앞뒤 5개)을 학습에 쓰지 않은 모델로 예측한 값으로 재생한다."""
    preds = blocked_cv_predictions(df)
    sigma = float((preds.to_numpy() - worst_edge_vb(df)).std())
    return PrecomputedWearModel(predictions=preds.to_dict(), sigma_mm=sigma)


@dataclass
class ReplayResult:
    replace_cycle: int | None  # 교체를 결정한 Cycle (끝까지 교체하지 않으면 None)
    inspection_cycles: list[int] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)  # 각 Cycle의 최종 판단


def run_system(
    df: pd.DataFrame,
    ctx: ProductionContext,
    model=None,
    on_event=None,
) -> ReplayResult:
    """공구 하나의 수명을 처음부터 재생하고, 교체 결정이 나오면 멈춘다.

    on_event(kind, payload): 데모 출력용 콜백 (kind: "decision" / "inspection")
    """
    model = model or out_of_sample_model(df)
    pipeline = MaintenancePipeline(wear_agent=WearAgent(model=model), history=HistoryStore())
    result = ReplayResult(replace_cycle=None)
    emit = on_event or (lambda kind, payload: None)

    for window in qit_windows(df):
        decision = pipeline.run_cycle(window, ctx)
        emit("decision", decision)
        while decision.action in (Action.INSPECT_EDGE, Action.REMEASURE):
            if decision.action == Action.REMEASURE:
                decision = pipeline.run_cycle(window, ctx)  # 재생 데이터는 같은 값으로 재측정된다
            else:
                edges = [decision.target_edge] if decision.target_edge else list(range(1, N_EDGES + 1))
                inspections = [InspectionResult(TOOL_ID, e, window.vb_label_mm[e - 1]) for e in edges]
                result.inspection_cycles.append(window.cycle)
                emit("inspection", inspections)
                decision = pipeline.apply_feedback(inspections)
            emit("decision", decision)
        result.decisions.append(decision)
        if decision.action in (Action.REPLACE_NOW, Action.REPLACE_AFTER_JOB):
            result.replace_cycle = window.cycle
            break
    return result


def is_finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
