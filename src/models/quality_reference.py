"""논문 기반 VB–Ra 참조 데이터. (Track C)

출처: Nguyen et al. (2024), Ti-6Al-4V 밀링 L27 실험, https://doi.org/10.1142/S0217979224400228
원본: data/reference/Ti6Al4V_MultiAgent_통합데이터.xlsx 의 Quality_Reference_Data 시트

주의: 가공조건·공구·윤활조건이 QIT-CEMC와 다르고, 27개 실험 전체에서 VB와 Ra의 상관이 거의 없다(r≈0.06).
따라서 VB로 Ra를 추정하거나 불량 확률을 학습하는 데 쓰지 않고, 품질 위험 판단의 참고 근거로만 제시한다.
"""
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.config.settings import ROOT_DIR

REFERENCE_PATH = ROOT_DIR / "data" / "reference" / "quality_reference.csv"
SOURCE = "Nguyen et al. (2024), Ti-6Al-4V 밀링 L27 실험"


@dataclass(frozen=True)
class ReferenceRun:
    run: int
    cooling_mode: str
    cutting_speed_m_min: float
    feed_mm_tooth: float
    depth_of_cut_mm: float
    ra_um: float
    vb_mm: float


@lru_cache
def load_reference(path: Path = REFERENCE_PATH) -> tuple[ReferenceRun, ...]:
    with open(path, encoding="utf-8") as f:
        return tuple(
            ReferenceRun(
                run=int(row["Run"]),
                cooling_mode=row["Cooling_Mode"],
                cutting_speed_m_min=float(row["Cutting_Speed_m_min"]),
                feed_mm_tooth=float(row["Feed_mm_tooth"]),
                depth_of_cut_mm=float(row["Depth_of_Cut_mm"]),
                ra_um=float(row["Ra_um"]),
                vb_mm=float(row["Vb_mm"]),
            )
            for row in csv.DictReader(f)
        )


def similar_runs(vb_mm: float, window_mm: float) -> list[ReferenceRun]:
    return [r for r in load_reference() if abs(r.vb_mm - vb_mm) <= window_mm]


def reference_ra_range(vb_mm: float, window_mm: float) -> tuple[float, float] | None:
    """VB가 비슷한 참조 실험들의 Ra 최소~최대. 해당 실험이 없으면 None."""
    runs = similar_runs(vb_mm, window_mm)
    if not runs:
        return None
    return min(r.ra_um for r in runs), max(r.ra_um for r in runs)
