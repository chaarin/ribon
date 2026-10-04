"""QIT-CEMC 전체 Cycle에서 특징을 추출해 작은 CSV 하나로 저장한다. (Track A, 학교 서버에서 실행)

실행: python -m scripts.extract_features --root <QIT-CEMC 폴더> [--workers 4]
결과: data/features/qit_cemc_features.csv  (1행 = 1 Cycle, git에 올림)

Cycle 파일을 여러 프로세스가 나눠 읽고, 각 프로세스는 한 번에 한 Cycle만 메모리에 둔다.
"""
import argparse
import csv
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from src.config.settings import DATA_RAW_DIR, N_EDGES, ROOT_DIR
from src.data.features import extract_features
from src.data.loader import CycleFiles, list_cycles, load_cycle, load_labels
from src.data.preprocess import channel_quality, preprocess

OUTPUT_PATH = ROOT_DIR / "data" / "features" / "qit_cemc_features.csv"
LABEL_COLUMNS = [f"edge{i}_vbmax_mm" for i in range(1, N_EDGES + 1)]


def process_cycle(files: CycleFiles, labels: dict[int, list[float]]) -> dict:
    window = load_cycle(files, labels)
    row = {"tool_id": window.tool_id, "cycle": window.cycle, "cycle_cut_time_min": window.cumulative_cut_time_min}
    row.update(extract_features(preprocess(window), window))
    del row["cut_time_min"]  # 누적값은 전체 Cycle을 모은 뒤 계산한다
    row["signal_quality"] = min(channel_quality(window).values())
    row["vibration_available"] = "vib_x" in window.signals
    row.update(dict(zip(LABEL_COLUMNS, window.vb_label_mm or [None] * N_EDGES)))
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DATA_RAW_DIR)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N개 Cycle만 처리 (시험용)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    cycles = list_cycles(args.root)[: args.limit]
    labels = load_labels(args.root)
    print(f"Cycle {len(cycles)}개, 프로세스 {args.workers}개", flush=True)

    start = time.time()
    rows, failed = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_cycle, c, labels): c for c in cycles}
        for future in as_completed(futures):
            files = futures[future]
            try:
                row = future.result()
            except Exception as e:  # 한 Cycle 실패가 전체 추출을 멈추지 않게 한다
                failed.append(files.cycle)
                print(f"Cycle {files.cycle} 실패 ({files.force.name}, {files.vibration}): {type(e).__name__}: {e}", flush=True)
                continue
            rows.append(row)
            print(f"[{len(rows) + len(failed)}/{len(cycles)}] Cycle {row['cycle']} 완료 ({time.time() - start:.0f}초)", flush=True)

    rows.sort(key=lambda r: r["cycle"])
    elapsed = 0.0
    for row in rows:
        elapsed += row["cycle_cut_time_min"]
        row["cut_time_min"] = elapsed

    columns = list(dict.fromkeys(k for r in rows for k in r))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)}개 Cycle → {args.output} ({args.output.stat().st_size / 1024:.0f}KB, {time.time() - start:.0f}초)")
    if failed:
        raise SystemExit(f"실패한 Cycle: {sorted(failed)}")


if __name__ == "__main__":
    main()
