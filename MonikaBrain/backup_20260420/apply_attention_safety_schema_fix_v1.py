from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "knowledge.db"


def backup_db(path: Path) -> Path | None:
    if not path.exists():
        print(f"[warn] DB not found yet: {path}")
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_attention_safety_schema_fix_{stamp}")
    shutil.copy2(path, backup)
    print(f"[backup] {path.name} -> {backup.name}")
    return backup


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def add_column(conn: sqlite3.Connection, table: str, name: str, decl: str) -> bool:
    if not table_exists(conn, table):
        print(f"[skip] table missing: {table}")
        return False
    existing = columns(conn, table)
    if name in existing:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    print(f"[migrated] {table}.{name} {decl}")
    return True


def migrate_schema(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"knowledge DB not found: {path}")

    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=OFF")

        # Existing v1b tables may lack the new safety/status columns.
        # Additions are intentionally additive only; no data is deleted.
        plan: dict[str, list[tuple[str, str]]] = {
            "attention_events": [
                ("status", "TEXT DEFAULT 'new'"),
                ("safety_risk", "TEXT DEFAULT 'ok'"),
                ("safety_action", "TEXT DEFAULT 'OK'"),
                ("safe_text", "TEXT DEFAULT ''"),
                ("block_send_to_llm", "INTEGER DEFAULT 0"),
                ("processed_ts", "REAL DEFAULT 0"),
                ("updated_ts", "REAL DEFAULT 0"),
                ("raw_json", "TEXT DEFAULT '{}'"),
            ],
            "attention_selected": [
                ("status", "TEXT DEFAULT 'pending'"),
                ("selected_ts", "REAL DEFAULT 0"),
                ("processed_ts", "REAL DEFAULT 0"),
                ("safe_text", "TEXT DEFAULT ''"),
                ("safety_risk", "TEXT DEFAULT 'ok'"),
                ("safety_action", "TEXT DEFAULT 'OK'"),
                ("block_send_to_llm", "INTEGER DEFAULT 0"),
                ("raw_json", "TEXT DEFAULT '{}'"),
            ],
            "attention_digest_log": [
                ("status", "TEXT DEFAULT 'active'"),
                ("safe_text", "TEXT DEFAULT ''"),
                ("safety_risk", "TEXT DEFAULT 'ok'"),
                ("created_ts", "REAL DEFAULT 0"),
            ],
            "attention_viewer_state": [
                ("status", "TEXT DEFAULT 'active'"),
                ("safety_score", "REAL DEFAULT 0"),
                ("updated_ts", "REAL DEFAULT 0"),
            ],
            "moderation_actions": [
                ("status", "TEXT DEFAULT 'dry_run'"),
                ("safe_text", "TEXT DEFAULT ''"),
                ("safety_risk", "TEXT DEFAULT ''"),
                ("safety_action", "TEXT DEFAULT ''"),
                ("source_event_id", "TEXT DEFAULT ''"),
                ("raw_text", "TEXT DEFAULT ''"),
                ("raw_json", "TEXT DEFAULT '{}'"),
                ("details_json", "TEXT DEFAULT '{}'"),
                ("created_ts", "REAL DEFAULT 0"),
                ("updated_ts", "REAL DEFAULT 0"),
                ("user_id", "TEXT DEFAULT ''"),
                ("user_name", "TEXT DEFAULT ''"),
                ("action", "TEXT DEFAULT ''"),
                ("reason", "TEXT DEFAULT ''"),
            ],
        }

        changed = 0
        for table, cols in plan.items():
            for name, decl in cols:
                if add_column(conn, table, name, decl):
                    changed += 1

        # Normalize old selected rows to pending so inspect/runtime can handle them.
        if table_exists(conn, "attention_selected") and "status" in columns(conn, "attention_selected"):
            conn.execute(
                "UPDATE attention_selected SET status='pending' "
                "WHERE status IS NULL OR TRIM(status)=''"
            )

        if table_exists(conn, "moderation_actions") and "status" in columns(conn, "moderation_actions"):
            conn.execute(
                "UPDATE moderation_actions SET status='dry_run' "
                "WHERE status IS NULL OR TRIM(status)=''"
            )

        conn.commit()
        print(f"[ok] schema migration complete; columns added: {changed}")
    finally:
        conn.close()


def run_check(cmd: list[str]) -> None:
    print("[check]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    print(f"[root] {ROOT}")
    print(f"[db]   {DB_PATH}")

    backup_db(DB_PATH)
    migrate_schema(DB_PATH)

    # Now the upgraded modules should initialize against the existing DB.
    try:
        run_check([sys.executable, "inspect_safety.py"])
        run_check([sys.executable, "inspect_attention.py"])
        run_check([sys.executable, "inspect_moderation.py"])
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] check failed: {e}")
        print("DB backup was created above. The migration is additive, but send this output if a check still fails.")
        raise

    print("[ok] Attention Safety schema fix applied.")
    print("Next:")
    print("  python streamerbot_attention_bridge.py")


if __name__ == "__main__":
    main()
