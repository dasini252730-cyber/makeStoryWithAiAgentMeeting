"""
MUSE Sprint 1 데모 파이프라인
- 실제 Claude API 호출 대신 목업(mock) 함수로 각 Agent를 흉내낸다.
- 목적: LangGraph 그래프 구조 + 비판 라운드 종료 조건(Workflow.md)이
        실제로 어떻게 도는지 눈으로 확인하는 것.
- Claude Code로 넘어가면 mock_* 함수들만 실제 API 호출로 교체하면 된다.
"""

from typing import TypedDict, List
from langgraph.graph import StateGraph, END
import random
import json

random.seed(7)

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


# ---------- 목업 Agent 함수 (나중에 실제 Claude API 호출로 교체) ----------

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

    # 라운드가 진행될수록 문제가 줄어드는 것처럼 시뮬레이션 (수렴 시나리오)
    possible_issues = [
        "등대지기 캐릭터의 존재가 세계관 설정과 모순됨 (Lore Team)",
        "문장이 과거형/현재형 혼용됨 (Editing Team)",
        "감정 곡선이 너무 급격함 (Emotion Team)",
    ]
    n_issues = max(0, len(possible_issues) - round_n)  # 라운드마다 이슈 감소
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
    # Workflow.md의 3중 안전장치 중 2개를 여기서 시연:
    # 1) 최대 라운드 제한  2) 수렴 판정(이슈 없음)
    # (라우팅 함수는 상태를 변경하지 않는다 - LangGraph에서 상태 변경은
    #  노드에서만 하고, 라우팅 함수는 순수하게 다음 경로만 결정해야
    #  변경사항이 유실되지 않는다)
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


# ---------- LangGraph 그래프 정의 ----------

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

app = graph.compile()

# ---------- 실행 ----------

initial_state: MuseState = {
    "world": "테스트 월드 (Sprint 1 더미 세계관)",
    "draft": "",
    "round": 0,
    "issues": [],
    "decision_log": [],
    "status": "",
}

result = app.invoke(initial_state)

print("=" * 60)
print("최종 챕터 초안")
print("=" * 60)
print(result["draft"])
print()
print("=" * 60)
print(f"종료 상태: {result['status']} (총 {result['round']}라운드)")
print("=" * 60)
print()
print("Decision Log (No Magic 원칙):")
for entry in result["decision_log"]:
    print(json.dumps(entry, ensure_ascii=False))
