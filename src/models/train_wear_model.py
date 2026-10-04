"""마모 예측 모델 평가와 결과 보고서 생성. (Track B)

실행: python -m src.models.train_wear_model
결과: docs/track_b_results.md

학습된 모델은 파일로 저장하지 않는다. 특징 CSV(68행)로 1초 안에 다시 학습되므로
src.models.tool_wear_model.train_tool_wear_model 을 필요할 때 호출한다.
"""
import numpy as np
import pandas as pd

from src.config.settings import ROOT_DIR
from src.models.tool_wear_model import (
    FEATURE_COLUMNS,
    LABEL_COLUMNS,
    blocked_cv_predictions,
    load_features,
    make_regressor,
    worst_edge_vb,
)

REPORT_PATH = ROOT_DIR / "docs" / "track_b_results.md"
TRAIN_UNTIL = 25  # 실제 최대 날이 0.3 mm에 처음 도달하는 Cycle 31 이전까지만 학습
VB_LIMIT = 0.3
FEATURE_SETS = {
    "누적 절삭시간만 (기준선)": ["cut_time_min"],
    "힘/토크만 (채택)": FEATURE_COLUMNS,
    "힘/토크 + 누적 절삭시간": FEATURE_COLUMNS + ["cut_time_min"],
}


def first_cycle(mask: np.ndarray, cycles: np.ndarray) -> int | None:
    return int(cycles[np.argmax(mask)]) if mask.any() else None


def chronological_eval(df: pd.DataFrame) -> list[dict]:
    train, test = df["cycle"] <= TRAIN_UNTIL, df["cycle"] > TRAIN_UNTIL
    y, cycles = worst_edge_vb(df), df["cycle"].to_numpy()
    rows = []
    for name, cols in FEATURE_SETS.items():
        pred = make_regressor().fit(df.loc[train, cols], y[train]).predict(df.loc[test, cols])
        err = pred - y[test]
        rows.append(
            {
                "특징": name,
                "MAE (mm)": np.abs(err).mean(),
                "RMSE (mm)": np.sqrt((err**2).mean()),
                "0.3 mm 도달 예측 Cycle": first_cycle(pred >= VB_LIMIT, cycles[test]),
            }
        )
    return rows


def edge_identification(df: pd.DataFrame) -> dict:
    """Cycle 단위 특징으로 날별 VBmax를 따로 예측했을 때 '가장 많이 닳은 날'을 맞히는지."""
    train, test = df["cycle"] <= TRAIN_UNTIL, df["cycle"] > TRAIN_UNTIL
    Y = df[LABEL_COLUMNS].to_numpy()
    P = make_regressor().fit(df.loc[train, FEATURE_COLUMNS], Y[train]).predict(df.loc[test, FEATURE_COLUMNS])
    mean_pred = make_regressor().fit(df.loc[train, FEATURE_COLUMNS], Y[train].mean(1)).predict(df.loc[test, FEATURE_COLUMNS])
    return {
        "worst_edge_accuracy": float(np.mean(P.argmax(1) == Y[test].argmax(1))),
        "per_edge_mae": float(np.abs(P - Y[test]).mean()),
        "same_value_mae": float(np.abs(mean_pred[:, None] - Y[test]).mean()),
    }


def label_noise(df: pd.DataFrame) -> float:
    smooth = df[LABEL_COLUMNS].rolling(5, center=True, min_periods=1).median()
    return float((df[LABEL_COLUMNS] - smooth).abs().to_numpy().mean())


def main() -> None:
    df = load_features()
    y, cycles = worst_edge_vb(df), df["cycle"].to_numpy()
    chrono = chronological_eval(df)
    ident = edge_identification(df)
    oos = blocked_cv_predictions(df).to_numpy()
    sigma = float(np.std(oos - y))

    table = "\n".join(
        f"| {r['특징']} | {r['MAE (mm)']:.3f} | {r['RMSE (mm)']:.3f} | {r['0.3 mm 도달 예측 Cycle']} |" for r in chrono
    )
    report = f"""# Track B 결과: 마모 예측 모델

자동 생성: `python -m src.models.train_wear_model` / 데이터: `data/features/qit_cemc_features.csv` (68 Cycle, 공구 1개)

## 결론

- 센서(Cycle 단위 특징)로는 **어느 날이 가장 많이 닳았는지 구분할 수 없다.** 그래서 공구 전체의 위험 수준인
  **가장 많이 닳은 날의 VBmax**와 불확실성을 예측하고, 날별 상태는 현장 검사(Feedback)로 확인한다.
- 모델: 표준화 + Ridge 회귀(α=10), 입력 = 힘/토크 4채널의 rms·std·peak (12개).
  진동은 8개 Cycle(마모가 가장 심한 65~68 포함)에 없어 쓰지 않는다.
  누적 절삭시간을 더하면 오히려 나빠져서 넣지 않았다 (아래 표). 센서만으로 시간 기준선과 같은 수준을 낸다.
- 실제 최대 날이 처음 0.3 mm를 넘는 Cycle은 **{first_cycle(y >= VB_LIMIT, cycles)}** (4날 평균 기준으로는 {first_cycle(df[LABEL_COLUMNS].mean(axis=1).to_numpy() >= VB_LIMIT, cycles)}).

## 1. 시간 순서 평가 (Cycle 1~{TRAIN_UNTIL} 학습 → {TRAIN_UNTIL + 1}~68 예측)

첫 0.3 mm 도달(Cycle 31)을 학습에서 보지 않도록 그 이전까지만 학습했다.

| 특징 | MAE (mm) | RMSE (mm) | 0.3 mm 도달 예측 Cycle |
|---|---|---|---|
{table}

- 센서(힘/토크)만으로 누적 절삭시간 기준선과 같은 수준이다. 다만 **공구가 1개뿐이라 시간이 마모를 대부분 설명**해서
  센서가 시간보다 낫다고 주장할 수는 없다.
  센서가 시간 이상의 정보를 주는지는 마모 속도가 다른 여러 공구의 데이터가 있어야 검증할 수 있다.

## 2. 날별 구분 가능성

같은 특징으로 Edge 1~4를 따로 예측한 경우 (Cycle 1~{TRAIN_UNTIL} 학습):

- 가장 많이 닳은 날을 맞힌 비율: **{ident['worst_edge_accuracy']:.0%}** (무작위로 찍으면 25%)
- 날별 MAE {ident['per_edge_mae']:.3f} mm vs 4날을 같은 값으로 예측 {ident['same_value_mae']:.3f} mm → 날별로 나눠도 나아지지 않음

원인: 특징이 4개 날이 번갈아 깎은 신호 전체의 통계라서 날 정보가 없다.
회전 한 바퀴 안의 날별 봉우리를 분리하는 방법도 시험했지만, 회전 위치 신호가 없어 날을 특정할 수 없고
공구 편심(런아웃) 성분이 섞여 실제 편마모와 연결되지 않았다 (docs/qit_cemc_data_report.md).
**스핀들 엔코더(회전 각도) 신호를 함께 수집하면 날별 분리가 가능할 것**으로 본다.

## 3. 불확실성

- 블록 교차검증(각 Cycle 앞뒤 5개를 빼고 학습) 예측 오차의 표준편차: **σ ≈ {sigma:.3f} mm**
- 라벨 자체의 흔들림(앞뒤 5 Cycle 이동중앙값 대비 평균 차이): {label_noise(df):.3f} mm
- Wear Agent는 이 σ를 불확실성으로 내보내고, Master Agent는 예측+σ가 주의 구간(0.2 mm)에 들어오면 4날 검사를 지시한다.

## 한계

- 공구 1개: 다른 공구·조건에서의 일반화는 검증하지 못했다.
- 라벨 노이즈: 정답값이 Cycle마다 감소하기도 한다(치핑·측정 편차). 첫 0.3 mm 도달 Cycle(31)도 다음 Cycle에 0.26으로 내려간다.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
