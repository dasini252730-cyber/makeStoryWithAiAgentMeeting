"use client";

import { useRef, useState } from "react";

type DecisionLogEntry = {
  round: number;
  agent: string;
  decision: string;
  reasoning: string;
};

type MuseState = {
  world: string;
  previous_summary: string;
  draft: string;
  round: number;
  issues: string[];
  decision_log: DecisionLogEntry[];
  status: string;
  summary: string;
};

type PipelineEvent = {
  node?: string;
  state?: MuseState;
  scene_id?: number;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const AGENTS: { key: string; label: string }[] = [
  { key: "StoryTeam", label: "Story Team" },
  { key: "EditingTeam", label: "Editing Team" },
  { key: "LoreTeam", label: "Lore Team" },
  { key: "EmotionTeam", label: "Emotion Team" },
  { key: "PM", label: "PM (조율/수렴 판정)" },
  { key: "ContinuityTeam", label: "Continuity Team" },
  { key: "Publisher", label: "Publisher" },
];

const DEFAULT_WORLD = "테스트 월드 (Sprint 1 더미 세계관)";

export default function Home() {
  const [world, setWorld] = useState(DEFAULT_WORLD);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<MuseState | null>(null);
  const [savedSceneId, setSavedSceneId] = useState<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const doneAgents = new Set(
    (state?.decision_log ?? []).map((entry) => entry.agent)
  );

  function latestDecisionFor(agentKey: string): DecisionLogEntry | undefined {
    const entries = (state?.decision_log ?? []).filter(
      (entry) => entry.agent === agentKey
    );
    return entries[entries.length - 1];
  }

  function runPipeline() {
    if (running) return;

    eventSourceRef.current?.close();
    setError(null);
    setState(null);
    setSavedSceneId(null);
    setRunning(true);

    const url = `${API_BASE}/pipeline/run?world=${encodeURIComponent(world)}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const payload: PipelineEvent = JSON.parse(event.data);
        if (payload.state) {
          setState(payload.state);
        }
        if (payload.scene_id != null) {
          setSavedSceneId(payload.scene_id);
        }
      } catch {
        // 파싱 실패한 메시지는 무시
      }
    };

    es.addEventListener("done", () => {
      es.close();
      setRunning(false);
    });

    es.onerror = () => {
      setError(
        "백엔드 연결에 실패했거나 파이프라인 실행 중 오류가 발생했습니다. " +
          "백엔드가 켜져 있는지, ANTHROPIC_API_KEY가 설정되어 있는지 확인하세요."
      );
      es.close();
      setRunning(false);
    };
  }

  return (
    <div className="layout">
      <div className="panel">
        <h1>MUSE 회의실</h1>
        <p className="subtitle">CEO 입력</p>

        <label htmlFor="world">세계관 / 프리미스</label>
        <textarea
          id="world"
          rows={6}
          value={world}
          onChange={(e) => setWorld(e.target.value)}
          disabled={running}
        />

        <button onClick={runPipeline} disabled={running}>
          {running ? "실행 중…" : "▶ 파이프라인 실행"}
        </button>

        {state && (
          <p className="status-line">
            라운드 {state.round} · {state.status || "대기 중"}
          </p>
        )}
        {savedSceneId != null && (
          <p className="status-line">DB에 장면 #{savedSceneId}로 저장됨</p>
        )}
        {error && <div className="error-banner">{error}</div>}
      </div>

      <div className="panel">
        <p className="subtitle">Agent 진행 상황</p>
        <div className="agent-grid">
          {AGENTS.map((agent) => {
            const isDone = doneAgents.has(agent.key);
            const latest = latestDecisionFor(agent.key);
            return (
              <div
                key={agent.key}
                className={`agent-card${isDone ? " done" : ""}`}
              >
                <p className="name">{agent.label}</p>
                <span className="badge">{isDone ? "완료" : "대기"}</span>
                {latest && (
                  <p className="latest-decision">{latest.decision}</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel">
        <p className="subtitle">결과물</p>
        {state?.draft ? (
          <p className="draft-box">{state.draft}</p>
        ) : (
          <p className="empty-hint">아직 생성된 장면이 없습니다.</p>
        )}

        <p className="subtitle">Decision Log</p>
        {state?.decision_log && state.decision_log.length > 0 ? (
          state.decision_log.map((entry, i) => (
            <div className="log-entry" key={i}>
              <p className="meta">
                라운드 {entry.round} · {entry.agent}
              </p>
              <p className="decision">{entry.decision}</p>
              <p className="reasoning">{entry.reasoning}</p>
            </div>
          ))
        ) : (
          <p className="empty-hint">아직 로그가 없습니다.</p>
        )}
      </div>
    </div>
  );
}
