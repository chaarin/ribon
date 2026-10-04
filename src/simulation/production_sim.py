"""MVP용 생산·비용 시나리오. (Track D)

data/reference/의 Economic_Context_Sim과 Production_Context_Sim을 Scenario_ID로 합친다.
모두 대회 MVP용 합성 값이며, 발표 시 'MVP 시뮬레이션 입력'으로 표기한다 (실제 산업 평균·시장가격 아님).
"""
import csv
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from src.config.settings import ROOT_DIR
from src.schemas import ProductionContext

REFERENCE_DIR = ROOT_DIR / "data" / "reference"
DEFAULT_SCENARIO = "S15"


def _read_csv(path: Path) -> dict[str, dict[str, str]]:
    with open(path, encoding="utf-8-sig") as f:
        return {row["Scenario_ID"]: row for row in csv.DictReader(f)}


@lru_cache
def load_scenarios(reference_dir: Path = REFERENCE_DIR) -> dict[str, ProductionContext]:
    economic = _read_csv(reference_dir / "economic_context_sim.csv")
    production = _read_csv(reference_dir / "production_context_sim.csv")
    scenarios = {}
    for sid, e in economic.items():
        p = production[sid]
        scenarios[sid] = ProductionContext(
            scenario_id=sid,
            tool_price=float(e["Tool_Price_KRW"]),
            change_time_min=float(e["Tool_Change_Time_min"]),
            downtime_cost_per_min=float(e["Downtime_Cost_per_min_KRW"]),
            part_value=float(e["Part_Value_KRW"]),
            tool_stock=int(e["Spare_Tool_Stock"]),
            remaining_parts=int(p["Remaining_Parts"]),
            process_progress_pct=float(p["Process_Progress_pct"]),
            due_slack_min=float(p["Due_Slack_min"]),
            production_priority=p["Production_Priority"],
            inspection_available=p["Inspection_Available"].strip().lower() == "yes",
        )
    return scenarios


def get_scenario(scenario_id: str = DEFAULT_SCENARIO) -> ProductionContext:
    return load_scenarios()[scenario_id]


def advance(ctx: ProductionContext, parts_done: int = 1) -> ProductionContext:
    """부품을 가공한 만큼 남은 수량과 진행률을 갱신한다."""
    remaining = max(0, ctx.remaining_parts - parts_done)
    total = ctx.remaining_parts / max(1e-9, 1 - ctx.process_progress_pct / 100)
    return replace(
        ctx,
        remaining_parts=remaining,
        process_progress_pct=min(100.0, 100 * (1 - remaining / total)) if total > 0 else 100.0,
    )
