"""시연용 웹 서버. 실제 QIT-CEMC 68 Cycle을 한 Cycle씩 Multi-Agent 시스템에 재생한다.

실행: python -m src.web  →  http://localhost:8000
"""
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from enum import Enum
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agents.wear_agent import WearAgent
from src.config.settings import N_EDGES, load_thresholds
from src.evaluation.policies import compare_policies
from src.evaluation.replay import TOOL_ID, out_of_sample_model, qit_windows, run_system
from src.memory.history_store import HistoryStore
from src.models.tool_wear_model import FORCE_CHANNELS, load_features, worst_edge_vb
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, InspectionResult, ProductionContext
from src.simulation.production_sim import DEFAULT_PRESET, PRESETS, advance_cycle, start_context

STATIC_DIR = Path(__file__).with_name("static")
SENSOR_FEATURES = [f"{ch}_std" for ch in FORCE_CHANNELS]  # 화면에 보여줄 센서 지표: 힘/토크의 출렁임

app = FastAPI(title="Ti-6Al-4V 공구 유지보수 Multi-Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 모델과 데이터는 한 번만 준비한다 (68 Cycle 블록 교차검증 예측)
DF = load_features()
MODEL = out_of_sample_model(DF)
WINDOWS = qit_windows(DF)
SENSOR_PRED = np.array([MODEL.predictions[c] for c in DF["cycle"]])


def to_json(obj):
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return to_json(asdict(obj))
    if isinstance(obj, dict):
        return {k: to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


@dataclass
class Session:
    preset_id: str
    start_ctx: ProductionContext  # 시작 조건 (비교 평가용)
    ctx: ProductionContext  # 지금 Cycle의 생산 상황 (윙 리브 진행에 따라 바뀜)
    pipeline: MaintenancePipeline
    index: int = 0  # 다음에 재생할 Cycle 위치
    pending: dict | None = None  # 검사·재측정 대기
    finished: bool = False
    replace_cycle: int | None = None
    inspection_cycles: list[int] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    @property
    def window(self):
        return WINDOWS[self.index - 1]

    def snapshot(self, kind: str) -> dict:
        """화면에 보낼 현재 Cycle 상태."""
        reports = self.pipeline.last_reports[TOOL_ID]
        decision = reports["decision"]
        window = self.window
        record = {
            "kind": kind,  # "cycle" / "inspection" / "remeasure"
            "cycle": window.cycle,
            "cut_time_min": window.cumulative_cut_time_min,
            "sensor": {k: window.features.get(k) for k in SENSOR_FEATURES},
            "context": to_json(self.ctx),
            "wear": to_json(reports["wear"]) | {
                "vb_max": reports["wear"].vb_max,
                "vb_mean": reports["wear"].vb_mean,
                "worst_edge": reports["wear"].worst_edge,
                "uneven_index": reports["wear"].uneven_index,
                "uneven_flag": reports["wear"].uneven_flag,
                "wear_difference_mm": reports["wear"].wear_difference_mm,
                "mean_uncertainty": reports["wear"].mean_uncertainty,
            },
            "quality": to_json(reports["quality"]),
            "economics": to_json(reports["economics"]),
            "decision": to_json(decision),
        }
        self.pending = None
        if decision.action == Action.INSPECT_EDGE:
            edges = [decision.target_edge] if decision.target_edge else list(range(1, N_EDGES + 1))
            self.pending = {
                "type": "inspection",
                "edges": edges,
                # 시연에서는 QIT-CEMC의 실제 측정값을 현장 실측값으로 미리 채운다 (발표자가 바꿀 수 있음)
                "suggested": {str(e): window.vb_label_mm[e - 1] for e in edges},
            }
        elif decision.action == Action.REMEASURE:
            self.pending = {"type": "remeasure"}
        elif decision.action in (Action.REPLACE_NOW, Action.REPLACE_AFTER_JOB):
            self.finished, self.replace_cycle = True, window.cycle
        if self.index >= len(WINDOWS) and self.pending is None:
            self.finished = True
        record["pending"] = self.pending
        record["finished"] = self.finished
        self.timeline.append(record)
        return record


SESSIONS: dict[str, Session] = {}


class ContextOverrides(BaseModel):
    tool_purpose: str | None = None
    change_time_min: float | None = None
    tool_stock: int | None = None
    due_slack_min: float | None = None
    production_priority: str | None = None
    inspection_available: bool | None = None
    process_progress_pct: float | None = None
    remaining_parts: int | None = None


class SessionRequest(BaseModel):
    preset_id: str = DEFAULT_PRESET
    overrides: ContextOverrides | None = None


class InspectionRequest(BaseModel):
    values: dict[str, float]  # 날 번호(문자열) → 실측 VBmax (mm)


def get_session(session_id: str) -> Session:
    if session_id not in SESSIONS:
        raise HTTPException(404, "세션이 없습니다. 처음부터 다시 시작하세요.")
    return SESSIONS[session_id]


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/presets")
def presets():
    th = load_thresholds()
    return {
        "presets": [
            {"id": p.id, "name": p.name, "description": p.description, "base_scenario": p.base_scenario, "context": to_json(p.context())}
            for p in PRESETS.values()
        ],
        "default": DEFAULT_PRESET,
        "tool_purposes": {k: {"label": v["label"], "caution_vb_mm": v["vb_medium_mm"]} for k, v in th["tool_purpose"].items()},
        "vb_limit_mm": th["wear"]["vb_limit_mm"],
        "production": th["production"],
        "total_cycles": len(WINDOWS),
    }


@app.post("/api/sessions")
def create_session(req: SessionRequest):
    if req.preset_id not in PRESETS:
        raise HTTPException(400, f"알 수 없는 프리셋: {req.preset_id}")
    ctx = PRESETS[req.preset_id].context()
    if req.overrides:
        changes = {k: v for k, v in req.overrides.model_dump().items() if v is not None}
        if changes.get("tool_purpose") not in (None, *load_thresholds()["tool_purpose"]):
            raise HTTPException(400, "tool_purpose는 finishing 또는 roughing")
        ctx = replace(ctx, **changes)
    pipeline = MaintenancePipeline(wear_agent=WearAgent(model=MODEL), history=HistoryStore())
    session_id = uuid.uuid4().hex[:12]
    ctx = start_context(ctx)
    SESSIONS[session_id] = Session(preset_id=req.preset_id, start_ctx=ctx, ctx=ctx, pipeline=pipeline)
    return {"session_id": session_id, "context": to_json(SESSIONS[session_id].ctx), "total_cycles": len(WINDOWS)}


@app.post("/api/sessions/{session_id}/step")
def step(session_id: str):
    s = get_session(session_id)
    if s.finished:
        raise HTTPException(409, "이미 끝난 세션입니다.")
    if s.pending:
        raise HTTPException(409, "검사 결과 입력 또는 재측정이 먼저 필요합니다.")
    s.index += 1
    s.ctx = advance_cycle(s.ctx)
    s.pipeline.run_cycle(s.window, s.ctx)
    return s.snapshot("cycle")


@app.post("/api/sessions/{session_id}/inspection")
def inspection(session_id: str, req: InspectionRequest):
    s = get_session(session_id)
    if not s.pending or s.pending["type"] != "inspection":
        raise HTTPException(409, "지금은 검사 단계가 아닙니다.")
    missing = [e for e in s.pending["edges"] if str(e) not in req.values]
    if missing:
        raise HTTPException(400, f"검사 값이 빠진 날: {missing}")
    results = [InspectionResult(TOOL_ID, e, float(req.values[str(e)])) for e in s.pending["edges"]]
    s.inspection_cycles.append(s.window.cycle)
    s.pipeline.apply_feedback(results)
    return s.snapshot("inspection")


@app.post("/api/sessions/{session_id}/remeasure")
def remeasure(session_id: str):
    s = get_session(session_id)
    if not s.pending or s.pending["type"] != "remeasure":
        raise HTTPException(409, "지금은 재측정 단계가 아닙니다.")
    s.pipeline.run_cycle(s.window, s.ctx)
    return s.snapshot("remeasure")


@app.get("/api/sessions/{session_id}/comparison")
def comparison(session_id: str, defect_scale: float = 1.0):
    """같은 생산 조건에서 판단 방식 비교. 시스템 결과는 이 세션에서 실제로 진행한 결과를 쓴다 (끝나지 않았으면 자동 재생)."""
    s = get_session(session_id)
    if s.finished:
        replace_cycle, n_insp, source = s.replace_cycle, len(s.inspection_cycles), "session"
    else:
        auto = run_system(DF, s.start_ctx, model=MODEL)
        replace_cycle, n_insp, source = auto.replace_cycle, len(auto.inspection_cycles), "auto"
    outcomes = compare_policies(DF, s.start_ctx, replace_cycle, n_insp, SENSOR_PRED, defect_scale=defect_scale)
    return {"defect_scale": defect_scale, "system_source": source, "outcomes": to_json(outcomes)}


@app.get("/api/truth")
def truth():
    """실제 측정된 마모 (정답). 시연 마지막에 시스템 판단과 겹쳐 보기 위한 것."""
    return {
        "cycles": DF["cycle"].tolist(),
        "worst_vb_mm": worst_edge_vb(DF).tolist(),
        "mean_vb_mm": DF[[f"edge{i}_vbmax_mm" for i in range(1, N_EDGES + 1)]].mean(axis=1).tolist(),
        "sensor_pred_mm": SENSOR_PRED.tolist(),
        "sigma_mm": MODEL.sigma_mm,
    }
