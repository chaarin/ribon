"""Master Agent 출력 형식."""
from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    CONTINUE = "CONTINUE"  # 계속 가공
    REMEASURE = "REMEASURE"  # 센서 재측정
    INSPECT_EDGE = "INSPECT_EDGE"  # 특정 날 검사
    REPLACE_AFTER_JOB = "REPLACE_AFTER_JOB"  # 현재 공정 후 교체
    REPLACE_NOW = "REPLACE_NOW"  # 즉시 교체


@dataclass
class Decision:
    tool_id: str
    cycle: int
    action: Action
    target_edge: int | None = None  # INSPECT_EDGE일 때 검사할 날 (None이면 4개 날 모두 검사)
    reasons: list[str] = field(default_factory=list)
    confidence: float = 1.0
