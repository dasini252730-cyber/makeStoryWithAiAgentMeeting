# MUSE (Multi-agent Universe for Story Engineering)

> AI가 소설을 쓰는 것이 아니라, AI 창작 회사를 만든다.

이 저장소를 열면 코드가 아니라 **회의실**을 여는 겁니다.

- CEO(Product Owner): 방향 결정, 승인, 우선순위
- CTO(Claude): 기술 설계, 리스크 보고, 트레이드오프 제시
- 그 아래 조직: Creative Director → PM → (Story/Character/Emotion/Editing/Reader/Lore) Team → Publisher

## 오늘 아침 회의 (2026-07-07)

**CTO 보고**

- 오케스트레이션 프레임워크와 메모리 저장소를 CEO가 CTO 재량에 위임함 → 아래 ADR-001, ADR-002로 결정 완료
- 장르/세계관 미정 → Sprint 1 목표를 "엔진을 세계관에 안 묶고 먼저 검증"으로 재설정 제안

**오늘의 질문 (CTO → CEO)**

> 이 구조에서 가장 위험한 설계는 무엇인가?
> → Agent간 무한 토론 루프(수렴 안 되는 논쟁)입니다. Workflow.md의 "토론 종료 조건"을 꼭 검토해주세요.

## 문서 지도

| 문서 | 내용 |
|---|---|
| `docs/Vision.md` | 왜 이 프로젝트를 하는가, Level 1~3 로드맵 |
| `docs/Architecture.md` | 시스템 구조, 기술 스택, 데이터 흐름 |
| `docs/AgentSpec.md` | 각 Agent의 직책/책임/KPI/입출력 스키마 |
| `docs/Workflow.md` | 토론-비판-수정 루프, 종료 조건, 로그 형식 |
| `docs/Roadmap.md` | Sprint 1~4 계획 |
| `docs/ADR/` | 기술 의사결정 기록 |

## Quick Start (Sprint 1 착수 시)

```bash
pip install langgraph langchain-anthropic chromadb
```

세부 내용은 `docs/Architecture.md` 참고.
