"""
MUSE Sprint 1 파이프라인 (실제 Claude API 연동, 팀별 개별 의견 + PM 조율)

원본: demo/sprint1_pipeline.py의 mock_* 함수를 Claude API(Anthropic SDK) 호출로 교체.
review 단계는 Editing/Lore/Emotion Team이 각각 독립적으로 의견을 내고, PM이 세 팀의
의견(충돌 포함)을 조율해 반영 여부를 결정하는 구조로 확장했다 — Workflow.md의
"토론-비판-수정 루프" 취지를 살려, 결과만이 아니라 각 팀의 개별 발언이 보이도록 함.

Anthropic 클라이언트는 지연 생성한다 — ANTHROPIC_API_KEY가 없어도 이 모듈을 import하고
/health 등 파이프라인을 실행하지 않는 요청은 정상 동작해야 하기 때문.
"""

import json
from typing import Dict, TypedDict, List

from anthropic import Anthropic
from langgraph.graph import StateGraph, END

MAX_ROUNDS = 3
MODEL = "claude-opus-4-8"


class DecisionLog(TypedDict):
    round: int
    agent: str
    decision: str
    reasoning: str


class TeamOpinion(TypedDict):
    has_issue: bool
    decision: str
    reasoning: str


class MuseState(TypedDict):
    world: str
    previous_summary: str
    draft: str
    round: int
    issues: List[str]
    current_opinions: Dict[str, TeamOpinion]
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

TEAM_OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "has_issue": {
            "type": "boolean",
            "description": "이 팀의 관점에서 반영이 필요한 문제가 있는지",
        },
        "decision": {"type": "string", "description": "이 팀의 의견을 한 줄로 요약"},
        "reasoning": {"type": "string", "description": "그렇게 판단한 구체적 근거"},
    },
    "required": ["has_issue", "decision", "reasoning"],
    "additionalProperties": False,
}

PM_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "팀 의견 중 실제로 반영하기로 결정한 이슈. 모두 문제 없다고 판단하면 빈 배열.",
        },
        "revised_draft": {"type": "string", "description": "결정을 반영해 수정한 초안 (수정 없으면 입력과 동일)"},
        "decision": {"type": "string", "description": "각 팀 의견을 어떻게 조율했는지 한 줄 요약"},
        "reasoning": {
            "type": "string",
            "description": "그렇게 조율한 근거. 팀 간 의견이 충돌했다면 어느 쪽을 우선했는지와 이유를 포함.",
        },
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

TEAM_ROLE_PROMPTS = {
    "EditingTeam": (
        "당신은 MUSE 창작 조직의 Editing Team입니다. "
        "오직 문장/문체/가독성 관점에서만 초안을 검토하세요. "
        "세계관 일관성이나 감정 곡선은 다른 팀의 영역이니 언급하지 마세요."
    ),
    "LoreTeam": (
        "당신은 MUSE 창작 조직의 Lore Team입니다. "
        "오직 세계관 설정과의 모순, 논리적 일관성 관점에서만 초안을 검토하세요. "
        "문장/문체나 감정 곡선은 다른 팀의 영역이니 언급하지 마세요."
    ),
    "EmotionTeam": (
        "당신은 MUSE 창작 조직의 Emotion Team입니다. "
        "오직 감정 곡선/페이싱/긴장감 흐름 관점에서만 초안을 검토하세요. "
        "문장/문체나 세계관 일관성은 다른 팀의 영역이니 언급하지 마세요."
    ),
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


def _team_opinion(state: MuseState, agent_key: str) -> MuseState:
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": TEAM_OPINION_SCHEMA},
        },
        system=TEAM_ROLE_PROMPTS[agent_key],
        messages=[{
            "role": "user",
            "content": f"세계관: {state['world']}\n\n현재 초안 (라운드 {state['round']}):\n{state['draft']}",
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    state["current_opinions"][agent_key] = {
        "has_issue": data["has_issue"],
        "decision": data["decision"],
        "reasoning": data["reasoning"],
    }
    state["decision_log"].append({
        "round": state["round"],
        "agent": agent_key,
        "decision": data["decision"],
        "reasoning": data["reasoning"],
    })
    return state


def editing_team(state: MuseState) -> MuseState:
    round_n = state["round"] + 1
    state["round"] = round_n
    state["current_opinions"] = {}
    return _team_opinion(state, "EditingTeam")


def lore_team(state: MuseState) -> MuseState:
    return _team_opinion(state, "LoreTeam")


def emotion_team(state: MuseState) -> MuseState:
    return _team_opinion(state, "EmotionTeam")


def pm_coordinate(state: MuseState) -> MuseState:
    round_n = state["round"]
    opinions_text = "\n".join(
        f"- {agent} (문제 있음: {op['has_issue']}): {op['decision']} — {op['reasoning']}"
        for agent, op in state["current_opinions"].items()
    )

    response = get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": PM_SCHEMA},
        },
        system=(
            "당신은 MUSE 창작 조직의 PM입니다. "
            "Editing/Lore/Emotion 세 팀의 의견을 종합해 이번 라운드에 실제로 반영할 "
            "사항을 결정하세요. 팀 간 의견이 충돌하면 어느 쪽을 우선했는지와 그 이유를 "
            "명시하세요. 모든 팀이 문제 없다고 판단하면 issues를 빈 배열로 반환하고 "
            "합의 도달을 선언하세요."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"세계관: {state['world']}\n\n"
                f"현재 초안 (라운드 {round_n}):\n{state['draft']}\n\n"
                f"팀별 의견:\n{opinions_text}"
            ),
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    state["issues"] = data["issues"]

    if data["issues"]:
        state["draft"] = data["revised_draft"]
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
    graph.add_node("editing_team", editing_team)
    graph.add_node("lore_team", lore_team)
    graph.add_node("emotion_team", emotion_team)
    graph.add_node("pm_coordinate", pm_coordinate)
    graph.add_node("publisher", publisher)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("story_team")
    graph.add_edge("story_team", "editing_team")
    graph.add_edge("editing_team", "lore_team")
    graph.add_edge("lore_team", "emotion_team")
    graph.add_edge("emotion_team", "pm_coordinate")
    graph.add_conditional_edges("pm_coordinate", should_continue, {
        "review": "editing_team",
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
        "current_opinions": {},
        "decision_log": [],
        "status": "",
        "summary": "",
    }
