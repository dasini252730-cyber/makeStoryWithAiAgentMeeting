"""
MUSE 회의실 백엔드 API

- /health          : 헬스체크
- /pipeline/run     : 파이프라인 1회 실행, 노드별 진행 상황을 SSE로 스트리밍.
                      같은 world의 직전 장면 요약을 SQLite에서 불러와 연속성을 유지하고,
                      완료되면 결과를 SQLite에 저장한다 (Architecture.md 0단계/9단계).
- /scenes          : 저장된 장면 목록 조회 (world로 필터 가능)
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .db import get_latest_scene, init_db, list_scenes, save_scene
from .pipeline import app_graph, make_initial_state

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


@app.get("/pipeline/run")
def run_pipeline(world: str = "테스트 월드 (Sprint 1 더미 세계관)"):
    def event_stream():
        previous = get_latest_scene(world)
        previous_summary = previous["summary"] if previous else ""
        state = make_initial_state(world, previous_summary=previous_summary)

        final_state = state
        for step in app_graph.stream(state):
            node_name, node_state = next(iter(step.items()))
            final_state = node_state
            payload = {"node": node_name, "state": node_state}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        scene_id = save_scene(
            world=world,
            final_draft=final_state["draft"],
            summary=final_state["summary"],
            decision_log=final_state["decision_log"],
            status=final_state["status"],
        )
        yield f"data: {json.dumps({'node': 'db_saved', 'scene_id': scene_id}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/scenes")
def get_scenes(world: str | None = None):
    return {"scenes": list_scenes(world)}
