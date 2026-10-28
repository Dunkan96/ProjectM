from __future__ import annotations

import ast
import gc
import json
import py_compile
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

GUARD = ROOT / "attention_safety_guard.py"
DB_CANDIDATES = [
    ROOT / "monika_memory.db",
    ROOT / "knowledge.db",
]


PATCH_MARKER_START = "# === MONIKA STRICT TOPIC GUARD V1 START ==="
PATCH_MARKER_END = "# === MONIKA STRICT TOPIC GUARD V1 END ==="


STRICT_WRAPPER = r'''
# === MONIKA STRICT TOPIC GUARD V1 START ===
# Added by apply_monika_attention_safety_strict_topics_v1.py
#
# Purpose:
#   Extra strict Twitch guard for bait questions that ask Monika for opinions
#   on religion, politics, protected/social groups, or identity-loaded topics.
#
# Safety contract:
#   Such messages must not be passed to the LLM as normal viewer questions.

import re as _monika_strict_re

_MONIKA_STRICT_ORIGINAL_CLASSIFY = classify_message
_MONIKA_STRICT_ORIGINAL_GUARD_CLASS = AttentionSafetyGuard

_MONIKA_STRICT_OPINION_PATTERNS = [
    r"\bчто\s+ты\s+думаешь\s+о\b",
    r"\bчто\s+думаешь\s+о\b",
    r"\bтв[оёе]\s+мнение\s+о\b",
    r"\bкак\s+ты\s+относишься\s+к\b",
    r"\bоцени\b",
    r"\bкто\s+лучше\b",
    r"\bкто\s+хуже\b",
    r"\bкого\s+ты\s+поддерживаешь\b",
]

_MONIKA_STRICT_TOPIC_PATTERNS = [
    r"\bрелиги[ияею]\b",
    r"\bрелигиоз\w*\b",
    r"\bхристиан\w*\b",
    r"\bмусульман\w*\b",
    r"\bислам\w*\b",
    r"\bевре\w*\b",
    r"\bиуде\w*\b",
    r"\bатеист\w*\b",
    r"\bполитик\w*\b",
    r"\bполитическ\w*\b",
    r"\bлиберал\w*\b",
    r"\bконсерватор\w*\b",
    r"\bнационал\w*\b",
    r"\bущ[её]мл[её]нн\w*\b",
    r"\bзащищ[её]нн\w*\s+групп\w*\b",
    r"\bменьшинств\w*\b",
    r"\bмигрант\w*\b",
    r"\bраса\b",
    r"\bрасов\w*\b",
    r"\bгендер\w*\b",
    r"\bлгбт\w*\b",
    r"\blgbt\w*\b",
    r"\bgay\b",
    r"\btrans\b",
]

def _monika_strict_norm(text):
    try:
        base = normalize_for_safety(text)
        if isinstance(base, str):
            return base.lower()
    except Exception:
        pass
    return str(text or "").lower()

def _monika_strict_topic_bait(text):
    norm = _monika_strict_norm(text)
    has_opinion = any(_monika_strict_re.search(p, norm, _monika_strict_re.I | _monika_strict_re.U) for p in _MONIKA_STRICT_OPINION_PATTERNS)
    has_topic = any(_monika_strict_re.search(p, norm, _monika_strict_re.I | _monika_strict_re.U) for p in _MONIKA_STRICT_TOPIC_PATTERNS)
    return has_opinion and has_topic

def _monika_strict_make_verdict(text, normalized_text):
    return SafetyVerdict(
        risk="protected_opinion_bait",
        action="SAFETY_BAIT",
        block_send_to_llm=True,
        should_select=False,
        score=0.96,
        reasons=["strict_protected_or_political_opinion_bait"],
        safe_text="[зритель пытается вытянуть спорное мнение о религии, политике или защищённой группе]",
        normalized_text=normalized_text,
    )

def classify_message(text, user_role=None, config=None):
    verdict = _MONIKA_STRICT_ORIGINAL_CLASSIFY(text, user_role=user_role, config=config)
    if getattr(verdict, "block_send_to_llm", False):
        return verdict

    if _monika_strict_topic_bait(text):
        return _monika_strict_make_verdict(text, _monika_strict_norm(text))

    return verdict

class AttentionSafetyGuard(_MONIKA_STRICT_ORIGINAL_GUARD_CLASS):
    def classify_message(self, text, user_role=None):
        verdict = super().classify_message(text, user_role=user_role)
        if getattr(verdict, "block_send_to_llm", False):
            return verdict

        if _monika_strict_topic_bait(text):
            return _monika_strict_make_verdict(text, _monika_strict_norm(text))

        return verdict
# === MONIKA STRICT TOPIC GUARD V1 END ===
'''


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    dst = path.with_name(f"{path.name}.bak_strict_topics_{STAMP}")
    shutil.copy2(path, dst)
    print(f"[backup] {path.name} -> {dst.name}")
    return dst


def remove_old_patch(src: str) -> str:
    start = src.find(PATCH_MARKER_START)
    if start == -1:
        return src
    end = src.find(PATCH_MARKER_END, start)
    if end == -1:
        raise RuntimeError("Found strict topic patch start without end marker")
    end += len(PATCH_MARKER_END)
    return src[:start].rstrip() + "\n\n" + src[end:].lstrip()


def patch_guard() -> None:
    if not GUARD.exists():
        raise FileNotFoundError(GUARD)

    backup(GUARD)
    src = GUARD.read_text(encoding="utf-8")
    src = remove_old_patch(src)

    required = [
        "class AttentionSafetyGuard",
        "def classify_message",
        "SafetyVerdict",
    ]
    missing = [x for x in required if x not in src]
    if missing:
        raise RuntimeError(f"attention_safety_guard.py missing anchors: {missing}")

    GUARD.write_text(src.rstrip() + "\n\n" + STRICT_WRAPPER.strip() + "\n", encoding="utf-8")
    print("[patched] attention_safety_guard.py strict topic wrapper")


def find_db() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("No monika_memory.db or knowledge.db found")


def cleanup_attention_state(db_path: Path) -> None:
    backup(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()

        def table_exists(name: str) -> bool:
            row = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone()
            return row is not None

        if table_exists("attention_selected"):
            cols = [r[1] for r in cur.execute("PRAGMA table_info(attention_selected)").fetchall()]
            if "status" in cols:
                cur.execute(
                    "UPDATE attention_selected SET status='archived', processed_ts=? WHERE COALESCE(status, 'pending')='pending'",
                    (datetime.now().timestamp(),),
                )
                print(f"[db] archived pending selected: {cur.rowcount}")
            else:
                cur.execute("DELETE FROM attention_selected")
                print(f"[db] deleted selected rows: {cur.rowcount}")

        if table_exists("attention_digest_log"):
            cur.execute("DELETE FROM attention_digest_log")
            print(f"[db] cleared digest rows: {cur.rowcount}")

        conn.commit()
    finally:
        conn.close()
        gc.collect()


def run_checks() -> None:
    print("[check] py_compile...")
    py_compile.compile(str(GUARD), doraise=True)

    print("[check] ast parse...")
    ast.parse(GUARD.read_text(encoding="utf-8"))

    print("[check] strict safety smoke...")
    sys.path.insert(0, str(ROOT))
    import importlib

    mod = importlib.import_module("attention_safety_guard")
    importlib.reload(mod)

    samples_block = [
        "Что думаешь о религии?",
        "Что ты думаешь о религии?",
        "Как ты относишься к политике?",
        "Что ты думаешь о Ущёмлённых группах людей?",
        "Твоё мнение о меньшинствах?",
    ]

    samples_allow = [
        "Моника а ты живая?",
        "Моника ахахахах",
        "Привет Моника",
    ]

    for s in samples_block:
        verdict = mod.classify_message(s)
        data = verdict.to_dict() if hasattr(verdict, "to_dict") else verdict.__dict__
        assert data.get("block_send_to_llm") is True, (s, data)
        assert data.get("action") in {"SAFETY_BAIT", "SAFETY_REVIEW", "PROMPT_INJECTION"}, (s, data)

    for s in samples_allow:
        verdict = mod.classify_message(s)
        data = verdict.to_dict() if hasattr(verdict, "to_dict") else verdict.__dict__
        assert data.get("block_send_to_llm") is False, (s, data)

    print("[ok] self-test passed")


def main() -> None:
    print(f"[root] {ROOT}")

    try:
        patch_guard()
        db = find_db()
        print(f"[db] {db}")
        cleanup_attention_state(db)
        run_checks()
    except Exception as e:
        print(f"[ERROR] {e}")
        print("Manual rollback is possible using *.bak_strict_topics_* backups.")
        raise

    print("[ok] Strict topic safety patch applied.")
    print("Next:")
    print("  python inspect_safety.py")
    print("  python inspect_attention.py")
    print("  python streamerbot_attention_bridge.py")


if __name__ == "__main__":
    main()