"""
MUSE 연속성 저장소 (SQLite)

ADR-002: 정형 데이터(장면/캐릭터/세계관 상태)는 SQLite에 저장.
장면 하나가 끝나면 요약을 저장하고, 같은 세계관의 다음 장면을 생성할 때
가장 최근 장면 요약을 불러와 story_team 프롬프트에 주입한다 (Architecture.md 0단계/9단계).

Arc Team(신설)이 만든 전체 화 로드맵도 여기 저장한다 — 최초 1회 설계 후,
매 화 실행 시 해당 화 번호의 설계를 불러와 Story Team에 주입한다.
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
    try:
        conn.execute("ALTER TABLE scenes ADD COLUMN episode_number INTEGER")
    except sqlite3.OperationalError:
        pass  # 이미 있는 배포에서는 컬럼이 이미 존재함

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arcs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            world TEXT NOT NULL,
            episode_count INTEGER NOT NULL,
            series_summary TEXT NOT NULL,
            episodes TEXT NOT NULL,
            pitch_to_ceo TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    try:
        conn.execute("ALTER TABLE arcs ADD COLUMN pitch_to_ceo TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 이미 있는 배포에서는 컬럼이 이미 존재함

    conn.commit()
    conn.close()


def get_latest_scene(world: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM scenes WHERE world = ? ORDER BY id DESC LIMIT 1", (world,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_scenes(world: str) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM scenes WHERE world = ?", (world,)
    ).fetchone()
    conn.close()
    return row["c"]


def save_scene(
    world: str,
    final_draft: str,
    summary: str,
    decision_log: list,
    status: str,
    episode_number: Optional[int] = None,
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO scenes (world, final_draft, summary, decision_log, status, episode_number) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            world,
            final_draft,
            summary,
            json.dumps(decision_log, ensure_ascii=False),
            status,
            episode_number,
        ),
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


def save_arc(
    world: str,
    episode_count: int,
    series_summary: str,
    episodes: list,
    pitch_to_ceo: str = "",
) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO arcs (world, episode_count, series_summary, episodes, pitch_to_ceo) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            world,
            episode_count,
            series_summary,
            json.dumps(episodes, ensure_ascii=False),
            pitch_to_ceo,
        ),
    )
    conn.commit()
    arc_id = cur.lastrowid
    conn.close()
    return arc_id


def get_arc(world: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM arcs WHERE world = ? ORDER BY id DESC LIMIT 1", (world,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    data = dict(row)
    data["episodes"] = json.loads(data["episodes"])
    return data
