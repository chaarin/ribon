"""현장 검사 결과를 상태와 마모 보고서에 반영한다."""
from dataclasses import replace

from src.schemas import InspectionResult, ToolState, WearReport

MEASURED_UNCERTAINTY_MM = 0.005  # 실측값의 측정 불확실성


def apply_inspection(inspection: InspectionResult, wear: WearReport, state: ToolState) -> WearReport:
    """실측 VB로 해당 날의 예측값을 덮어쓰고, 예측 오차를 bias로 저장해 다음 예측에 반영한다."""
    edge_state = state.edges[inspection.edge_id - 1]
    edge_state.bias_mm = inspection.vb_measured_mm - edge_state.raw_pred_mm
    edge_state.vb_mm = inspection.vb_measured_mm
    edge_state.uncertainty_mm = MEASURED_UNCERTAINTY_MM
    edge_state.measured = True
    edge_state.last_measured_vb_mm = inspection.vb_measured_mm

    edges = list(wear.edges)
    edges[inspection.edge_id - 1] = replace(
        edges[inspection.edge_id - 1],
        vb_max_mm=inspection.vb_measured_mm,
        uncertainty_mm=MEASURED_UNCERTAINTY_MM,
        # 예측 대신 실측값 기준으로 직전 Cycle 대비 증가량을 다시 계산
        increment_mm=edges[inspection.edge_id - 1].increment_mm
        + inspection.vb_measured_mm
        - edges[inspection.edge_id - 1].vb_max_mm,
        measured=True,
    )
    return replace(wear, edges=edges)
