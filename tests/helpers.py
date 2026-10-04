from dataclasses import replace

from src.agents.economics_agent import EconomicsAgent
from src.agents.master_agent import MasterAgent
from src.agents.quality_agent import QualityAgent
from src.schemas import EdgeWear, ToolState, WearReport
from src.simulation.production_sim import get_scenario


def make_wear(
    vb: list[float],
    uncertainty: float = 0.03,
    increments: list[float] | None = None,
    signal_quality: float = 1.0,
    cycle: int = 1,
    measured: bool = False,
) -> WearReport:
    increments = increments or [0.0] * len(vb)
    return WearReport(
        tool_id="T01",
        cycle=cycle,
        edges=[
            EdgeWear(i + 1, v, uncertainty, increment_mm=inc, raw_vb_mm=v, measured=measured)
            for i, (v, inc) in enumerate(zip(vb, increments))
        ],
        signal_quality=signal_quality,
    )


def scenario(scenario_id: str = "S15", **overrides):
    return replace(get_scenario(scenario_id), **overrides)


def decide(wear, ctx=None, state=None):
    ctx = ctx or scenario()
    quality = QualityAgent().analyze(wear, ctx.tool_purpose)
    economics = EconomicsAgent().analyze(quality, ctx, wear)
    return MasterAgent().analyze(wear, quality, economics, state or ToolState("T01"))
