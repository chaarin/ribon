"""Quality Agent: 가장 많이 마모된 날, 편마모, 급속 마모로 표면 품질 위험도를 판단한다. (Track C)

1. 최대 VBmax를 공구 용도별 구간으로 나눠 기본 등급을 정한다
   (정삭: 0.2 mm 미만 LOW / 0.3 mm 미만 MEDIUM / 그 이상 HIGH, 황삭: 0.25 / 0.3 mm)
2. MEDIUM 이상에서 편마모 또는 급속 마모(검사 실측끼리 비교)가 있으면 한 단계 올린다
   (LOW에서는 등급을 올리지 않고 관찰 대상으로만 표시한다. 마모가 작은 단계에서 등급을 올리면
    공구를 지나치게 일찍 교체하게 되므로, 확인은 Master Agent의 검사 규칙이 맡는다)
3. 논문 참조 데이터에서 VB가 비슷한 건식 실험의 Ra 범위를 근거로 함께 제시한다 (등급 계산에는 쓰지 않음)
"""
from src.agents.base import BaseAgent
from src.models.quality_reference import SOURCE, reference_ra_range, similar_runs
from src.schemas import QualityReport, RiskLevel, WearReport

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


class QualityAgent(BaseAgent):
    name = "quality"

    def analyze(self, wear: WearReport, tool_purpose: str = "finishing") -> QualityReport:
        th = self.thresholds["quality"]
        bands = self.thresholds["tool_purpose"][tool_purpose]
        label = bands["label"]
        # 표면 품질은 평균이 아니라 가장 나쁜 날이 결정한다
        basis = wear.edge(wear.worst_edge)
        vb = basis.vb_max_mm

        if vb >= bands["vb_high_mm"]:
            level_idx = 2
            drivers = [f"최대 VBmax {vb:.3f} mm ≥ {bands['vb_high_mm']} mm (ISO 8688-2 공구수명 기준)"]
        elif vb >= bands["vb_medium_mm"]:
            level_idx = 1
            source = "표면 결함 증가 구간, Li et al. 2018" if tool_purpose == "finishing" else "수명 기준 근접 구간"
            drivers = [f"최대 VBmax {vb:.3f} mm ≥ {bands['vb_medium_mm']} mm ({label} 주의 구간: {source})"]
        else:
            level_idx = 0
            drivers = [f"최대 VBmax {vb:.3f} mm < {bands['vb_medium_mm']} mm ({label} 주의 구간 전)"]

        escalations = []
        if wear.uneven_flag:
            escalations.append(f"편마모 (Edge {basis.edge_id}, 날 간 차이 {wear.wear_difference_mm:.3f} mm)")
        # 급속 마모는 실측끼리 비교한 증가량으로만 판단한다. 센서 예측끼리의 차이는 모델 오차(±0.08 mm)가 기준(0.02 mm)보다 커서 노이즈다
        measured = [e for e in wear.edges if e.measured]
        fastest = max(measured, key=lambda e: e.increment_mm) if measured else None
        if fastest is not None and fastest.increment_mm >= th["rapid_increment_mm"]:
            escalations.append(f"급속 마모 (Edge {fastest.edge_id}, 실측 기준 Cycle당 +{fastest.increment_mm:.3f} mm)")
        if escalations and level_idx >= 1:
            level_idx = min(level_idx + 1, 2)
            drivers.append(f"{' / '.join(escalations)} → 한 단계 상향")
        elif escalations:
            drivers.append(f"{' / '.join(escalations)} → 관찰 필요")
        level = LEVELS[level_idx]

        ra_range = reference_ra_range(vb, th["reference_vb_window_mm"])
        runs = similar_runs(vb, th["reference_vb_window_mm"])
        reasons = [f"품질 위험 {level.value} ({label} 공구): {'; '.join(drivers)}"]
        if runs:
            ra_text = f"{ra_range[0]:.2f}~{ra_range[1]:.2f}" if len(runs) > 1 else f"{ra_range[0]:.2f}"
            reasons.append(
                f"참고: {SOURCE}의 건식 가공 중 VB {vb:.2f}±{th['reference_vb_window_mm']} mm인 실험 {len(runs)}개의 Ra {ra_text} µm (가공조건에 따라 다름)"
            )

        return QualityReport(
            risk_level=level,
            basis_edge=basis.edge_id,
            basis_vb_mm=vb,
            caution_vb_mm=bands["vb_medium_mm"],
            tool_purpose=tool_purpose,
            drivers=drivers,
            reference_ra_range_um=ra_range,
            reasons=reasons,
        )
