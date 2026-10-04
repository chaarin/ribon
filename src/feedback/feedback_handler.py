"""현장 검사 결과를 상태와 마모 보고서에 반영한다."""
from dataclasses import replace

from src.schemas import InspectionResult, ToolState, WearReport

MEASURED_UNCERTAINTY_MM = 0.005  # 실측값의 측정 불확실성


def apply_inspection(inspection: InspectionResult, wear: WearReport, state: ToolState) -> WearReport:
    """실측 VB로 해당 날의 예측값을 덮어쓰고, 예측 오차를 bias로 저장해 이후 예측에 반영한다."""
    edge_state = state.edges[inspection.edge_id - 1]
    edge = wear.edge(inspection.edge_id)

    # 마모 증가량은 실측끼리 비교한다 (실측 - 예측은 마모 속도가 아니라 예측 오차이므로)
    if edge_state.last_measured_cycle is not None and wear.cycle > edge_state.last_measured_cycle:
        increment = (inspection.vb_measured_mm - edge_state.last_measured_vb_mm) / (wear.cycle - edge_state.last_measured_cycle)
    else:
        increment = edge.increment_mm

    edge_state.bias_mm = inspection.vb_measured_mm - edge_state.raw_pred_mm
    edge_state.bias_cycle = wear.cycle
    edge_state.vb_mm = inspection.vb_measured_mm
    edge_state.uncertainty_mm = MEASURED_UNCERTAINTY_MM
    edge_state.measured = True
    edge_state.last_measured_vb_mm = inspection.vb_measured_mm
    edge_state.last_measured_cycle = wear.cycle

    edges = list(wear.edges)
    edges[inspection.edge_id - 1] = replace(
        edge,
        vb_max_mm=inspection.vb_measured_mm,
        uncertainty_mm=MEASURED_UNCERTAINTY_MM,
        increment_mm=increment,
        measured=True,
    )
    return replace(wear, edges=edges)
