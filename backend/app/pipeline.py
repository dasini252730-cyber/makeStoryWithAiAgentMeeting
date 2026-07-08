"""
MUSE Sprint 1 파이프라인 (실제 Claude API 연동)

원본: demo/sprint1_pipeline.py의 mock_* 함수를 Claude API(Anthropic SDK) 호출로 교체.
그래프 구조(story_team -> review -> publisher -> summarize)와 종료 조건(Workflow.md)은
데모와 동일하게 유지.

Anthropic 클라이언트는 지연 생성한다 — ANTHROPIC_API_KEY가 없어도 이 모듈을 import하고
/health 등 파이프라인을 실행하지 않는 요청은 정상 동작해야 하기 때문.
"""

import json
from typing import TypedDict, List

from anthropic import Anthropic
from langgraph.graph import StateGraph, END

MAX_ROUNDS = 3
MODEL = "claude-opus-4-8"


class DecisionLog(TypedDict):
    round: int
    agent: str
    decision: str
    reasoning: str


class MuseState(TypedDict):
    world: str
    previous_summary: str
    draft: str
    round: int
    issues: List[str]
    decision_log: List[DecisionLog]
    status: str
    summary: str


_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


STORY_TEAM_SCHEMA = {
    "type": "object",
    "properties": {
        "draft": {"type": "string", "description": "장면 오프닝 초안 (한국어, 2~4문장)"},
        "decision": {"type": "string", "description": "채택한 방향을 한 줄로 요약"},
        "reasoning": {"type": "string", "description": "그 방향을 선택한 근거"},
    },
    "required": ["draft", "decision", "reasoning"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "이번 라운드에서 발견된 이슈 (세계관 모순, 문장 오류, 감정 곡선 문제 등). 없으면 빈 배열.",
        },
        "revised_draft": {"type": "string", "description": "이슈를 반영해 수정한 초안 (이슈가 없으면 입력과 동일)"},
        "decision": {"type": "string", "description": "이번 라운드의 결정 사항 한 줄 요약"},
        "reasoning": {"type": "string", "description": "그 결정의 근거"},
    },
    "required": ["issues", "revised_draft", "decision", "reasoning"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "다음 장면 작성자가 연속성을 위해 참고할 2~3문장 요약 (인물 상태, 사건, 남은 복선 위주)",
        },
    },
    "required": ["summary"],
    "additionalProperties": False,
}


def story_team(state: MuseState) -> MuseState:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": STORY_TEAM_SCHEMA},
        },
        system=(
            "당신은 MUSE 창작 조직의 Story Team입니다. "
            "주어진 세계관에 맞는 장면 오프닝 초안을 씁니다. "
            "박민규 식 유머(과장된 서사시급 진지함, 스케일 미스매치 비유, 나열식 리듬)를 "
            "살리되 장르/톤 일관성을 지키세요."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"세계관: {state['world']}\n\n"
                + (
                    f"직전 장면 요약: {state['previous_summary']}\n\n"
                    "이 요약을 이어받아 다음 장면의 오프닝을 작성해주세요."
                    if state["previous_summary"]
                    else "이 세계관에 맞는 장면 오프닝을 작성해주세요."
                )
            ),
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    state["draft"] = data["draft"]
    state["decision_log"].append({
        "round": 0,
        "agent": "StoryTeam",
        "decision": data["decision"],
        "reasoning": data["reasoning"],
    })
    return state


def review_round(state: MuseState) -> MuseState:
    round_n = state["round"] + 1
    state["round"] = round_n

    response = get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
        },
        system=(
            "당신은 MUSE 창작 조직의 Editing+Lore+Emotion Team입니다. "
            "주어진 초안을 세계관 일관성, 문장/문체, 감정 곡선 관점에서 검토하고, "
            "발견한 이슈를 구체적으로 나열한 뒤 초안을 수정하세요. "
            "문제가 없다면 issues를 빈 배열로 반환하세요."
        ),
        messages=[{
            "role": "user",
            "content": f"세계관: {state['world']}\n\n현재 초안 (라운드 {round_n}):\n{state['draft']}",
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    state["issues"] = data["issues"]

    if data["issues"]:
        state["draft"] = data["revised_draft"]
        state["decision_log"].append({
            "round": round_n,
            "agent": "EditingTeam+LoreTeam",
            "decision": data["decision"],
            "reasoning": data["reasoning"],
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
            "decision": data["decision"],
            "reasoning": data["reasoning"],
        })

    return state


def summarize(state: MuseState) -> MuseState:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=512,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA},
        },
        system=(
            "당신은 MUSE 창작 조직의 연속성 담당자입니다. "
            "완성된 장면을 다음 장면 작성자가 참고할 수 있도록 간결하게 요약하세요."
        ),
        messages=[{
            "role": "user",
            "content": f"완성된 장면:\n{state['draft']}",
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    state["summary"] = data["summary"]
    state["decision_log"].append({
        "round": state["round"],
        "agent": "ContinuityTeam",
        "decision": "장면 요약 생성 완료 (DB 반영 대기)",
        "reasoning": "다음 장면 생성 시 연속성 확보를 위해 요약이 필요함 (Architecture.md 9단계)",
    })
    return state


def should_continue(state: MuseState) -> str:
    if not state["issues"] or state["round"] >= MAX_ROUNDS:
        return "publish"
    return "review"


def publisher(state: MuseState) -> MuseState:
    state["decision_log"].append({
        "round": state["round"],
        "agent": "Publisher",
        "decision": "최종본 조립 완료",
        "reasoning": f"종료 사유: {state['status']}",
    })
    return state


def build_graph():
    graph = StateGraph(MuseState)
    graph.add_node("story_team", story_team)
    graph.add_node("review", review_round)
    graph.add_node("publisher", publisher)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("story_team")
    graph.add_edge("story_team", "review")
    graph.add_conditional_edges("review", should_continue, {
        "review": "review",
        "publish": "publisher",
    })
    graph.add_edge("publisher", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


app_graph = build_graph()


def make_initial_state(
    world: str = "테스트 월드 (Sprint 1 더미 세계관)", previous_summary: str = ""
) -> MuseState:
    return {
        "world": world,
        "previous_summary": previous_summary,
        "draft": "",
        "round": 0,
        "issues": [],
        "decision_log": [],
        "status": "",
        "summary": "",
    }
