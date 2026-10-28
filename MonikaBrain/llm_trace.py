# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class LLMTrace:
    """Writes full LLM calls to Logs/llm_trace_YYYYMMDD.jsonl for postmortem debugging."""

    def __init__(self, logs_dir: str | Path = "Logs"):
        self.logs_dir = Path(logs_dir)

    def record(
        self,
        *,
        turn_id: str = "",
        purpose: str = "main",
        model: str = "",
        messages: list[dict[str, Any]] | None = None,
        params: dict[str, Any] | None = None,
        raw: str = "",
        final: str = "",
        policy: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        try:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            path = self.logs_dir / f"llm_trace_{time.strftime('%Y%m%d')}.jsonl"
            item = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "turn_id": turn_id,
                "purpose": purpose,
                "model": model,
                "params": params or {},
                "messages": messages or [],
                "raw": raw,
                "final": final,
                "policy": policy or {},
                "error": error,
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

