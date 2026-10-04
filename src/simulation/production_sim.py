"""MVP용 생산 시나리오와 시연 프리셋. (Track D)

- 시나리오 S01~S24: data/reference/의 Economic_Context_Sim과 Production_Context_Sim을 Scenario_ID로 합친 팀 합성값
- 시연 프리셋 5개: 시나리오 하나를 바탕으로 공구 용도·납기 등을 바꿔, Agent마다 다른 역할을 보여주도록 만든 상황
모두 실제 기업 데이터가 아니며, 발표 시 'MVP 시뮬레이션 입력'으로 표기한다.
"""
import csv
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from src.config.settings import ROOT_DIR, load_thresholds
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
            name=sid,
        )
    return scenarios


def get_scenario(scenario_id: str = DEFAULT_SCENARIO) -> ProductionContext:
    return load_scenarios()[scenario_id]


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    description: str
    base_scenario: str
    overrides: dict = field(default_factory=dict)

    def context(self) -> ProductionContext:
        overrides = {"process_progress_pct": PRESET_START_PROGRESS_PCT, **self.overrides}
        return replace(get_scenario(self.base_scenario), name=self.name, **overrides)


# 프리셋끼리 비교할 수 있게 모두 같은 윙 리브 위치에서 시작한다 (MVP 가정).
# 이 위치면 실제 마모가 주의 구간에 들어오는 Cycle 13 무렵이 윙 리브 초반이라, 지금 교체할지 윙 리브를 마치고 교체할지가 갈린다
PRESET_START_PROGRESS_PCT = 90.0


PRESETS: dict[str, Preset] = {
    p.id: p
    for p in (
        Preset("finishing", "정삭 공구", "윙 리브 마무리 가공. 표면이 곧 품질이라 0.2 mm부터 주의하고, 불량이 나면 윙 리브 전체를 다시 가공한다.",
               "S15", {"tool_purpose": "finishing"}),
        Preset("roughing", "황삭 공구", "윙 리브 거친 가공. 이후 정삭에서 표면을 다시 깎으므로 0.3 mm 수명 기준 가까이까지 쓴다.",
               "S15", {"tool_purpose": "roughing"}),
        Preset("no_stock", "여분 공구 없음", "정삭 공구인데 교체할 공구가 없다. 지금 멈추기보다 윙 리브를 마치는 동안 공구를 확보한다.",
               "S10", {"tool_purpose": "finishing"}),
        Preset("due_tight", "납기 임박", "정삭 공구, 납기 여유 5분·우선순위 높음. 지금 교체하면 납기를 넘긴다.",
               "S15", {"tool_purpose": "finishing", "due_slack_min": 5.0, "production_priority": "High"}),
        Preset("no_inspection", "검사 장비 없는 라인", "정삭 공구인데 현장 검사를 할 수 없다. 센서 예측만으로 판단한다.",
               "S21", {"tool_purpose": "finishing"}),
    )
}
DEFAULT_PRESET = "finishing"


def advance_cycle(ctx: ProductionContext, cycles_per_rib: int | None = None) -> ProductionContext:
    """한 Cycle 가공한 뒤의 생산 상황. 윙 리브가 끝나면 다음 윙 리브로 넘어간다 (남은 수량은 최소 1개 유지)."""
    cycles_per_rib = cycles_per_rib or load_thresholds()["production"]["cycles_per_rib"]
    progress = ctx.process_progress_pct + 100 / cycles_per_rib
    remaining = ctx.remaining_parts
    if progress > 100 + 1e-6:  # 이전 Cycle에서 윙 리브를 끝냈다 → 다음 윙 리브의 첫 Cycle
        progress = 100 / cycles_per_rib
        remaining = max(1, remaining - 1)
    return replace(ctx, process_progress_pct=min(progress, 100.0), remaining_parts=remaining)


def start_context(ctx: ProductionContext, cycles_per_rib: int | None = None) -> ProductionContext:
    """재생 시작 전 상태. 시나리오의 진행률을 가장 가까운 Cycle 경계로 맞춘다."""
    cycles_per_rib = cycles_per_rib or load_thresholds()["production"]["cycles_per_rib"]
    step = 100 / cycles_per_rib
    return replace(ctx, process_progress_pct=round(ctx.process_progress_pct / step) * step)
