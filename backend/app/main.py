"""
MUSE 회의실 백엔드 API

- /health          : 헬스체크
- /pipeline/run     : 파이프라인 1회 실행, 노드별 진행 상황을 SSE로 스트리밍

지금은 pipeline.py의 mock_* 함수를 그대로 사용한다 (실제 Claude API 호출은 다음 단계).
프론트엔드 없이 curl로 먼저 검증하는 것이 목적이므로 최소 구성만 둔다.
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .pipeline import app_graph, make_initial_state

app = FastAPI(title="MUSE Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pipeline/run")
def run_pipeline(world: str = "테스트 월드 (Sprint 1 더미 세계관)"):
    def event_stream():
        state = make_initial_state(world)
        for step in app_graph.stream(state):
            node_name, node_state = next(iter(step.items()))
            payload = {"node": node_name, "state": node_state}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
