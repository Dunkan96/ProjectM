# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any


class DebugTrace:
    """JSONL trace: почему мозг выбрал фокус, память, людей и политику ответа."""

    def __init__(self, path: str | Path | None = None, logger: logging.Logger | None = None):
        self.path = Path(path) if path else None
        self.logger = logger

    def record(self, event: str, payload: dict[str, Any]) -> None:
        item = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "payload": self._safe(payload),
        }
        line = json.dumps(item, ensure_ascii=False, default=str)
        if self.logger:
            try:
                self.logger.info("COGNITIVE_TRACE | %s", line)
            except Exception:
                pass
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def _safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe(x) for x in value[:30]]
        if hasattr(value, "to_dict"):
            try:
                return self._safe(value.to_dict())
            except Exception:
                return str(value)
        if hasattr(value, "__dict__") and value.__class__.__module__ != "builtins":
            return self._safe(value.__dict__)
        return value

