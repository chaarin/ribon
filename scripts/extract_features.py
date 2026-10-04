"""QIT-CEMC 전체 Cycle에서 특징을 추출해 작은 CSV 하나로 저장한다. (Track A, 학교 서버에서 실행)

실행: python -m scripts.extract_features [--root data/raw/QIT-CEMC]
결과: data/features/qit_cemc_features.csv  (1행 = 1 Cycle, git에 올림)

src/data/loader.py 의 load_qit_cemc 를 먼저 구현해야 한다.
Cycle을 하나씩 읽고 바로 버리므로 40GB 전체를 메모리에 올리지 않는다.
"""
import argparse
import csv
from pathlib import Path

from src.config.settings import DATA_RAW_DIR, N_EDGES, ROOT_DIR
from src.data.features import extract_features
from src.data.loader import load_qit_cemc
from src.data.preprocess import channel_quality, preprocess

OUTPUT_PATH = ROOT_DIR / "data" / "features" / "qit_cemc_features.csv"
LABEL_COLUMNS = [f"edge{i}_vbmax_mm" for i in range(1, N_EDGES + 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DATA_RAW_DIR)
    args = parser.parse_args()

    rows = []
    for window in load_qit_cemc(args.root):
        row = {"tool_id": window.tool_id, "cycle": window.cycle}
        row.update(extract_features(preprocess(window), window))
        row["signal_quality"] = min(channel_quality(window).values())
        labels = window.vb_label_mm or [None] * N_EDGES
        row.update(dict(zip(LABEL_COLUMNS, labels)))
        rows.append(row)
        print(f"{window.tool_id} cycle {window.cycle}: 특징 {len(row)}개")

    if not rows:
        raise SystemExit("읽은 Cycle이 없습니다. --root 경로와 loader를 확인하세요.")

    columns = list(dict.fromkeys(k for r in rows for k in r))  # 첫 등장 순서 유지
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)}개 Cycle → {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
