# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

from config import DB_PATH, STREAMER_ID
from social_memory import SocialMemoryCore
import sqlite3


def main() -> None:
    person_id = sys.argv[1] if len(sys.argv) > 1 else STREAMER_ID
    db = Path(DB_PATH)
    if not db.exists():
        raise SystemExit(f"DB not found: {db}")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    sm = SocialMemoryCore(conn, creator_id=STREAMER_ID)
    data = sm.inspect_person(person_id)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    conn.close()


if __name__ == "__main__":
    main()
