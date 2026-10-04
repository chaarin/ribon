from src.schemas import EdgeWear, WearReport


def make_wear(vb: list[float], uncertainty: float = 0.03, signal_quality: float = 1.0, cycle: int = 1) -> WearReport:
    return WearReport(
        tool_id="T01",
        cycle=cycle,
        edges=[EdgeWear(i + 1, v, uncertainty, raw_vb_mm=v) for i, v in enumerate(vb)],
        signal_quality=signal_quality,
    )
