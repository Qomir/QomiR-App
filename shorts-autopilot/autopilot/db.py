"""État persistant en SQLite (data/autopilot.db) : vidéos, publications, stats, bandit."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .config import DATA_DIR

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY, created_at TEXT, status TEXT, mode TEXT,
    topic_title TEXT, topic_url TEXT, topic_key TEXT, category TEXT,
    format TEXT, hook_style TEXT, template TEXT, voice TEXT, slot TEXT,
    title TEXT, script_json TEXT, path TEXT, duration REAL,
    scheduled_at TEXT, qc_json TEXT, approval TEXT DEFAULT 'pending', error TEXT
);
CREATE TABLE IF NOT EXISTS posts (
    video_id TEXT, platform TEXT, remote_id TEXT, url TEXT, published_at TEXT,
    status TEXT, error TEXT, PRIMARY KEY (video_id, platform)
);
CREATE TABLE IF NOT EXISTS stats (
    video_id TEXT, platform TEXT, fetched_at TEXT, views INTEGER, likes INTEGER,
    comments INTEGER, shares INTEGER, avg_view_pct REAL, avg_view_sec REAL,
    PRIMARY KEY (video_id, platform)
);
CREATE TABLE IF NOT EXISTS arms (
    dimension TEXT, value TEXT, n INTEGER, mean REAL, PRIMARY KEY (dimension, value)
);
CREATE TABLE IF NOT EXISTS used_assets (asset_id TEXT PRIMARY KEY, used_at TEXT);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DATA_DIR / "autopilot.db", check_same_thread=False,
                                    isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def execute(sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
    with _lock:
        return conn().execute(sql, params)


def query(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchall()


def insert_video(row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join(f":{k}" for k in row)
    execute(f"INSERT OR REPLACE INTO videos ({cols}) VALUES ({marks})", row)


def update_video(video_id: str, **fields) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    execute(f"UPDATE videos SET {sets} WHERE id = :id", {**fields, "id": video_id})


def kv_get(key: str, default=None):
    rows = query("SELECT value FROM kv WHERE key = ?", (key,))
    return json.loads(rows[0]["value"]) if rows else default


def kv_set(key: str, value) -> None:
    execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, json.dumps(value)))
