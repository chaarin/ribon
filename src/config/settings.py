"""프로젝트 공통 설정: 경로, 공구 스펙, 임계값 로딩."""
from functools import lru_cache
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "outputs"
THRESHOLDS_PATH = Path(__file__).with_name("thresholds.yaml")

# 공구: 4날 코팅 카바이드 엔드밀
N_EDGES = 4

# QIT-CEMC 센서 채널 (Force/Torque, Vibration, Sound)
SENSOR_CHANNELS = ("Fx", "Fy", "Fz", "Mz", "vib_x", "vib_y", "vib_z", "sound")


@lru_cache
def load_thresholds(path: Path = THRESHOLDS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
