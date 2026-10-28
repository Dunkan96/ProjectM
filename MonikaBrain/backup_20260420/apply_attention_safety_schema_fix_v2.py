from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAG = "attention_safety_schema_fix_v2"


class PatchError(RuntimeError):
    pass


def backup(path: Path, backups: dict[Path, Path | None]) -> None:
    if path in backups:
        return
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        b = path.with_name(f"{path.name}.bak_{TAG}_{stamp}")
        shutil.copy2(path, b)
        backups[path] = b
        print(f"[backup] {path.name} -> {b.name}")
    else:
        backups[path] = None


def rollback(backups: dict[Path, Path | None]) -> None:
    print("[rollback] restoring backups...")
    for path, b in reversed(list(backups.items())):
        try:
            if b and b.exists():
                shutil.copy2(b, path)
                print(f"[rollback] {b.name} -> {path.name}")
            elif path.exists():
                path.unlink()
                print(f"[rollback] removed created {path.name}")
        except Exception as exc:
            print(f"[rollback-error] {path}: {exc}")


def replace_between(src: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    s = src.find(start_marker)
    if s < 0:
        raise PatchError(f"{label}: start marker not found")
    e = src.find(end_marker, s)
    if e < 0:
        raise PatchError(f"{label}: end marker not found")
    return src[:s] + replacement.rstrip() + "\n\n" + src[e:]


ATTENTION_INIT_REPLACEMENT = """
    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.OperationalError:
            return set()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        if column not in self._table_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def init_schema(self) -> None:
        # Create or migrate AttentionLayer tables additively.
        # CREATE TABLE IF NOT EXISTS does not update old SQLite tables.
        with self.connect() as conn:
            conn.execute(\"\"\"
                CREATE TABLE IF NOT EXISTS attention_events (
                    event_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT '',
                    user_id TEXT,
                    user_name TEXT,
                    text TEXT,
                    safe_text TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    bucket TEXT NOT NULL DEFAULT 'ignored',
                    action TEXT NOT NULL DEFAULT 'IGNORE',
                    reasons_json TEXT NOT NULL DEFAULT '[]',
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_ts REAL NOT NULL DEFAULT 0,
                    raw_json TEXT,
                    safety_json TEXT
                )
            \"\"\")
            conn.execute(\"\"\"
                CREATE TABLE IF NOT EXISTS attention_selected (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_ts REAL NOT NULL DEFAULT 0,
                    processed_ts REAL,
                    FOREIGN KEY(event_id) REFERENCES attention_events(event_id)
                )
            \"\"\")
            conn.execute(\"\"\"
                CREATE TABLE IF NOT EXISTS attention_viewer_state (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    selected_count INTEGER NOT NULL DEFAULT 0,
                    safety_count INTEGER NOT NULL DEFAULT 0,
                    last_seen_ts REAL NOT NULL DEFAULT 0,
                    last_message TEXT
                )
            \"\"\")
            conn.execute(\"\"\"
                CREATE TABLE IF NOT EXISTS attention_digest_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_ts REAL NOT NULL DEFAULT 0,
                    digest TEXT NOT NULL DEFAULT ''
                )
            \"\"\")

            for table, columns in {
                "attention_events": [
                    ("source", "TEXT NOT NULL DEFAULT ''"),
                    ("event_type", "TEXT NOT NULL DEFAULT ''"),
                    ("user_id", "TEXT"),
                    ("user_name", "TEXT"),
                    ("text", "TEXT"),
                    ("safe_text", "TEXT"),
                    ("score", "REAL NOT NULL DEFAULT 0"),
                    ("bucket", "TEXT NOT NULL DEFAULT 'ignored'"),
                    ("action", "TEXT NOT NULL DEFAULT 'IGNORE'"),
                    ("reasons_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("priority", "INTEGER NOT NULL DEFAULT 0"),
                    ("created_ts", "REAL NOT NULL DEFAULT 0"),
                    ("raw_json", "TEXT"),
                    ("safety_json", "TEXT"),
                ],
                "attention_selected": [
                    ("event_id", "TEXT"),
                    ("status", "TEXT NOT NULL DEFAULT 'pending'"),
                    ("created_ts", "REAL NOT NULL DEFAULT 0"),
                    ("processed_ts", "REAL"),
                ],
                "attention_viewer_state": [
                    ("user_name", "TEXT"),
                    ("message_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("selected_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("safety_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("last_seen_ts", "REAL NOT NULL DEFAULT 0"),
                    ("last_message", "TEXT"),
                ],
                "attention_digest_log": [
                    ("created_ts", "REAL NOT NULL DEFAULT 0"),
                    ("digest", "TEXT NOT NULL DEFAULT ''"),
                ],
            }.items():
                for column, spec in columns:
                    self._ensure_column(conn, table, column, spec)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_events_created ON attention_events(created_ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_events_bucket ON attention_events(bucket)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_selected_status ON attention_selected(status)")
            conn.commit()
"""


MODERATION_INIT_REPLACEMENT = """
    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        except sqlite3.OperationalError:
            return set()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        if column not in self._table_columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def init_schema(self) -> None:
        # Create or migrate moderation dry-run table additively.
        with self.connect() as conn:
            conn.execute(\"\"\"
                CREATE TABLE IF NOT EXISTS moderation_actions (
                    action_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    user_id TEXT,
                    user_name TEXT,
                    action TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'dry_run',
                    reason TEXT,
                    confidence REAL NOT NULL DEFAULT 0,
                    created_ts REAL NOT NULL DEFAULT 0,
                    raw_json TEXT
                )
            \"\"\")
            for column, spec in [
                ("event_id", "TEXT"),
                ("user_id", "TEXT"),
                ("user_name", "TEXT"),
                ("action", "TEXT NOT NULL DEFAULT ''"),
                ("status", "TEXT NOT NULL DEFAULT 'dry_run'"),
                ("reason", "TEXT"),
                ("confidence", "REAL NOT NULL DEFAULT 0"),
                ("created_ts", "REAL NOT NULL DEFAULT 0"),
                ("raw_json", "TEXT"),
            ]:
                self._ensure_column(conn, "moderation_actions", column, spec)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_status ON moderation_actions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_created ON moderation_actions(created_ts)")
            conn.commit()
"""


def patch_attention_layer(backups: dict[Path, Path | None]) -> None:
    path = ROOT / "attention_layer.py"
    if not path.exists():
        raise PatchError("attention_layer.py not found")
    src = path.read_text(encoding="utf-8")
    backup(path, backups)
    new = replace_between(
        src,
        "    def init_schema(self) -> None:",
        "    def _write_jsonl(self, path: Path, item: dict[str, Any]) -> None:",
        ATTENTION_INIT_REPLACEMENT,
        "attention_layer init_schema",
    )
    path.write_text(new, encoding="utf-8")
    print("[patched] attention_layer.py schema migration")


def patch_moderation_governor(backups: dict[Path, Path | None]) -> None:
    path = ROOT / "moderation_governor.py"
    if not path.exists():
        raise PatchError("moderation_governor.py not found")
    src = path.read_text(encoding="utf-8")
    backup(path, backups)
    new = replace_between(
        src,
        "    def init_schema(self) -> None:",
        "    def _write_jsonl(self, item: dict[str, Any]) -> None:",
        MODERATION_INIT_REPLACEMENT,
        "moderation_governor init_schema",
    )
    path.write_text(new, encoding="utf-8")
    print("[patched] moderation_governor.py schema migration")


def resolve_default_db_path() -> Path:
    try:
        sys.path.insert(0, str(ROOT))
        import config  # type: ignore
        for name in ("KNOWLEDGE_DB_PATH", "KNOWLEDGE_DB", "DB_PATH", "DATABASE_PATH"):
            value = getattr(config, name, None)
            if value:
                p = Path(str(value))
                return p if p.is_absolute() else ROOT / p
    except Exception:
        pass
    return ROOT / "knowledge.db"


def direct_migrate_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        b = db_path.with_name(f"{db_path.name}.bak_{TAG}_{stamp}")
        shutil.copy2(db_path, b)
        print(f"[backup] {db_path.name} -> {b.name}")
    print(f"[db] {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        def cols(table: str) -> set[str]:
            return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

        def ensure_col(table: str, column: str, spec: str) -> None:
            if column not in cols(table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
                print(f"[db add] {table}.{column}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS attention_events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT '',
                user_id TEXT,
                user_name TEXT,
                text TEXT,
                safe_text TEXT,
                score REAL NOT NULL DEFAULT 0,
                bucket TEXT NOT NULL DEFAULT 'ignored',
                action TEXT NOT NULL DEFAULT 'IGNORE',
                reasons_json TEXT NOT NULL DEFAULT '[]',
                priority INTEGER NOT NULL DEFAULT 0,
                created_ts REAL NOT NULL DEFAULT 0,
                raw_json TEXT,
                safety_json TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attention_selected (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_ts REAL NOT NULL DEFAULT 0,
                processed_ts REAL,
                FOREIGN KEY(event_id) REFERENCES attention_events(event_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attention_viewer_state (
                user_id TEXT PRIMARY KEY,
                user_name TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                selected_count INTEGER NOT NULL DEFAULT 0,
                safety_count INTEGER NOT NULL DEFAULT 0,
                last_seen_ts REAL NOT NULL DEFAULT 0,
                last_message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attention_digest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts REAL NOT NULL DEFAULT 0,
                digest TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_actions (
                action_id TEXT PRIMARY KEY,
                event_id TEXT,
                user_id TEXT,
                user_name TEXT,
                action TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'dry_run',
                reason TEXT,
                confidence REAL NOT NULL DEFAULT 0,
                created_ts REAL NOT NULL DEFAULT 0,
                raw_json TEXT
            )
        """)

        for table, pairs in {
            "attention_events": [
                ("source", "TEXT NOT NULL DEFAULT ''"), ("event_type", "TEXT NOT NULL DEFAULT ''"),
                ("user_id", "TEXT"), ("user_name", "TEXT"), ("text", "TEXT"), ("safe_text", "TEXT"),
                ("score", "REAL NOT NULL DEFAULT 0"), ("bucket", "TEXT NOT NULL DEFAULT 'ignored'"),
                ("action", "TEXT NOT NULL DEFAULT 'IGNORE'"), ("reasons_json", "TEXT NOT NULL DEFAULT '[]'"),
                ("priority", "INTEGER NOT NULL DEFAULT 0"), ("created_ts", "REAL NOT NULL DEFAULT 0"),
                ("raw_json", "TEXT"), ("safety_json", "TEXT"),
            ],
            "attention_selected": [
                ("event_id", "TEXT"), ("status", "TEXT NOT NULL DEFAULT 'pending'"),
                ("created_ts", "REAL NOT NULL DEFAULT 0"), ("processed_ts", "REAL"),
            ],
            "attention_viewer_state": [
                ("user_name", "TEXT"), ("message_count", "INTEGER NOT NULL DEFAULT 0"),
                ("selected_count", "INTEGER NOT NULL DEFAULT 0"), ("safety_count", "INTEGER NOT NULL DEFAULT 0"),
                ("last_seen_ts", "REAL NOT NULL DEFAULT 0"), ("last_message", "TEXT"),
            ],
            "attention_digest_log": [("created_ts", "REAL NOT NULL DEFAULT 0"), ("digest", "TEXT NOT NULL DEFAULT ''")],
            "moderation_actions": [
                ("event_id", "TEXT"), ("user_id", "TEXT"), ("user_name", "TEXT"),
                ("action", "TEXT NOT NULL DEFAULT ''"), ("status", "TEXT NOT NULL DEFAULT 'dry_run'"),
                ("reason", "TEXT"), ("confidence", "REAL NOT NULL DEFAULT 0"),
                ("created_ts", "REAL NOT NULL DEFAULT 0"), ("raw_json", "TEXT"),
            ],
        }.items():
            for column, spec in pairs:
                ensure_col(table, column, spec)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_events_created ON attention_events(created_ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_events_bucket ON attention_events(bucket)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_attention_selected_status ON attention_selected(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_status ON moderation_actions(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_created ON moderation_actions(created_ts)")
        conn.commit()
        print("[ok] direct db migration complete")
    finally:
        conn.close()


def run_checks() -> None:
    print("[check] py_compile...")
    for name in [
        "attention_safety_guard.py",
        "attention_layer.py",
        "moderation_governor.py",
        "streamerbot_attention_bridge.py",
        "inspect_safety.py",
        "inspect_attention.py",
        "inspect_moderation.py",
    ]:
        path = ROOT / name
        if path.exists():
            py_compile.compile(str(path), doraise=True)

    print("[check] ast parse...")
    for name in [
        "attention_layer.py",
        "moderation_governor.py",
        "inspect_safety.py",
        "inspect_attention.py",
        "inspect_moderation.py",
    ]:
        path = ROOT / name
        if path.exists():
            ast.parse(path.read_text(encoding="utf-8"))

    print("[check] inspectors...")
    for cmd in [
        [sys.executable, "inspect_safety.py"],
        [sys.executable, "inspect_attention.py"],
        [sys.executable, "inspect_moderation.py"],
    ]:
        print("[run]", " ".join(cmd))
        subprocess.run(cmd, cwd=str(ROOT), check=True)


def main() -> None:
    backups: dict[Path, Path | None] = {}
    try:
        patch_attention_layer(backups)
        patch_moderation_governor(backups)
        direct_migrate_db(resolve_default_db_path())
        run_checks()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        traceback.print_exc()
        rollback(backups)
        raise
    print("[ok] Attention Safety schema fix v2 applied.")
    print("Next:")
    print("  python streamerbot_attention_bridge.py")


if __name__ == "__main__":
    main()
