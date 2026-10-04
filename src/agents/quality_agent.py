"""Quality Agent: 가장 많이 마모된 날, 편마모, 급속 마모로 표면 품질 위험도를 판단한다. (Track C)

1. 최대 VBmax 구간으로 기본 등급을 정한다 (0.2 mm 미만 LOW / 0.3 mm 미만 MEDIUM / 그 이상 HIGH)
2. MEDIUM 이상에서 편마모 또는 급속 마모가 있으면 한 단계 올린다
   (LOW에서는 등급을 올리지 않고 관찰 대상으로만 표시한다. 마모가 작은 단계에서 등급을 올리면
    고가 부품 시나리오에서 공구를 지나치게 일찍 교체하게 되므로, 확인은 Master Agent의 검사 규칙이 맡는다)
3. 논문 참조 데이터에서 VB가 비슷한 실험의 Ra 범위를 근거로 함께 제시한다 (등급 계산에는 쓰지 않음)
"""
from src.agents.base import BaseAgent
from src.models.quality_reference import SOURCE, reference_ra_range, similar_runs
from src.schemas import QualityReport, RiskLevel, WearReport

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


class QualityAgent(BaseAgent):
    name = "quality"

    def analyze(self, wear: WearReport) -> QualityReport:
        th = self.thresholds["quality"]
        # 표면 품질은 평균이 아니라 가장 나쁜 날이 결정한다
        basis = wear.edge(wear.worst_edge)
        vb = basis.vb_max_mm

        if vb >= th["vb_high_mm"]:
            level_idx = 2
            drivers = [f"최대 VBmax {vb:.3f} mm ≥ {th['vb_high_mm']} mm (ISO 8688-2 공구수명 기준)"]
        elif vb >= th["vb_medium_mm"]:
            level_idx = 1
            drivers = [f"최대 VBmax {vb:.3f} mm ≥ {th['vb_medium_mm']} mm (표면 결함 증가 구간, Li et al. 2018)"]
        else:
            level_idx = 0
            drivers = [f"최대 VBmax {vb:.3f} mm < {th['vb_medium_mm']} mm"]

        escalations = []
        if wear.uneven_flag:
            escalations.append(f"편마모 (Edge {basis.edge_id}, 날 간 차이 {wear.wear_difference_mm:.3f} mm)")
        fastest = wear.edge(wear.fastest_edge)
        if fastest.increment_mm >= th["rapid_increment_mm"]:
            escalations.append(f"급속 마모 (Edge {fastest.edge_id}, 직전 Cycle 대비 +{fastest.increment_mm:.3f} mm)")
        if escalations and level_idx >= 1:
            level_idx = min(level_idx + 1, 2)
            drivers.append(f"{' / '.join(escalations)} → 한 단계 상향")
        elif escalations:
            drivers.append(f"{' / '.join(escalations)} → 관찰 필요")
        level = LEVELS[level_idx]

        ra_range = reference_ra_range(vb, th["reference_vb_window_mm"])
        reasons = [f"품질 위험 {level.value}: {'; '.join(drivers)}"]
        runs = similar_runs(vb, th["reference_vb_window_mm"])
        if runs:
            ra_text = f"{ra_range[0]:.2f}~{ra_range[1]:.2f}" if len(runs) > 1 else f"{ra_range[0]:.2f}"
            reasons.append(
                f"참고: {SOURCE}에서 VB {vb:.2f}±{th['reference_vb_window_mm']} mm인 실험 {len(runs)}개의 Ra {ra_text} µm (가공조건에 따라 다름)"
            )

        return QualityReport(
            risk_level=level,
            basis_edge=basis.edge_id,
            basis_vb_mm=vb,
            drivers=drivers,
            reference_ra_range_um=ra_range,
            reasons=reasons,
        )
