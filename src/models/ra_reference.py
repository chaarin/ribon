"""VB–Ra 참조 데이터. (Track C)

TODO(Track C): 아래 값은 파이프라인 동작 확인용 임시값이다.
Ti-6Al-4V 밀링의 플랭크 마모–표면조도 관계를 다룬 논문 데이터로 교체하고 SOURCE에 출처를 적는다.
"""
import numpy as np

SOURCE = "PLACEHOLDER - 논문 데이터로 교체 필요"

# (VB mm, Ra µm)
REFERENCE_POINTS = [
    (0.0, 0.4),
    (0.1, 0.6),
    (0.2, 0.8),
    (0.3, 1.2),
    (0.4, 1.8),
]


def estimate_ra(vb_mm: float) -> float:
    """참조 점 사이는 선형 보간하고, 범위를 넘으면 마지막 구간 기울기로 외삽한다."""
    vb = np.array([p[0] for p in REFERENCE_POINTS])
    ra = np.array([p[1] for p in REFERENCE_POINTS])
    if vb_mm > vb[-1]:
        slope = (ra[-1] - ra[-2]) / (vb[-1] - vb[-2])
        return float(ra[-1] + slope * (vb_mm - vb[-1]))
    return float(np.interp(vb_mm, vb, ra))
