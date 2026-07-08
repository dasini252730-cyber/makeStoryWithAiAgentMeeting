"""
MUSE 회의실 백엔드 API

- /health                    : 헬스체크
- /pipeline/start (POST)     : 파이프라인 실행을 백그라운드 스레드로 시작하고 run_id 반환.
                                같은 world의 직전 장면 요약을 SQLite에서 불러와 연속성을 유지하고,
                                완료되면 결과를 SQLite에 저장한다 (Architecture.md 0단계/9단계).
- /pipeline/stream/{run_id}  : run의 진행 상황을 SSE로 스트리밍. `since` 커서로 이어받을 수 있어
                                호스팅 프록시가 긴 연결을 끊어도(Render 무료 티어 등) 클라이언트가
                                재연결하며 이어볼 수 있다.
- /scenes                    : 저장된 장면 목록 조회 (world로 필터 가능)
- /arc/start (POST)          : Arc Team의 전체 화 로드맵 설계를 백그라운드 스레드로 시작하고 run_id 반환.
                                50화 분량 설계는 응답까지 오래 걸릴 수 있어(고효율 사고 모드),
                                /pipeline/stream과 같은 run_id 기반 SSE로 결과를 받는다.
- /arc                       : 저장된 로드맵과 다음에 생성할 화 번호 조회.
"""

import json
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .db import (
    count_scenes,
    get_arc,
    get_latest_scene,
    init_db,
    list_scenes,
    save_arc,
    save_scene,
)
from .pipeline import app_graph, generate_arc, make_initial_state
from .runs import append_event, create_run, get_events_since, mark_done

app = FastAPI(title="MUSE Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.get("/")
def root():
    # Render 등 호스팅의 기본 헬스체크가 "/"를 때리는 경우가 있다. 라우트가 없어
    # 404가 나면 정상 서비스도 비정상으로 판단해 재시작시킬 수 있으므로 둔다.
    return {"status": "ok", "service": "muse-backend"}


@app.get("/health")
def health():
    return {"status": "ok"}


def _episode_plan_text(world: str, episode_number: int) -> str:
    arc = get_arc(world)
    if not arc:
        return ""
    for ep in arc["episodes"]:
        if ep["episode_number"] == episode_number:
            return (
                f"{episode_number}화 목적: {ep['purpose']}\n"
                f"등장인물: {', '.join(ep['characters'])}\n"
                f"새로 심는 복선: {', '.join(ep['foreshadowing_plant']) or '없음'}\n"
                f"회수하는 복선: {', '.join(ep['foreshadowing_payoff']) or '없음'}"
            )
    return ""


def _execute_pipeline(run_id: str, world: str) -> None:
    try:
        episode_number = count_scenes(world) + 1
        episode_plan = _episode_plan_text(world, episode_number)

        previous = get_latest_scene(world)
        previous_summary = previous["summary"] if previous else ""
        state = make_initial_state(
            world, previous_summary=previous_summary, episode_plan=episode_plan
        )

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
            episode_number=episode_number,
        )
        append_event(
            run_id,
            {"node": "db_saved", "scene_id": scene_id, "episode_number": episode_number},
        )
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


def _execute_arc(run_id: str, world: str, episode_count: int) -> None:
    try:
        result = generate_arc(world, episode_count)
        arc_id = save_arc(
            world=world,
            episode_count=episode_count,
            series_summary=result["series_summary"],
            episodes=result["episodes"],
            pitch_to_ceo=result["pitch_to_ceo"],
        )
        append_event(
            run_id,
            {
                "node": "arc_saved",
                "arc_id": arc_id,
                "world": world,
                "episode_count": episode_count,
                "series_summary": result["series_summary"],
                "episodes": result["episodes"],
                "pitch_to_ceo": result["pitch_to_ceo"],
            },
        )
        mark_done(run_id)
    except Exception as exc:  # noqa: BLE001 — 백그라운드 스레드라 예외를 이벤트로 전달해야 함
        mark_done(run_id, error=str(exc))


@app.post("/arc/start")
def start_arc(world: str, episode_count: int):
    run_id = create_run()
    threading.Thread(
        target=_execute_arc, args=(run_id, world, episode_count), daemon=True
    ).start()
    return {"run_id": run_id}


@app.get("/arc")
def read_arc(world: str):
    return {"arc": get_arc(world), "next_episode": count_scenes(world) + 1}
