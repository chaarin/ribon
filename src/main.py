"""데모: 공구 1개의 수명 동안 Multi-Agent 의사결정 흐름을 실행한다.

실행:
  python -m src.main --data qit [--scenario S15]        실제 QIT-CEMC 68 Cycle 재생 (검사 결과 = 실제 라벨)
  python -m src.main --data synthetic [--cycles 25]     합성 센서 데이터
"""
import argparse

from src.config.settings import OUTPUT_DIR
from src.data.synthetic import generate_tool_run
from src.memory.history_store import HistoryStore
from src.orchestrator.pipeline import MaintenancePipeline
from src.schemas import Action, Decision, InspectionResult
from src.simulation.production_sim import DEFAULT_SCENARIO, advance, get_scenario


def print_decision(decision: Decision, prefix: str = "") -> None:
    target = f" (Edge {decision.target_edge})" if decision.target_edge else ""
    print(f"{prefix}[Cycle {decision.cycle:2d}] {decision.action.value}{target}  신뢰도 {decision.confidence:.2f}")
    print(f"{prefix}    → {decision.reasons[0]}")


def run_qit_demo(scenario_id: str = DEFAULT_SCENARIO) -> None:
    from src.evaluation.replay import run_system
    from src.models.tool_wear_model import load_features

    ctx = get_scenario(scenario_id)
    print(f"QIT-CEMC 실제 데이터 68 Cycle 재생 / 시나리오 {scenario_id} (MVP 시뮬레이션 입력)")
    print("센서 예측: 각 Cycle을 그 Cycle 앞뒤 5개를 학습에서 뺀 모델로 예측 / 검사 결과: 실제 라벨\n")
    last: list[Decision] = []

    def on_event(kind, payload):
        if kind == "inspection":
            values = ", ".join(f"E{i.edge_id} {i.vb_measured_mm:.3f}" for i in payload)
            print(f"    ⤷ 검사 결과(실측 VBmax mm): {values} → 재판단")
        else:
            prefix = "    " if last and last[-1].cycle == payload.cycle else ""
            if payload.action != Action.CONTINUE or prefix:
                print_decision(payload, prefix=prefix)
            last.append(payload)

    result = run_system(load_features(), ctx, on_event=on_event)
    continued = sum(1 for d in result.decisions if d.action == Action.CONTINUE)
    print(f"\n계속 가공 {continued} Cycle, 검사 {len(result.inspection_cycles)}회 (Cycle {result.inspection_cycles}), "
          f"교체 Cycle {result.replace_cycle}")
    if result.decisions:
        print("\n최종 판단 근거:")
        for reason in result.decisions[-1].reasons:
            print(f"  - {reason}")


def run_demo(scenario_id: str = DEFAULT_SCENARIO, n_cycles: int = 25) -> None:
    history_path = OUTPUT_DIR / "history.jsonl"
    history_path.unlink(missing_ok=True)
    pipeline = MaintenancePipeline(history=HistoryStore(history_path))
    ctx = get_scenario(scenario_id)
    print(f"시나리오 {scenario_id} (MVP 시뮬레이션 입력) / 합성 센서 데이터\n")

    for window in generate_tool_run("T01", n_cycles):
        decision = pipeline.run_cycle(window, ctx)
        print_decision(decision)

        while decision.action in (Action.INSPECT_EDGE, Action.REMEASURE):
            if decision.action == Action.INSPECT_EDGE:
                # 합성 데이터의 실제 마모값을 현장 실측값으로 사용
                measured = window.vb_label_mm[decision.target_edge - 1]
                print(f"    ⤷ 검사 결과: Edge {decision.target_edge} 실측 VBmax {measured:.3f} mm → 재판단")
                decision = pipeline.apply_feedback(InspectionResult(window.tool_id, decision.target_edge, measured))
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--cycles", type=int, default=25)
    parser.add_argument("--data", choices=("qit", "synthetic"), default="qit")
    args = parser.parse_args()
    if args.data == "qit":
        run_qit_demo(args.scenario)
    else:
        run_demo(args.scenario, args.cycles)
