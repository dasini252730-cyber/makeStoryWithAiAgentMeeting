"use client";

import { useEffect, useRef, useState } from "react";

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
  episode_number?: number;
  message?: string;
};

type ArcEpisode = {
  episode_number: number;
  purpose: string;
  characters: string[];
  foreshadowing_plant: string[];
  foreshadowing_payoff: string[];
};

type Arc = {
  world: string;
  episode_count: number;
  series_summary: string;
  episodes: ArcEpisode[];
  pitch_to_ceo: string;
};

const MAX_RECONNECTS = 20;

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
  const eventCountRef = useRef(0);
  const reconnectAttemptsRef = useRef(0);

  const [episodeCount, setEpisodeCount] = useState(25);
  const [arc, setArc] = useState<Arc | null>(null);
  const [nextEpisode, setNextEpisode] = useState<number | null>(null);
  const [arcLoading, setArcLoading] = useState(false);
  const [arcError, setArcError] = useState<string | null>(null);

  useEffect(() => {
    loadArc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doneAgents = new Set(
    (state?.decision_log ?? []).map((entry) => entry.agent)
  );

  function latestDecisionFor(agentKey: string): DecisionLogEntry | undefined {
    const entries = (state?.decision_log ?? []).filter(
      (entry) => entry.agent === agentKey
    );
    return entries[entries.length - 1];
  }

  function connectStream(runId: string, since: number) {
    const url = `${API_BASE}/pipeline/stream/${runId}?since=${since}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const payload: PipelineEvent = JSON.parse(event.data);
        eventCountRef.current += 1;
        reconnectAttemptsRef.current = 0; // 데이터가 오면 재연결 카운터 리셋

        if (payload.node === "error" && payload.message) {
          setError(payload.message);
        }
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
      loadArc();
    });

    es.onerror = () => {
      es.close();
      // 호스팅 프록시가 긴 연결을 끊는 경우가 있어(예: Render 무료 티어), 마지막으로
      // 받은 이벤트 지점부터 자동 재연결한다. 계속 실패할 때만 사용자에게 알린다.
      if (reconnectAttemptsRef.current >= MAX_RECONNECTS) {
        setError(
          "백엔드와 연결이 반복적으로 끊겼습니다. 백엔드가 켜져 있는지 확인 후 다시 시도해주세요."
        );
        setRunning(false);
        return;
      }
      reconnectAttemptsRef.current += 1;
      setTimeout(() => connectStream(runId, eventCountRef.current), 1000);
    };
  }

  async function loadArc() {
    setArcError(null);
    try {
      const res = await fetch(`${API_BASE}/arc?world=${encodeURIComponent(world)}`);
      if (!res.ok) throw new Error(`load failed: ${res.status}`);
      const data = (await res.json()) as { arc: Arc | null; next_episode: number };
      setArc(data.arc);
      setNextEpisode(data.next_episode);
    } catch {
      setArcError("Arc 로딩에 실패했습니다. 백엔드가 켜져 있는지 확인하세요.");
    }
  }

  function connectArcStream(runId: string, since: number, attempt = 0) {
    const url = `${API_BASE}/pipeline/stream/${runId}?since=${since}`;
    const es = new EventSource(url);
    let count = since;

    es.onmessage = (event) => {
      try {
        const payload: {
          node?: string;
          message?: string;
          arc_id?: number;
          world?: string;
          episode_count?: number;
          series_summary?: string;
          episodes?: ArcEpisode[];
          pitch_to_ceo?: string;
        } = JSON.parse(event.data);
        count += 1;
        attempt = 0;

        if (payload.node === "error" && payload.message) {
          setArcError(payload.message);
        }
        if (payload.node === "arc_saved" && payload.series_summary && payload.episodes) {
          setArc({
            world: payload.world ?? world,
            episode_count: payload.episode_count ?? episodeCount,
            series_summary: payload.series_summary,
            episodes: payload.episodes,
            pitch_to_ceo: payload.pitch_to_ceo ?? "",
          });
        }
      } catch {
        // 파싱 실패한 메시지는 무시
      }
    };

    es.addEventListener("done", () => {
      es.close();
      setArcLoading(false);
      loadArc();
    });

    es.onerror = () => {
      es.close();
      if (attempt >= MAX_RECONNECTS) {
        setArcError("Arc 설계 중 백엔드와 연결이 반복적으로 끊겼습니다. 잠시 후 다시 시도해주세요.");
        setArcLoading(false);
        return;
      }
      setTimeout(() => connectArcStream(runId, count, attempt + 1), 1000);
    };
  }

  async function createArc() {
    if (arcLoading) return;
    setArcLoading(true);
    setArcError(null);
    try {
      const res = await fetch(
        `${API_BASE}/arc/start?world=${encodeURIComponent(world)}&episode_count=${episodeCount}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`start failed: ${res.status}`);
      const { run_id } = (await res.json()) as { run_id: string };
      connectArcStream(run_id, 0);
    } catch {
      setArcError("Arc 설계 시작에 실패했습니다. 백엔드가 켜져 있는지 확인하세요.");
      setArcLoading(false);
    }
  }

  async function runPipeline() {
    if (running) return;

    eventSourceRef.current?.close();
    setError(null);
    setState(null);
    setSavedSceneId(null);
    setRunning(true);
    eventCountRef.current = 0;
    reconnectAttemptsRef.current = 0;

    try {
      const res = await fetch(
        `${API_BASE}/pipeline/start?world=${encodeURIComponent(world)}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`start failed: ${res.status}`);
      const { run_id } = (await res.json()) as { run_id: string };
      connectStream(run_id, 0);
    } catch {
      setError("파이프라인 시작에 실패했습니다. 백엔드가 켜져 있는지 확인하세요.");
      setRunning(false);
    }
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

        <p className="subtitle" style={{ marginTop: 20 }}>
          Arc 설계 (전체 화 로드맵)
        </p>

        <label htmlFor="episodeCount">총 화수</label>
        <input
          id="episodeCount"
          type="number"
          min={1}
          max={999}
          value={episodeCount}
          onChange={(e) => setEpisodeCount(Number(e.target.value))}
          disabled={arcLoading}
        />

        <div className="arc-actions">
          <button onClick={createArc} disabled={arcLoading || running}>
            {arcLoading ? "설계 중…" : "🗺 Arc 설계 생성"}
          </button>
          <button onClick={loadArc} disabled={arcLoading}>
            불러오기
          </button>
        </div>

        {nextEpisode != null && (
          <p className="status-line">다음 화: {nextEpisode}화</p>
        )}
        {arcError && <div className="error-banner">{arcError}</div>}

        {arc && (
          <>
            {arc.pitch_to_ceo && (
              <div className="pitch-box">
                <p className="pitch-label">Arc Team → CEO 제안</p>
                <p className="pitch-text">{arc.pitch_to_ceo}</p>
              </div>
            )}
            <p className="arc-summary">{arc.series_summary}</p>
            <div className="arc-list">
              {arc.episodes.map((ep) => (
                <div
                  key={ep.episode_number}
                  className={`arc-episode${
                    ep.episode_number === nextEpisode ? " next" : ""
                  }`}
                >
                  <p className="ep-num">
                    {ep.episode_number}화
                    {ep.episode_number === nextEpisode ? " (다음)" : ""}
                  </p>
                  <p className="ep-purpose">{ep.purpose}</p>
                </div>
              ))}
            </div>
          </>
        )}
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
