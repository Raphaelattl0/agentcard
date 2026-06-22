"""
Persistent storage layer using SQLite — replaces the in-memory dicts so
tenant data, keys, and call counts survive restarts/deploys.
"""
from __future__ import annotations
import sqlite3
import json
import os
import time
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.environ.get("AGENTCARD_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agentcard.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            slug TEXT PRIMARY KEY,
            card_json TEXT NOT NULL,
            operation_map_json TEXT NOT NULL,
            upstream_base_url TEXT NOT NULL,
            upstream_auth_header_json TEXT NOT NULL,
            public_key_jwk_json TEXT NOT NULL,
            private_key_pem TEXT NOT NULL,
            key_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            task_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            email TEXT PRIMARY KEY,
            joined_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_db()


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_tenant(slug: str, data: dict[str, Any], private_key_pem: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO tenants
               (slug, card_json, operation_map_json, upstream_base_url,
                upstream_auth_header_json, public_key_jwk_json, private_key_pem,
                key_id, created_at, call_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slug,
                json.dumps(data["card"].model_dump(exclude_none=True)),
                json.dumps(data["operation_map"]),
                data["upstream_base_url"],
                json.dumps(data["upstream_auth_header"]),
                json.dumps(data["public_key_jwk"]),
                private_key_pem,
                data["key_id"],
                data["created_at"],
                data.get("call_count", 0),
            ),
        )


def load_tenant_raw(slug: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        return dict(row)


def tenant_exists(slug: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM tenants WHERE slug = ?", (slug,)).fetchone()
        return row is not None


def increment_call_count(slug: str) -> None:
    with _get_conn() as conn:
        conn.execute("UPDATE tenants SET call_count = call_count + 1 WHERE slug = ?", (slug,))


def list_all_tenants() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT slug, call_count, created_at, card_json FROM tenants").fetchall()
        return [dict(r) for r in rows]


def save_task(task_id: str, task_json: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tasks (id, task_json, created_at) VALUES (?, ?, ?)",
            (task_id, json.dumps(task_json), time.time()),
        )


def load_task(task_id: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT task_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["task_json"])


def add_waitlist_email(email: str) -> bool:
    """Returns True if newly added, False if already existed."""
    with _get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM waitlist WHERE email = ?", (email,)).fetchone()
        if existing:
            return False
        conn.execute("INSERT INTO waitlist (email, joined_at) VALUES (?, ?)", (email, time.time()))
        return True
