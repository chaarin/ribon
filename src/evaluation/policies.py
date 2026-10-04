"""교체 판단 방식 비교. (Step 3)

공구 1개의 실제 마모 기록을 '모든 공구가 같은 수명을 반복한다'고 보고(갱신 과정), Cycle k에 교체하는 방식의
Cycle당 기대 비용 = (공구값 + 교체 정지비용 + 검사 정지비용 + Σ_{t≤k} 불량 기대손실_t) / k 로 비교한다.

- 불량 기대손실_t: Cycle t의 **실제** 최대 날 VBmax로 정한 위험 등급의 불량 확률 × 부품가치 (Cycle당 부품 1개 가정)
- 비용 값은 모두 MVP 시뮬레이션 입력이다 (data/reference/*_context_sim.csv, thresholds.yaml).
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config.settings import load_thresholds
from src.models.tool_wear_model import LABEL_COLUMNS, worst_edge_vb
from src.schemas import ProductionContext, RiskLevel

VB_LIMIT_MM = 0.3
VB_CAUTION_MM = 0.2


def true_risk_levels(df: pd.DataFrame, thresholds: dict | None = None) -> list[RiskLevel]:
    th = (thresholds or load_thresholds())["quality"]
    levels = []
    for vb in worst_edge_vb(df):
        if vb >= th["vb_high_mm"]:
            levels.append(RiskLevel.HIGH)
        elif vb >= th["vb_medium_mm"]:
            levels.append(RiskLevel.MEDIUM)
        else:
            levels.append(RiskLevel.LOW)
    return levels


def first_cycle(mask: np.ndarray, cycles: np.ndarray) -> int | None:
    return int(cycles[np.argmax(mask)]) if mask.any() else None


@dataclass
class PolicyOutcome:
    name: str
    replace_cycle: int  # 교체한 Cycle (끝까지 교체하지 않으면 마지막 Cycle)
    replaced: bool
    n_inspections: int
    over_limit_cycles: int  # 교체 전까지 실제 최대 날 VB가 0.3 mm 이상인 상태로 가공한 Cycle 수
    cost_per_cycle: float


def evaluate(
    name: str,
    replace_cycle: int | None,
    n_inspections: int,
    df: pd.DataFrame,
    ctx: ProductionContext,
    thresholds: dict | None = None,
) -> PolicyOutcome:
    th = thresholds or load_thresholds()
    cycles = df["cycle"].to_numpy()
    k = replace_cycle if replace_cycle is not None else int(cycles[-1])
    used = cycles <= k
    p_defect = th["economics"]["defect_probability"]
    defect_cost = sum(p_defect[level.value] * ctx.part_value for level, u in zip(true_risk_levels(df, th), used) if u)
    downtime = ctx.downtime_cost_per_min
    total = (
        ctx.tool_price
        + ctx.change_time_min * downtime
        + n_inspections * th["economics"]["inspection_time_min"] * downtime
        + defect_cost
    )
    return PolicyOutcome(
        name=name,
        replace_cycle=k,
        replaced=replace_cycle is not None,
        n_inspections=n_inspections,
        over_limit_cycles=int(np.sum(worst_edge_vb(df)[used] >= VB_LIMIT_MM)),
        cost_per_cycle=total / k,
    )


def baseline_replace_cycles(df: pd.DataFrame, sensor_pred: np.ndarray) -> dict[str, int | None]:
    """고정 기준 교체 방식들. 라벨 기반 방식은 매 Cycle 날별 마모를 정확히 안다고 가정한 이상적인 경우다."""
    cycles = df["cycle"].to_numpy()
    return {
        "평균 VB ≥ 0.3 (매 Cycle 실측 가정)": first_cycle(df[LABEL_COLUMNS].mean(axis=1).to_numpy() >= VB_LIMIT_MM, cycles),
        "최대 날 VB ≥ 0.3 (매 Cycle 실측 가정)": first_cycle(worst_edge_vb(df) >= VB_LIMIT_MM, cycles),
        # 시스템과 같은 품질 기준(0.2 mm)을 매 Cycle 정확히 안다고 가정한 이상적인 방식 (공정한 비교 기준)
        "최대 날 VB ≥ 0.2 (매 Cycle 실측 가정, 이상적)": first_cycle(worst_edge_vb(df) >= VB_CAUTION_MM, cycles),
        "센서 예측 VB ≥ 0.3 (검사 없음)": first_cycle(sensor_pred >= VB_LIMIT_MM, cycles),
    }
