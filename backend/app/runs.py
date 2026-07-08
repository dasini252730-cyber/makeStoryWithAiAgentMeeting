"""
백그라운드로 실행되는 파이프라인 run의 이벤트 버퍼.

파이프라인 실행 자체는 별도 스레드에서 돌고, 여기 버퍼에 이벤트를 쌍는다.
클라이언트는 짧은 SSE 연결으로 붙었다 끔고젌연결하며 `since` 커서로 이어받는다 —
Render 같은 호스팅이 긴 연결을 중간에 끓어도(무료 티어에서 흔함) 재연결으로 복구되게 하기 위함.
"""

import threading
import uuid
from typing import Dict, List, Optional, Tuple

_lock = threading.Lock()
_runs: Dict[str, dict] = {}


def create_run() -> str:
    run_id = uuid.uuid4().hex
    with _lock:
        _runs[run_id] = {"events": [], "done": False, "error": None}
    return run_id


def append_event(run_id: str, event: dict) -> None:
    with _lock:
        _runs[run_id]["events"].append(event)


def mark_done(run_id: str, error: Optional[str] = None) -> None:
    with _lock:
        _runs[run_id]["done"] = True
        _runs[run_id]["error"] = error


def get_events_since(run_id: str, since: int) -> Tuple[List[dict], bool, Optional[str]]:
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            return [], True, "run_id를 찾을 수 없습니다 (서버가 재시작될 수 있습니다)."
        return list(run["events"][since:]), run["done"], run["error"]
