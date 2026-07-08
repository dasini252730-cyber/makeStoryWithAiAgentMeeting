"""
MUSE 회의실 백엔드 API

- /health                    : 헬스체크
- /pipeline/start (POST)     : 파이프라인 실행을 백그라운드 스레드로 시작하고 run_id 반환.
                                같은 world의 직전 장면 요약을 SQLite에서 불러와 연속성을 유지하고,
                                완료되면 결과를 SQLite에 저장한다 (Architecture.md 0단계/9단계).
- /pipeline/stream/{run_id}  : run의 진행 상황을 SSE로 스트리밍. `since` 커서로 이어받을 수 있어
                                호스팅 프록시가 긴 연결을 끓어도(Render 무료 티어 등) 클라이언트가
                                재연결하며 이어볼 수 있다.
- /scenes                    : 저장된 장면 목록 조회 (world로 필터 가능)
"""

import json
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .db import get_latest_scene, init_db, list_scenes, save_scene
from .pipeline import app_graph, make_initial_state
from .runs import append_event, create_run, get_events_since, mark_done

app = FastAPI(title="MUSE Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


def _execute_pipeline(run_id: str, world: str) -> None:
    try:
        previous = get_latest_scene(world)
        previous_summary = previous["summary"] if previous else ""
        state = make_initial_state(world, previous_summary=previous_summary)

        final_state = state
        for step in app_graph.stream(state):
            node_name, node_state = next(iter(step.items()))
            final_state = node_state
            append_event(run_id, {"node": node_name, "state": node_state})

        scene_id = save_scene(
            world=world,
            final_draft=final_state["draft"],
            summary=final_state["summary"],
            decision_log=final_state["decision_log"],
            status=final_state["status"],
        )
        append_event(run_id, {"node": "db_saved", "scene_id": scene_id})
        mark_done(run_id)
    except Exception as exc:  # noqa: BLE001 — 백그라운드 스레드라 예외를 이벤트로 전달해야 함
        mark_done(run_id, error=str(exc))


@app.post("/pipeline/start")
def start_pipeline(world: str = "테스트 월드 (Sprint 1 더미 세계관)"):
    run_id = create_run()
    threading.Thread(target=_execute_pipeline, args=(run_id, world), daemon=True).start()
    return {"run_id": run_id}


@app.get("/pipeline/stream/{run_id}")
def stream_pipeline(run_id: str, since: int = 0):
    def event_stream():
        cursor = since
        while True:
            events, done, error = get_events_since(run_id, cursor)
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                cursor += 1

            if done:
                if error:
                    payload = {"node": "error", "message": error}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
                return

            yield ": heartbeat\n\n"
            time.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/scenes")
def get_scenes(world: str | None = None):
    return {"scenes": list_scenes(world)}
