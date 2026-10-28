# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from config import BRAIN_DIR, STREAMER_ID
from reflection_curator import ReflectionCurator


def parse_turns(path: Path):
    last_input = ""
    stage_mode = ""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "| INPUT |" in line and "text=" in line:
                last_input = line.split("text=", 1)[-1].strip()
            elif "| STAGE_DIRECTOR |" in line:
                m = re.search(r'"mode"\s*:\s*"([^"]+)"', line)
                if m:
                    stage_mode = m.group(1)
            elif "| OUTPUT | Моника:" in line:
                reply = line.split("| OUTPUT | Моника:", 1)[-1].strip()
                if last_input and reply:
                    yield last_input, reply, stage_mode
                    stage_mode = ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    log_path = Path(args.logfile)
    if not log_path.exists():
        raise SystemExit(f"Log not found: {log_path}")

    db = Path(BRAIN_DIR) / "knowledge.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    curator = ReflectionCurator(conn)

    count = 0
    for user_input, reply, stage_mode in parse_turns(log_path):
        result = curator.classify_reply(user_input, reply, stage_mode=stage_mode)
        count += 1
        print(f"[{count}] {result['quality']} score={result['score']} stage={stage_mode} reasons={result['reasons']}")
        print(" U:", user_input[:140])
        print(" M:", reply[:180])
        if args.apply:
            curator.observe_turn(STREAMER_ID, user_input, reply, stage_mode=stage_mode, source=f"log:{log_path.name}")
    print(f"\nParsed turns: {count}")
    print("Mode:", "APPLY" if args.apply else "DRY-RUN")
    conn.close()


if __name__ == "__main__":
    main()
