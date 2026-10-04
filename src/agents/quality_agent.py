"""Quality Agent: 가장 많이 마모된 날 기준으로 표면 품질 위험도를 판단한다. (Track C)"""
from src.agents.base import BaseAgent
from src.models.ra_reference import estimate_ra
from src.schemas import QualityReport, RiskLevel, WearReport


class QualityAgent(BaseAgent):
    name = "quality"

    def analyze(self, wear: WearReport) -> QualityReport:
        # 표면 품질은 평균이 아니라 가장 나쁜 날이 결정한다
        basis = wear.edge(wear.worst_edge)
        ra = estimate_ra(basis.vb_max_mm)
        limits = self.thresholds["quality"]["ra_limits_um"]
        if ra >= limits["high"]:
            level = RiskLevel.HIGH
        elif ra >= limits["medium"]:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return QualityReport(
            risk_level=level,
            ra_estimated_um=ra,
            basis_edge=basis.edge_id,
            basis_vb_mm=basis.vb_max_mm,
            reasons=[
                f"최대 마모 Edge {basis.edge_id} (VBmax {basis.vb_max_mm:.3f} mm) 기준 추정 Ra {ra:.2f} µm → {level.value}"
            ],
        )
