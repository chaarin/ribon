"""QIT-CEMC 데이터셋 로더. (Track A)

TODO(Track A): 학교 서버의 데이터 구조를 확인한 뒤 구현한다.
- 각 Cycle의 센서 파일을 읽어 SensorWindow로 변환
- 채널명은 settings.SENSOR_CHANNELS 에 맞춰 매핑
- Cycle별 Edge 1~4 VBmax 라벨을 SensorWindow.vb_label_mm 에 채움
"""
from collections.abc import Iterator
from pathlib import Path

from src.config.settings import DATA_RAW_DIR
from src.schemas import SensorWindow


def load_qit_cemc(root: Path = DATA_RAW_DIR) -> Iterator[SensorWindow]:
    raise NotImplementedError("데이터 구조 확인 후 구현 예정 (Track A)")
