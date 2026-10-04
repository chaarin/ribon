"""Step 3 평가: 실제 QIT-CEMC 68 Cycle에서 교체 판단 방식 비교.

실행: python -m scripts.evaluate_policies
결과: docs/step3_results.md
"""
import numpy as np
import pandas as pd

from src.config.settings import ROOT_DIR, load_thresholds
from src.evaluation.policies import baseline_replace_cycles, evaluate, true_risk_levels
from src.evaluation.replay import out_of_sample_model, run_system
from src.models.tool_wear_model import LABEL_COLUMNS, load_features, worst_edge_vb
from src.simulation.production_sim import load_scenarios

REPORT_PATH = ROOT_DIR / "docs" / "step3_results.md"
SYSTEM = "Multi-Agent 시스템 (센서 + 검사)"
DETAIL_SCENARIOS = ("S01", "S08", "S10", "S15")


def main() -> None:
    df = load_features()
    thresholds = load_thresholds()
    model = out_of_sample_model(df)
    sensor_pred = np.array([model.predictions[c] for c in df["cycle"]])
    baselines = baseline_replace_cycles(df, sensor_pred)

    rows = []
    for sid, ctx in load_scenarios().items():
        result = run_system(df, ctx, model=model)
        outcomes = [evaluate(SYSTEM, result.replace_cycle, len(result.inspection_cycles), df, ctx, thresholds)]
        # '매 Cycle 실측 가정' 방식은 교체할 때까지 매 Cycle 검사가 필요하므로 그만큼 검사 비용을 넣는다
        outcomes += [
            evaluate(name, k, (k or int(df["cycle"].max())) if "실측" in name else 0, df, ctx, thresholds)
            for name, k in baselines.items()
        ]
        for o in outcomes:
            rows.append({"scenario": sid, **o.__dict__})
    res = pd.DataFrame(rows)

    # 시나리오마다 가장 저렴한 방식 대비 비용 비율
    res["cost_ratio"] = res["cost_per_cycle"] / res.groupby("scenario")["cost_per_cycle"].transform("min")
    order = [SYSTEM, *baselines]
    summary = (
        res.groupby("name")
        .agg(
            교체_Cycle=("replace_cycle", "median"),
            검사_횟수=("n_inspections", "mean"),
            한계초과_가공_Cycle=("over_limit_cycles", "mean"),
            최저비용_대비=("cost_ratio", "mean"),
            최저비용_시나리오_수=("cost_ratio", lambda s: int((s <= 1.0 + 1e-9).sum())),
        )
        .reindex(order)
    )

    levels = true_risk_levels(df, thresholds)
    cycles = df["cycle"].to_numpy()
    first = lambda lvl: next((int(c) for c, l in zip(cycles, levels) if l.value == lvl), None)

    lines = [
        "# Step 3 결과: 실제 데이터로 교체 판단 방식 비교",
        "",
        "자동 생성: `python -m scripts.evaluate_policies` / 데이터: QIT-CEMC 68 Cycle (공구 1개) + 시나리오 S01~S24 (MVP 합성값)",
        "",
        "## 평가 방법",
        "",
        "- **센서 예측:** 각 Cycle을 그 Cycle 앞뒤 5개를 학습에서 뺀 모델로 예측 (블록 교차검증). 답을 본 예측이 섞이지 않게 함",
        "- **검사:** 시스템이 검사를 지시하면 그 Cycle의 실제 Edge 1~4 VBmax를 현장 실측값으로 넣음",
        "- **비용:** 공구가 같은 수명을 반복한다고 보고 Cycle당 기대 비용 = (공구값 + 교체 정지 + 검사 정지 + Σ 불량 기대손실) / 교체 Cycle",
        f"  - 불량 기대손실은 실제 최대 날 VB 기준 위험 등급(0.2 mm 미만 LOW / 0.3 mm 미만 MEDIUM / 그 이상 HIGH)의 불량 확률 × 부품가치, Cycle당 부품 1개 가정",
        f"  - 실제 라벨 기준 첫 MEDIUM은 Cycle {first('MEDIUM')}, 첫 HIGH(0.3 mm)는 Cycle {first('HIGH')}",
        "- **비교 기준:** '매 Cycle 실측 가정' 방식은 교체할 때까지 매 Cycle 4날을 검사한다고 보고 검사 비용(검사 1회 = 정지 5분, 가정값)을 넣었다",
        "",
        "## 요약 (시나리오 24개 평균)",
        "",
        "| 방식 | 교체 Cycle (중앙값) | 검사 횟수 | 한계 초과 상태로 가공한 Cycle | 최저 비용 대비 | 최저 비용인 시나리오 수 |",
        "|---|---|---|---|---|---|",
    ]
    for name, r in summary.iterrows():
        lines.append(
            f"| {name} | {r['교체_Cycle']:.0f} | {r['검사_횟수']:.1f} | {r['한계초과_가공_Cycle']:.1f} | {r['최저비용_대비']:.2f}배 | {int(r['최저비용_시나리오_수'])} / 24 |"
        )

    lines += ["", "## 대표 시나리오", ""]
    scenarios = load_scenarios()
    for sid in DETAIL_SCENARIOS:
        ctx = scenarios[sid]
        lines += [
            f"### {sid}: 부품가치 {ctx.part_value:,.0f}원, 공구 {ctx.tool_price:,.0f}원, 재고 {ctx.tool_stock}개, "
            f"검사 {'가능' if ctx.inspection_available else '불가'}, 남은 부품 {ctx.remaining_parts}개",
            "",
            "| 방식 | 교체 Cycle | 검사 | 한계 초과 가공 | Cycle당 비용(원) |",
            "|---|---|---|---|---|",
        ]
        for _, r in res[res["scenario"] == sid].iterrows():
            lines.append(
                f"| {r['name']} | {r['replace_cycle']}{'' if r['replaced'] else ' (교체 안 함)'} | {r['n_inspections']} | "
                f"{r['over_limit_cycles']} | {r['cost_per_cycle']:,.0f} |"
            )
        lines.append("")

    lines += [
        "## 해석",
        "",
        "- **평균 기준은 가장 많이 닳은 날을 놓친다.** 교체가 Cycle 53으로 늦고, 한계(0.3 mm)를 넘은 상태로 10 Cycle을 가공한다.",
        "- **최대 날 0.3 mm 기준**도 표면 결함이 늘어나는 0.2~0.3 mm 구간을 오래 가공해 불량 기대손실이 크다.",
        "- **Multi-Agent 시스템**은 센서 예측이 주의 구간에 들어올 때만 4날을 검사(평균 2~3회)해 날별 실제 상태를 확인하고,",
        "  품질 위험과 부품가치·재고를 함께 보고 교체한다. 한계 초과 가공은 0 Cycle이다.",
        "- **이상적인 방식(매 Cycle 4날 검사 + 0.2 mm 기준)이 가장 저렴하다.** 검사 1회 비용(정지 5분 가정)이 고가 부품의",
        "  불량 손실보다 훨씬 작기 때문이다. 시스템은 검사를 평균 2~3회만 하는 대신 교체가 2 Cycle 늦어 비용이 더 든다.",
        "  실제 최대 날이 처음 0.2 mm를 넘는 Cycle 11은 한 날만 갑자기 튄 값이라 공구 단위 센서 예측으로는 잡기 어렵다.",
        "- 검사가 오래 걸리거나(공구를 빼서 현미경 측정) 검사 인력이 부족한 현장일수록 시스템 방식이 유리해진다.",
        "",
        "## 한계",
        "",
        "- 공구 1개의 기록을 반복한다고 가정한 평가다. 다른 공구에서의 일반화는 검증하지 못했다.",
        "- 비용·불량 확률·검사 시간은 모두 MVP 가정값이다. 비용 수치는 '시뮬레이션 기준'으로만 말할 수 있다.",
        "- 시스템과 평가가 같은 위험 등급 기준(0.2 / 0.3 mm)을 쓰므로, 고정 기준 방식보다 유리한 면이 있다.",
        "- 라벨 노이즈 때문에 교체 시점이 한두 Cycle 앞뒤로 달라질 수 있다.",
        "- 재검사 간격(0.03 mm)은 이 공구 하나의 재생 결과를 보고 골랐다 (0.05 mm일 때 이상적 대비 1.41배 → 0.03 mm일 때 1.19배).",
        "  같은 데이터로 고르고 평가했으므로 다른 공구에서는 성능이 더 낮을 수 있다.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
