"""데모: 합성 데이터로 공구 1개의 전체 수명 동안 의사결정 흐름을 실행한다.

실행: python -m src.main
"""
from src.config.settings import OUTPUT_DIR
from src.data.synthetic import generate_tool_run
from src.memory.history_store import HistoryStore
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, Decision, InspectionResult
from src.simulation.production_sim import advance, default_context


def print_decision(decision: Decision, prefix: str = "") -> None:
    target = f" (Edge {decision.target_edge})" if decision.target_edge else ""
    print(f"{prefix}[Cycle {decision.cycle:2d}] {decision.action.value}{target}  신뢰도 {decision.confidence:.2f}")
    print(f"{prefix}    → {decision.reasons[0]}")


def run_demo(n_cycles: int = 25) -> None:
    history_path = OUTPUT_DIR / "history.jsonl"
    history_path.unlink(missing_ok=True)
    pipeline = MaintenancePipeline(history=HistoryStore(history_path))
    ctx = default_context()

    for window in generate_tool_run("T01", n_cycles):
        decision = pipeline.run_cycle(window, ctx)
        print_decision(decision)

        while decision.action in (Action.INSPECT_EDGE, Action.REMEASURE):
            if decision.action == Action.INSPECT_EDGE:
                # 합성 데이터의 실제 마모값을 현장 실측값으로 사용
                measured = window.vb_label_mm[decision.target_edge - 1]
                print(f"    ⤷ 검사 결과: Edge {decision.target_edge} 실측 VBmax {measured:.3f} mm → 재판단")
                decision = pipeline.apply_feedback(
                    InspectionResult(window.tool_id, decision.target_edge, measured)
                )
            else:
                print("    ⤷ 센서 재측정 → 재판단")
                decision = pipeline.run_cycle(window, ctx)
            print_decision(decision, prefix="    ")

        if decision.action in (Action.REPLACE_NOW, Action.REPLACE_AFTER_JOB):
            pipeline.confirm_replacement(window.tool_id)
            print(f"\n공구 교체 완료. 판단 이력: {history_path}")
            print("\n최종 판단 근거:")
            for reason in decision.reasons:
                print(f"  - {reason}")
            break

        ctx = advance(ctx)


if __name__ == "__main__":
    run_demo()
