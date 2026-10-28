
# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path

from yuna_memory_bridge import YunaMemoryBridge

ROOT = Path(__file__).resolve().parent
DB = ROOT / "knowledge.db"


def main() -> None:
    if not DB.exists():
        print(f"knowledge.db not found: {DB}")
        return
    conn = sqlite3.connect(str(DB))
    bridge = YunaMemoryBridge(conn)
    print("YunaBridge summary:")
    print(bridge.inspect())

    print("\nAliases:")
    try:
        for row in conn.execute("SELECT alias, person_id, display_name, confidence, source FROM person_alias_map ORDER BY person_id, confidence DESC, alias LIMIT 40"):
            print(f"- {row[0]} -> {row[1]} / {row[2]} ({row[3]}, {row[4]})")
    except Exception as exc:
        print(f"alias read error: {exc}")

    print("\nRecent bridge turns:")
    try:
        for row in conn.execute("SELECT id, stage_mode, summary, user_input FROM yuna_bridge_turns ORDER BY id DESC LIMIT 12"):
            print(f"#{row[0]} [{row[1]}] {row[2]} | U: {str(row[3] or '')[:100]}")
    except Exception as exc:
        print(f"turn read error: {exc}")

    print("\nSession recap test:")
    print(bridge.build_session_recap_answer())


if __name__ == "__main__":
    main()
