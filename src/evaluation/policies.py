"""교체 판단 방식 비교. (Step 3)

공구 1개의 실제 마모 기록을 '모든 공구가 같은 수명을 반복한다'고 보고(갱신 과정), Cycle k에 교체하는 방식의
**윙 리브 1개당 손실 시간**과 **윙 리브 1개당 공구 사용량**을 비교한다.

  공구 수명 1회의 손실 시간 = 교체 시간 + 검사 횟수 × 검사 시간 + Σ_{t≤k} 불량 확률_t × 불량 1건당 손실 시간
  윙 리브 1개당 손실 = 위 값 × (윙 리브당 Cycle 수 / k),  윙 리브 1개당 공구 사용량 = 윙 리브당 Cycle 수 / k

- 불량 확률_t: Cycle t의 **실제** 최대 날 VBmax로 정한 위험 등급(공구 용도별 구간)의 확률
- 시간 값·확률은 모두 MVP 가정이다 (thresholds.yaml, data/reference/*_context_sim.csv)
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.agents.economics_agent import defect_loss_min
from src.config.settings import load_thresholds
from src.models.tool_wear_model import LABEL_COLUMNS, worst_edge_vb
from src.schemas import ProductionContext, RiskLevel

VB_LIMIT_MM = 0.3


def true_risk_levels(df: pd.DataFrame, tool_purpose: str = "finishing", thresholds: dict | None = None) -> list[RiskLevel]:
    bands = (thresholds or load_thresholds())["tool_purpose"][tool_purpose]
    levels = []
    for vb in worst_edge_vb(df):
        if vb >= bands["vb_high_mm"]:
            levels.append(RiskLevel.HIGH)
        elif vb >= bands["vb_medium_mm"]:
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
    loss_min_per_rib: float
    tools_per_rib: float
    defect_loss_min_per_rib: float  # 손실 중 불량에 의한 부분


def evaluate(
    name: str,
    replace_cycle: int | None,
    n_inspections: int,
    df: pd.DataFrame,
    ctx: ProductionContext,
    thresholds: dict | None = None,
    defect_scale: float = 1.0,
) -> PolicyOutcome:
    """defect_scale: 불량 확률 가정을 몇 배로 볼지 (민감도 분석용)"""
    th = thresholds or load_thresholds()
    prod = th["production"]
    cycles = df["cycle"].to_numpy()
    k = replace_cycle if replace_cycle is not None else int(cycles[-1])
    used = cycles <= k
    p_defect = th["economics"]["defect_probability"]
    per_defect = defect_loss_min(ctx.tool_purpose, th)
    levels = true_risk_levels(df, ctx.tool_purpose, th)
    defect_loss = sum(min(1.0, p_defect[lvl.value] * defect_scale) * per_defect for lvl, u in zip(levels, used) if u)
    total = ctx.change_time_min + n_inspections * prod["inspection_time_min"] + defect_loss
    per_rib = prod["cycles_per_rib"] / k
    return PolicyOutcome(
        name=name,
        replace_cycle=k,
        replaced=replace_cycle is not None,
        n_inspections=n_inspections,
        over_limit_cycles=int(np.sum(worst_edge_vb(df)[used] >= VB_LIMIT_MM)),
        loss_min_per_rib=total * per_rib,
        tools_per_rib=per_rib,
        defect_loss_min_per_rib=defect_loss * per_rib,
    )


IDEAL = "최대 날 VB ≥ 주의 기준 (매 Cycle 검사, 이상적)"
PER_CYCLE_INSPECTION = ("평균 VB ≥ 0.3 (매 Cycle 검사)", "최대 날 VB ≥ 0.3 (매 Cycle 검사)", IDEAL)


def baseline_replace_cycles(
    df: pd.DataFrame, sensor_pred: np.ndarray, tool_purpose: str = "finishing", thresholds: dict | None = None
) -> dict[str, int | None]:
    """고정 기준 교체 방식들. '매 Cycle 검사' 방식은 날별 마모를 매번 실측한다고 가정한다 (검사 비용 포함)."""
    caution = (thresholds or load_thresholds())["tool_purpose"][tool_purpose]["vb_medium_mm"]
    cycles = df["cycle"].to_numpy()
    worst = worst_edge_vb(df)
    return {
        "평균 VB ≥ 0.3 (매 Cycle 검사)": first_cycle(df[LABEL_COLUMNS].mean(axis=1).to_numpy() >= VB_LIMIT_MM, cycles),
        "최대 날 VB ≥ 0.3 (매 Cycle 검사)": first_cycle(worst >= VB_LIMIT_MM, cycles),
        # 시스템과 같은 품질 기준을 매 Cycle 정확히 안다고 가정한 이상적인 방식 (공정한 비교 기준)
        IDEAL: first_cycle(worst >= caution, cycles),
        "센서 예측 VB ≥ 0.3 (검사 없음)": first_cycle(sensor_pred >= VB_LIMIT_MM, cycles),
    }


def compare_policies(
    df: pd.DataFrame, ctx: ProductionContext, system_replace: int | None, system_inspections: int,
    sensor_pred: np.ndarray, thresholds: dict | None = None, defect_scale: float = 1.0,
) -> list[PolicyOutcome]:
    th = thresholds or load_thresholds()
    outcomes = [evaluate("Multi-Agent 시스템 (센서 + 필요할 때 검사)", system_replace, system_inspections, df, ctx, th, defect_scale)]
    for name, k in baseline_replace_cycles(df, sensor_pred, ctx.tool_purpose, th).items():
        n_insp = (k or int(df["cycle"].max())) if name in PER_CYCLE_INSPECTION else 0
        outcomes.append(evaluate(name, k, n_insp, df, ctx, th, defect_scale))
    return outcomes
