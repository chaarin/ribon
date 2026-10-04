"""MVP용 생산·비용 상황. (Track D)

모든 값은 가정값이다. 현실적인 값과 출처가 확보되면 갱신한다.
"""
from dataclasses import replace

from src.schemas import ProductionContext


def default_context() -> ProductionContext:
    return ProductionContext(
        tool_price=150_000,
        change_time_min=10,
        downtime_cost_per_min=5_000,
        part_value=800_000,
        remaining_parts=30,
        cycle_time_min=2.0,
        tool_stock=3,
        due_hours=8,
        breakage_cost=2_000_000,
    )


SCENARIOS: dict[str, ProductionContext] = {
    "normal": default_context(),
    "urgent_due": replace(default_context(), due_hours=1.1),
    "no_stock": replace(default_context(), tool_stock=0),
}


def advance(ctx: ProductionContext, parts_done: int = 1) -> ProductionContext:
    """부품을 가공한 만큼 남은 생산량과 납기 시간을 줄인다."""
    return replace(
        ctx,
        remaining_parts=max(0, ctx.remaining_parts - parts_done),
        due_hours=max(0.0, ctx.due_hours - parts_done * ctx.cycle_time_min / 60),
    )
