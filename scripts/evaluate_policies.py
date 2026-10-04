"""Step 3 평가: 실제 QIT-CEMC 68 Cycle에서 교체 판단 방식 비교 (손실 = 가공 시간).

실행: python -m scripts.evaluate_policies
결과: docs/step3_results.md
"""
import numpy as np
import pandas as pd

from src.config.settings import ROOT_DIR, load_thresholds
from src.evaluation.policies import compare_policies
from src.evaluation.replay import out_of_sample_model, run_system
from src.models.tool_wear_model import load_features
from src.simulation.production_sim import PRESETS, load_scenarios

REPORT_PATH = ROOT_DIR / "docs" / "step3_results.md"
SCALES = (0.5, 1.0, 2.0)


def table(outcomes) -> list[str]:
    lines = [
        "| 방식 | 교체 Cycle | 검사 | 한계 초과 가공 | 윙 리브당 손실(분) | 그중 불량 | 윙 리브당 공구 |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        lines.append(
            f"| {o.name} | {o.replace_cycle}{'' if o.replaced else ' (교체 안 함)'} | {o.n_inspections} | {o.over_limit_cycles} | "
            f"{o.loss_min_per_rib:.1f} | {o.defect_loss_min_per_rib:.1f} | {o.tools_per_rib:.2f}개 |"
        )
    return lines


def main() -> None:
    df = load_features()
    th = load_thresholds()
    prod = th["production"]
    model = out_of_sample_model(df)
    pred = np.array([model.predictions[c] for c in df["cycle"]])

    lines = [
        "# Step 3 결과: 실제 데이터로 교체 판단 방식 비교",
        "",
        "자동 생성: `python -m scripts.evaluate_policies` / 데이터: QIT-CEMC 68 Cycle (공구 1개) / 생산 조건: 시연 프리셋 5개, 시나리오 S01~S24 (MVP 합성값)",
        "",
        "## 평가 방법",
        "",
        "- **센서 예측:** 각 Cycle을 그 Cycle 앞뒤 5개를 학습에서 뺀 모델로 예측 (블록 교차검증). 답을 본 예측이 섞이지 않게 함",
        "- **검사:** 시스템이 검사를 지시하면 그 Cycle의 실제 Edge 1~4 VBmax를 현장 실측값으로 넣음",
        f"- **손실 = 가공 시간(분):** 윙 리브 1개 = {prod['cycles_per_rib']} Cycle, Cycle당 {prod['cycle_time_min']}분 (QIT-CEMC 실측), "
        f"검사 1회 {prod['inspection_time_min']}분, 교체 시간은 시나리오 값",
        "  - 불량 1건 손실: 정삭은 윙 리브 전체 재가공(85분), 황삭은 한 Cycle 재가공(8.5분)",
        "  - 불량 확률: 실제 최대 날 VB 기준 위험 등급별 LOW 1% / MEDIUM 5% / HIGH 30% (MVP 가정)",
        "  - 공구가 같은 수명을 반복한다고 보고 윙 리브 1개당 손실과 공구 사용량으로 환산",
        "- **비교 기준:** '매 Cycle 검사' 방식은 교체할 때까지 매 Cycle 4날을 실측한다 (검사 시간 포함)",
        "",
    ]

    # 1. 프리셋별 상세
    lines += ["## 1. 시연 프리셋별 결과 (불량 확률 기본 가정)", ""]
    for preset in PRESETS.values():
        ctx = preset.context()
        r = run_system(df, ctx, model=model)
        last = r.decisions[-1]
        lines += [
            f"### {preset.name}",
            "",
            f"{preset.description}",
            "",
            f"- 시스템 판단: Cycle {r.replace_cycle} **{last.action.value}**, 검사 Cycle {r.inspection_cycles}",
            f"- 이유: {last.reasons[0]}",
            "",
            *table(compare_policies(df, ctx, r.replace_cycle, len(r.inspection_cycles), pred, th)),
            "",
        ]

    # 2. 민감도 분석
    lines += [
        "## 2. 불량 확률 가정에 대한 민감도",
        "",
        "불량 확률(LOW 1% / MEDIUM 5% / HIGH 30%)은 근거가 없는 가정이라, 절반·2배로 바꿔 결론이 유지되는지 본다.",
        "",
        "| 프리셋 | 불량 확률 | 시스템 | 센서 예측 0.3 (검사 없음) | 최대 날 0.3 (매 Cycle 검사) | 평균 0.3 (매 Cycle 검사) | 이상적 (매 Cycle 검사) |",
        "|---|---|---|---|---|---|---|",
    ]
    for pid in ("finishing", "roughing"):
        ctx = PRESETS[pid].context()
        r = run_system(df, ctx, model=model)
        for scale in SCALES:
            o = {x.name: x.loss_min_per_rib for x in compare_policies(df, ctx, r.replace_cycle, len(r.inspection_cycles), pred, th, scale)}
            sys_name = next(n for n in o if n.startswith("Multi-Agent"))
            best = min(o, key=o.get)
            cells = [o[sys_name], o["센서 예측 VB ≥ 0.3 (검사 없음)"], o["최대 날 VB ≥ 0.3 (매 Cycle 검사)"],
                     o["평균 VB ≥ 0.3 (매 Cycle 검사)"], o["최대 날 VB ≥ 주의 기준 (매 Cycle 검사, 이상적)"]]
            names = [sys_name, "센서 예측 VB ≥ 0.3 (검사 없음)", "최대 날 VB ≥ 0.3 (매 Cycle 검사)",
                     "평균 VB ≥ 0.3 (매 Cycle 검사)", "최대 날 VB ≥ 주의 기준 (매 Cycle 검사, 이상적)"]
            fmt = [f"**{v:.1f}**" if n == best else f"{v:.1f}" for v, n in zip(cells, names)]
            lines.append(f"| {PRESETS[pid].name} | ×{scale} | " + " | ".join(fmt) + " |")
    lines += ["", "(윙 리브 1개당 손실 시간, 분. 굵은 글씨가 가장 작은 값)", ""]

    # 3. 팀 시나리오 24개 (정삭 공구 가정)
    rows = []
    for sid, ctx in load_scenarios().items():
        r = run_system(df, ctx, model=model)
        for o in compare_policies(df, ctx, r.replace_cycle, len(r.inspection_cycles), pred, th):
            rows.append({"name": o.name, "replace": o.replace_cycle, "insp": o.n_inspections, "over": o.over_limit_cycles,
                         "loss": o.loss_min_per_rib, "tools": o.tools_per_rib})
    res = pd.DataFrame(rows)
    summary = res.groupby("name", sort=False).agg(replace=("replace", "median"), insp=("insp", "mean"),
                                                  over=("over", "mean"), loss=("loss", "mean"), tools=("tools", "mean"))
    lines += [
        "## 3. 팀 시나리오 S01~S24 평균 (정삭 공구 가정)",
        "",
        "| 방식 | 교체 Cycle (중앙값) | 검사 | 한계 초과 가공 | 윙 리브당 손실(분) | 윙 리브당 공구 |",
        "|---|---|---|---|---|---|",
        *[f"| {n} | {r['replace']:.0f} | {r['insp']:.1f} | {r['over']:.1f} | {r['loss']:.1f} | {r['tools']:.2f}개 |" for n, r in summary.iterrows()],
        "",
        "## 해석",
        "",
        "- **평균 기준은 가장 많이 닳은 날을 놓친다.** 교체가 Cycle 53으로 늦고 한계(0.3 mm)를 넘은 상태로 10 Cycle을 가공해, 불량 손실이 가장 크다.",
        "- **매 Cycle 검사하는 방식들은 검사 시간이 손실의 대부분**이다. 날별 상태를 정확히 알아도 매번 멈추는 비용이 크다.",
        "- **Multi-Agent 시스템은 필요할 때만(2~3회) 검사**해 날별 상태를 확인하고, 공구 용도·재고·납기에 따라 교체 시점과 방식을 바꾼다.",
        "  매 Cycle 검사 방식들보다 손실이 작고 한계 초과 가공이 없다.",
        "- **센서 예측만으로 0.3 mm에서 교체하는 단순한 방식과는 우열이 가정에 따라 바뀐다.** 불량 확률이 기본 가정 이하면 검사 시간과",
        "  더 이른 교체 비용 때문에 단순 방식의 손실이 작고, 불량 확률이 높을수록(×2) 검사로 위험을 일찍 잡는 시스템이 유리해진다.",
        "  즉 **검사의 가치는 불량이 비쌀수록 커진다.** 이 판단은 실제 현장의 불량률 데이터가 있어야 확정할 수 있다.",
        "",
        "## 한계",
        "",
        "- 공구 1개의 기록을 반복한다고 가정한 평가다. 다른 공구에서의 일반화는 검증하지 못했다.",
        "- 불량 확률, 검사 시간, 윙 리브당 Cycle 수는 MVP 가정이다. 손실 수치는 '시뮬레이션 기준'으로만 말할 수 있다.",
        "- Cycle 1의 센서 예측은 학습 범위 밖이라 크게 빗나가(예측 0.17 mm, 실제 0.05 mm) 검사가 한 번 더 일어난다.",
        "  여러 공구로 학습한 실제 모델이라면 이 검사는 줄어든다.",
        "- 재검사 간격(0.03 mm)은 이 공구 하나의 재생 결과를 보고 골랐다. 다른 공구에서는 성능이 더 낮을 수 있다.",
        "- 공구 사용량(윙 리브당 공구 개수)은 손실 시간에 넣지 않고 따로 보여준다. 공구값을 시간으로 바꿀 근거가 없기 때문이다.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
