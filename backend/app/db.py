"""
MUSE 연속성 저장소 (SQLite)

ADR-002: 정형 데이터(장면/캐릭터/세계관 상태)는 SQLite에 저장.
장면 하나가 끝나면 요약을 저장하고, 같은 세계관의 다음 장면을 생성할 때
가장 최근 장면 요약을 불러와 story_team 프롬프트에 주입한다 (Architecture.md 0단계/9단계).
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get(
    "MUSE_DB_PATH", str(Path(__file__).resolve().parent.parent / "muse.db")
)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world TEXT NOT NULL,
            final_draft TEXT NOT NULL,
            summary TEXT NOT NULL,
            decision_log TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def get_latest_scene(world: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM scenes WHERE world = ? ORDER BY id DESC LIMIT 1", (world,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def save_scene(
    world: str, final_draft: str, summary: str, decision_log: list, status: str
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO scenes (world, final_draft, summary, decision_log, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (world, final_draft, summary, json.dumps(decision_log, ensure_ascii=False), status),
    )
    conn.commit()
    scene_id = cur.lastrowid
    conn.close()
    return scene_id


def list_scenes(world: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    if world:
        rows = conn.execute(
            "SELECT * FROM scenes WHERE world = ? ORDER BY id ASC", (world,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM scenes ORDER BY id ASC").fetchall()
    conn.close()
    return [
        {**dict(r), "decision_log": json.loads(r["decision_log"])} for r in rows
    ]
