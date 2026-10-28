from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from opinion_core import OpinionCore
from session_mind import SessionMind
from stage_director import StageDirector
from response_guard import ResponseGuard

ROOT = Path(__file__).resolve().parent
DB = ROOT / "knowledge.db"


def main() -> None:
    text = " ".join(sys.argv[1:]).strip() or "Тебе нравится брокколи?"
    conn = sqlite3.connect(DB) if DB.exists() else sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    oc = OpinionCore(conn)
    sd = StageDirector()
    sm = SessionMind()
    rg = ResponseGuard()

    opinion = oc.get_current_opinion(text, create=oc.is_opinion_request(text))
    stage = sd.classify(text, opinion_request=oc.is_opinion_request(text))
    sm.observe_turn(text, "Тестовая реплика.", stage=stage["stage"])

    print("Input:", text)
    print("\nOpinionCore:")
    print(opinion or "no opinion request")

    print("\nStageDirector:")
    print(stage)

    print("\nSessionMind:")
    print(sm.build_prompt_block(text))

    print("\nResponseGuard examples:")
    for reply in [
        "Я чуть не повторила тебя попугаем.",
        "БРОККОЛИ? ОН НЕ СПРАШИВАЛ ПОЧЕМУ!",
        "По вайбу спорно, но я бы прицепилась.",
    ]:
        print("-", reply, "=>", rg.assess(reply, text, {"relationship_role": "creator", "opinion": opinion}))


if __name__ == "__main__":
    main()
