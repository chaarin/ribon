"""판단·실행·검사 이력 저장소 (JSON Lines)."""
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path


class HistoryStore:
    def __init__(self, path: Path | None = None):
        """path가 없으면 메모리에만 기록한다 (테스트용)."""
        self.path = path
        self._records: list[dict] = []

    def append(self, event: str, payload) -> None:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": asdict(payload) if is_dataclass(payload) else payload,
        }
        self._records.append(record)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def records(self, event: str | None = None) -> list[dict]:
        return [r for r in self._records if event is None or r["event"] == event]
