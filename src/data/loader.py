"""QIT-CEMC 데이터셋 로더. (Track A)

데이터: Ti-6Al-4V 밀링, 원본 약 11GB (압축 해제 약 40GB), 약 68 Cycle
- 입력: Fx, Fy, Fz, Mz / Vibration X, Y, Z / Sound
- 라벨: Cycle별 Edge 1~4 VBmax

TODO(Track A, 학교 서버에서 진행):
- 각 Cycle의 센서 파일을 읽어 SensorWindow로 변환
- 원본 채널명과 라벨 열 이름(예: Edg1_VBmax / Edge2_VBmax 처럼 표기가 섞여 있는지)을 확인해
  settings.SENSOR_CHANNELS 와 Edge 1~4 순서로 매핑
- 40GB 전체를 메모리에 올리지 말고 Cycle 단위로 읽어 특징만 추출 (scripts/extract_features.py 예정)
"""
from collections.abc import Iterator
from pathlib import Path

from src.config.settings import DATA_RAW_DIR
from src.schemas import SensorWindow


def load_qit_cemc(root: Path = DATA_RAW_DIR) -> Iterator[SensorWindow]:
    raise NotImplementedError("데이터 구조 확인 후 구현 예정 (Track A)")
