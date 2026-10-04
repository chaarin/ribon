"""모든 Agent의 공통 인터페이스."""
from abc import ABC, abstractmethod

from src.config.settings import load_thresholds


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, thresholds: dict | None = None):
        self.thresholds = thresholds or load_thresholds()

    @abstractmethod
    def analyze(self, *args, **kwargs):
        """입력 스키마를 받아 출력 스키마(Report/Decision)를 반환한다."""
