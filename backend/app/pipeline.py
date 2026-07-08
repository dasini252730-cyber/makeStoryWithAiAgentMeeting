"""
MUSE Sprint 1 파이프라인 (FastAPI 백엔드용으로 이식)

원본: demo/sprint1_pipeline.py
- mock_* 함수는 아직 실제 Claude API 호출로 교체되지 않았다 (다음 단계 작업).
- 이 모듈은 LangGraph 그래프 정의와 초기 상태 생성만 담당하고,
  실행/스트리밍은 main.py에서 처리한다.
"""

from typing import TypedDict, List

from langgraph.graph import StateGraph, END

MAX_ROUNDS = 3


class DecisionLog(TypedDict):
    round: int
    agent: str
    decision: str
    reasoning: str


class MuseState(TypedDict):
    world: str
    draft: str
    round: int
    issues: List[str]
    decision_log: List[DecisionLog]
    status: str


def mock_story_team(state: MuseState) -> MuseState:
    draft = (
        f"[{state['world']}] 주인공은 폐허가 된 등대 앞에 섰다. "
        f"바다는 조용했지만, 그녀는 등대 안에서 불빛이 깜빡이는 것을 보았다."
    )
    state["draft"] = draft
    state["decision_log"].append({
        "round": 0,
        "agent": "StoryTeam",
        "decision": "폐등대 미스터리 오프닝 채택",
        "reasoning": "테스트 월드 설정상 '버려진 것들의 흔적'이라는 톤과 부합",
    })
    return state


def mock_review_round(state: MuseState) -> MuseState:
    round_n = state["round"] + 1
    state["round"] = round_n

    possible_issues = [
        "등대지기 캐릭터의 존재가 세계관 설정과 모순됨 (Lore Team)",
        "문장이 과거형/현재형 혼용됨 (Editing Team)",
        "감정 곡선이 너무 급격함 (Emotion Team)",
    ]
    n_issues = max(0, len(possible_issues) - round_n)
    issues = possible_issues[:n_issues]
    state["issues"] = issues

    if issues:
        fix = f"{issues[0]} 관련 수정 반영"
        state["draft"] += f" (r{round_n} 수정: {issues[0]} 해결)"
        state["decision_log"].append({
            "round": round_n,
            "agent": "EditingTeam+LoreTeam",
            "decision": fix,
            "reasoning": f"{round_n}라운드 리뷰에서 발견된 이슈 해결",
        })
        state["status"] = (
            f"라운드 초과({MAX_ROUNDS}회) - PM 강제 종료"
            if round_n >= MAX_ROUNDS else "진행 중"
        )
    else:
        state["status"] = "합의 도달 (수렴)"
        state["decision_log"].append({
            "round": round_n,
            "agent": "PM",
            "decision": "이슈 없음 - 수렴 판정",
            "reasoning": "diff 크기가 임계값 이하로 감소함",
        })

    return state


def should_continue(state: MuseState) -> str:
    if not state["issues"] or state["round"] >= MAX_ROUNDS:
        return "publish"
    return "review"


def mock_publisher(state: MuseState) -> MuseState:
    state["decision_log"].append({
        "round": state["round"],
        "agent": "Publisher",
        "decision": "최종본 조립 완료",
        "reasoning": f"종료 사유: {state['status']}",
    })
    return state


def build_graph():
    graph = StateGraph(MuseState)
    graph.add_node("story_team", mock_story_team)
    graph.add_node("review", mock_review_round)
    graph.add_node("publisher", mock_publisher)

    graph.set_entry_point("story_team")
    graph.add_edge("story_team", "review")
    graph.add_conditional_edges("review", should_continue, {
        "review": "review",
        "publish": "publisher",
    })
    graph.add_edge("publisher", END)

    return graph.compile()


app_graph = build_graph()


def make_initial_state(world: str = "테스트 월드 (Sprint 1 더미 세계관)") -> MuseState:
    return {
        "world": world,
        "draft": "",
        "round": 0,
        "issues": [],
        "decision_log": [],
        "status": "",
    }
