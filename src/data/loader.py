"""QIT-CEMC 데이터셋 로더. (Track A)

데이터 구조 (docs/qit_cemc_data_report.md 참고):
- Force and torque data/MM-DD-N.txt : 탭 구분, 열 Time Fx Fy Fz Mz, 10 kHz (68개)
- Vibration and sound data/MM-DD-NN.csv|xlsx : 열 time, 진동 X/Y/Z [m/s²], 소리 [Pa] (67개, Cycle 2 없음)
- tool wear.xls : Cycle별 측면 날(Side teeth) Edge 1~4 VBmax 등

파일 이름의 날짜·순번 순서가 Cycle 1~68 순서다. 순번은 '1'과 '01'처럼 표기가 섞여 있어 숫자로 비교한다.
"""
import re
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.config.settings import DATA_RAW_DIR, N_EDGES
from src.schemas import SensorWindow

FORCE_DIR = "Force and torque data"
VIBRATION_DIR = "Vibration and sound data"
LABEL_FILE = "tool wear.xls"
SAMPLING_RATE_HZ = 10_000.0

FORCE_COLUMNS = {"Fx": "Fx", "Fy": "Fy", "Fz": "Fz", "Mz": "Mz"}
# 진동/소리 채널 이름 → (원본 열 이름 접두어, 기대 단위)
VIBRATION_COLUMNS = {
    "vib_x": ("AI1-01", "m/s"),
    "vib_y": ("AI1-02", "m/s"),
    "vib_z": ("AI1-03", "m/s"),
    "sound": ("AI1-07", "Pa"),
}

# tool wear.xls: 앞 4행은 머리글, 측면 날 Edge 1~4의 VBmax 열 위치
LABEL_HEADER_ROWS = 4
SIDE_VBMAX_COLUMNS = (1, 4, 7, 10)

# 절삭 구간 검출: 0.1초 구간별 표준편차(신호의 출렁임)가 상위 수준의 10%를 넘는 첫 구간~마지막 구간.
# 절삭 중에는 날이 하나씩 맞물릴 때마다 힘·진동이 크게 출렁이고, 공회전·정지 중에는 거의 변하지 않는다.
ACTIVE_WINDOW_S = 0.1
ACTIVE_RATIO = 0.1

# 진동 파일에서 숫자로 읽을 수 없는 값이 이 비율을 넘으면 파일 전체를 결측 처리한다.
# Cycle 39 파일은 약 24%가 손상돼 있고, 숫자로 읽힌 나머지 값도 비정상(소리 RMS 1e29 등)이었다.
MAX_CORRUPT_FRACTION = 0.05

NAME_PATTERN = re.compile(r"^(\d{2})-(\d{2})-(\d+)$")


@dataclass(frozen=True)
class CycleFiles:
    cycle: int
    force: Path
    vibration: Path | None  # Cycle 2는 진동/소리 데이터가 없다


def _sort_key(path: Path) -> tuple[int, int, int]:
    m = NAME_PATTERN.match(path.stem)
    if not m:
        raise ValueError(f"예상과 다른 파일 이름: {path.name}")
    month, day, run = (int(g) for g in m.groups())
    return month, day, run


def list_cycles(root: Path | str = DATA_RAW_DIR) -> list[CycleFiles]:
    root = Path(root)
    force_files = sorted((root / FORCE_DIR).glob("*.txt"), key=_sort_key)
    vibration_by_key = {
        _sort_key(p): p for p in (root / VIBRATION_DIR).iterdir() if p.suffix.lower() in (".csv", ".xlsx")
    }
    return [
        CycleFiles(cycle=i, force=f, vibration=vibration_by_key.get(_sort_key(f)))
        for i, f in enumerate(force_files, start=1)
    ]


def load_labels(root: Path | str = DATA_RAW_DIR) -> dict[int, list[float]]:
    """Cycle → 측면 날 Edge 1~4 VBmax (mm)."""
    root = Path(root)
    import xlrd

    sheet = xlrd.open_workbook(root / LABEL_FILE).sheet_by_index(0)
    labels = {}
    for r in range(LABEL_HEADER_ROWS, sheet.nrows):
        row = sheet.row_values(r)
        if row[0] == "":
            continue
        labels[int(row[0])] = [float(row[c]) for c in SIDE_VBMAX_COLUMNS]
    return labels


def active_slice(signal: np.ndarray, fs: float = SAMPLING_RATE_HZ) -> slice:
    """실제 절삭 구간 (신호 출렁임이 충분히 큰 첫 구간 ~ 마지막 구간)."""
    window = max(1, int(ACTIVE_WINDOW_S * fs))
    n_windows = len(signal) // window
    if n_windows == 0:
        return slice(0, len(signal))
    std = signal[: n_windows * window].reshape(n_windows, window).std(axis=1)
    threshold = ACTIVE_RATIO * np.percentile(std, 95)
    active = np.flatnonzero(std > threshold)
    if len(active) == 0:
        return slice(0, len(signal))
    return slice(active[0] * window, (active[-1] + 1) * window)


def read_force(path: Path) -> dict[str, np.ndarray]:
    df = pd.read_csv(path, sep="\t", usecols=list(FORCE_COLUMNS), dtype="float32", engine="c", encoding_errors="ignore")
    return {name: df[col].to_numpy() for name, col in FORCE_COLUMNS.items()}


def vibration_columns(header: list[str]) -> list[int]:
    """머리글에서 진동 X/Y/Z, 소리 열 위치를 찾는다. 단위가 다르면 ValueError.

    대부분의 파일은 `AI1-01[m/s²], AI1-02, AI1-03, AI1-07[Pa]` 4채널이지만,
    마지막 4개 Cycle(65~68)은 8채널 `AI1-01[mV] ... AI1-08[mV]` 보정 전 전압이라 다른 Cycle과 비교할 수 없다.
    """
    positions = []
    for name, (prefix, unit) in VIBRATION_COLUMNS.items():
        matches = [i for i, h in enumerate(header) if str(h).strip().startswith(prefix)]
        if not matches:
            raise ValueError(f"{name} 채널({prefix}) 없음")
        if unit not in str(header[matches[0]]):
            raise ValueError(f"{name} 단위가 {unit}이 아님: {header[matches[0]]}")
        positions.append(matches[0])
    return positions


def read_vibration(path: Path) -> dict[str, np.ndarray]:
    """원본 파일 일부가 손상돼 있다 (docs/qit_cemc_data_report.md):
    xlsx 2개(Cycle 21, 54)는 내부가 잘려 열 수 없고, csv 1개(Cycle 39)는 숫자 중간에 깨진 문자가 있다."""
    if path.suffix.lower() == ".xlsx":
        header = pd.read_excel(path, nrows=0, engine="openpyxl").columns.tolist()
        df = pd.read_excel(path, usecols=vibration_columns(header), engine="openpyxl")
    else:
        header = pd.read_csv(path, nrows=0, encoding_errors="ignore").columns.tolist()
        df = pd.read_csv(path, usecols=vibration_columns(header), engine="c", encoding_errors="ignore", dtype=str)
        # 깨진 값만 NaN으로 바꾼다 (손상 비율이 크면 load_cycle에서 파일 전체를 결측 처리)
        df = df.apply(pd.to_numeric, errors="coerce")
    return {name: df.iloc[:, i].to_numpy(dtype="float32") for i, name in enumerate(VIBRATION_COLUMNS)}


def load_cycle(files: CycleFiles, labels: dict[int, list[float]], tool_id: str = "QIT-CEMC") -> SensorWindow:
    """한 Cycle을 읽어 절삭 구간만 남긴 SensorWindow를 만든다.

    cumulative_cut_time_min 에는 이 Cycle의 절삭 시간만 넣는다. 누적값은 호출하는 쪽에서 Cycle 순서대로 더한다.
    """
    force = read_force(files.force)
    magnitude = np.sqrt(force["Fx"] ** 2 + force["Fy"] ** 2 + force["Fz"] ** 2)
    cut = active_slice(magnitude)
    signals = {name: x[cut] for name, x in force.items()}

    vibration = None
    if files.vibration is not None:
        try:
            vibration = read_vibration(files.vibration)
        except Exception as e:  # 손상됐거나 단위가 다른 진동 파일은 결측으로 처리하고 힘/토크만 사용한다
            warnings.warn(f"Cycle {files.cycle} 진동 파일을 쓸 수 없어 결측 처리: {files.vibration.name} ({type(e).__name__}: {e})")
        else:
            corrupt = max(float(np.mean(~np.isfinite(x))) for x in vibration.values())
            if corrupt > MAX_CORRUPT_FRACTION:
                warnings.warn(f"Cycle {files.cycle} 진동 파일 손상 {corrupt:.0%} → 결측 처리: {files.vibration.name}")
                vibration = None
        if vibration is not None:
            vib_cut = active_slice(np.nan_to_num(vibration["vib_x"]))
            signals.update({name: x[vib_cut] for name, x in vibration.items()})

    label = labels.get(files.cycle)
    return SensorWindow(
        tool_id=tool_id,
        cycle=files.cycle,
        sampling_rate_hz=SAMPLING_RATE_HZ,
        signals=signals,
        cumulative_cut_time_min=(cut.stop - cut.start) / SAMPLING_RATE_HZ / 60,
        vb_label_mm=label if label is not None and len(label) == N_EDGES else None,
    )


def load_qit_cemc(root: Path | str = DATA_RAW_DIR) -> Iterator[SensorWindow]:
    """Cycle 순서대로 하나씩 읽는다 (40GB 전체를 메모리에 올리지 않음)."""
    labels = load_labels(root)
    elapsed = 0.0
    for files in list_cycles(root):
        window = load_cycle(files, labels)
        elapsed += window.cumulative_cut_time_min
        window.cumulative_cut_time_min = elapsed
        yield window
