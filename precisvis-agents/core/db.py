"""Base SQLite : journal de chaque action, coûts, créas, posts, éléments « À traiter »."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,           -- ok | error | skipped | simulated
    result TEXT,                    -- JSON
    cost_eur REAL DEFAULT 0,
    error TEXT,
    dry_run INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_actions_day ON actions(day, agent);

CREATE TABLE IF NOT EXISTS costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    agent TEXT NOT NULL,
    provider TEXT NOT NULL,         -- claude | fal | sume | ...
    kind TEXT NOT NULL,             -- llm | image | video
    amount_eur REAL NOT NULL,
    dry_run INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_costs_day ON costs(day);

CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    day TEXT NOT NULL,
    agent TEXT NOT NULL,
    phase TEXT NOT NULL,            -- morning | publish | evening
    status TEXT NOT NULL,           -- ok | failed | skipped
    attempts INTEGER DEFAULT 1,
    bullets TEXT,                   -- JSON list de phrases pour le bilan
    data TEXT,                      -- JSON
    error TEXT,
    started TEXT,
    finished TEXT,
    dry_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS creatives (
    id TEXT PRIMARY KEY,            -- ex. 2026-11-24-c03
    day TEXT NOT NULL,
    concept TEXT NOT NULL,          -- type de créa
    angle TEXT,
    headline TEXT,
    kind TEXT NOT NULL,             -- image | video
    master_path TEXT,
    files TEXT,                     -- JSON {"facebook/1x1": "path", ...}
    prompt TEXT,
    model TEXT,
    cost_eur REAL DEFAULT 0,
    score REAL,
    attempts INTEGER DEFAULT 1,
    status TEXT NOT NULL,           -- ok | rejected
    rejection_reason TEXT,
    parent_id TEXT,                 -- variante d'une créa gagnante
    dry_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS copies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creative_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    variant TEXT NOT NULL,          -- A | B | C
    hook TEXT, body TEXT, title TEXT, cta TEXT, hashtags TEXT,
    day TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    creative_id TEXT NOT NULL,
    platform TEXT NOT NULL,         -- facebook | instagram | tiktok
    placement TEXT NOT NULL,        -- feed | reel | video | photo
    copy_id INTEGER,
    caption TEXT,
    media_path TEXT,
    media_url TEXT,                 -- URL publique (Shopify Files) : les runs GitHub n'ont pas de disque partagé
    scheduled_at TEXT NOT NULL,     -- ISO, heure de Paris
    status TEXT NOT NULL,           -- queued | published | failed | cancelled
    external_id TEXT,
    permalink TEXT,
    published_at TEXT,
    error TEXT,
    metrics TEXT,                   -- JSON {views, likes, comments, shares, saves, clicks}
    metrics_updated TEXT,
    dry_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS todo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    category TEXT NOT NULL,         -- remboursement | litige | erreur | produit_brouillon | validation | info
    title TEXT NOT NULL,
    details TEXT,
    ref TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created TEXT NOT NULL,
    dry_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    source TEXT NOT NULL,           -- agent émetteur
    topic TEXT NOT NULL,            -- angles | winners | ...
    payload TEXT NOT NULL,          -- JSON
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics_daily (
    day TEXT PRIMARY KEY,
    payload TEXT NOT NULL,          -- JSON
    dry_run INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- bas niveau -----------------------------------------------------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, tuple(params))
        self.conn.commit()
        return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        row = self.conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def insert(self, table: str, row: dict[str, Any]) -> int:
        row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in row.items()}
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", row.values())
        return int(cur.lastrowid or 0)

    def update(self, table: str, key: str, key_value: Any, values: dict[str, Any]) -> None:
        values = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in values.items()}
        sets = ", ".join(f"{k} = ?" for k in values)
        self.execute(f"UPDATE {table} SET {sets} WHERE {key} = ?", [*values.values(), key_value])

    # -- haut niveau ----------------------------------------------------
    def log_action(self, *, day: str, run_id: str, agent: str, action: str, status: str = "ok",
                   result: Any = None, cost_eur: float = 0.0, error: str | None = None, dry_run: bool = False) -> None:
        self.insert("actions", {
            "ts": now_iso(), "day": day, "run_id": run_id, "agent": agent, "action": action,
            "status": status, "result": json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
            "cost_eur": round(cost_eur, 4), "error": error, "dry_run": int(dry_run),
        })

    def add_cost(self, *, day: str, agent: str, provider: str, kind: str, amount_eur: float, dry_run: bool) -> None:
        self.insert("costs", {"ts": now_iso(), "day": day, "agent": agent, "provider": provider,
                              "kind": kind, "amount_eur": round(amount_eur, 4), "dry_run": int(dry_run)})

    def cost_total(self, day_prefix: str) -> float:
        row = self.one("SELECT COALESCE(SUM(amount_eur), 0) AS s FROM costs WHERE day LIKE ?", [day_prefix + "%"])
        return float(row["s"]) if row else 0.0

    def costs_by_kind(self, day: str) -> dict[str, float]:
        rows = self.query("SELECT provider, kind, SUM(amount_eur) AS s FROM costs WHERE day = ? GROUP BY provider, kind", [day])
        return {f"{r['provider']}:{r['kind']}": round(r["s"], 4) for r in rows}

    def add_todo(self, *, day: str, category: str, title: str, details: str = "", ref: str = "", dry_run: bool = False) -> None:
        exists = self.one("SELECT id FROM todo WHERE ref = ? AND ref != '' AND status = 'open'", [ref]) if ref else None
        if exists:
            return
        self.insert("todo", {"day": day, "category": category, "title": title, "details": details, "ref": ref,
                             "status": "open", "created": now_iso(), "dry_run": int(dry_run)})

    def open_todos(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM todo WHERE status = 'open' ORDER BY category, id")

    def publish_insight(self, *, day: str, source: str, topic: str, payload: Any) -> None:
        self.insert("insights", {"day": day, "source": source, "topic": topic,
                                 "payload": json.dumps(payload, ensure_ascii=False), "created": now_iso()})

    def latest_insight(self, topic: str) -> Any:
        row = self.one("SELECT payload FROM insights WHERE topic = ? ORDER BY id DESC LIMIT 1", [topic])
        return json.loads(row["payload"]) if row else None

    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM kv WHERE key = ?", [key])
        return json.loads(row["value"]) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        self.insert("kv", {"key": key, "value": json.dumps(value, ensure_ascii=False, default=str), "updated": now_iso()})
