# KION RAG - AI 반도체 장비 추천 시스템

> 자연어 기반 반도체/디스플레이 공정 장비 추천 AI 챗봇

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen2.5:32B-purple.svg)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 개요

KION RAG는 [국가나노인프라협의체(KION)](https://www.kion.or.kr) 팹서비스의 장비 검색을 자연어 AI 챗봇으로 구현한 PoC(Proof of Concept) 프로젝트입니다.

기존의 키워드 기반 검색 대신, 사용자가 **"6인치 Si 웨이퍼용 MOCVD 장비 추천해줘"** 같은 자연어로 질문하면 AI가 최적의 장비를 추천하고 이유를 설명합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| **Hybrid Search** | BM25 + Vector 결합으로 검색 정확도 향상 |
| **LLM Intent Parser** | 부정문/복합/추상적 질의 자동 감지 |
| **Session Management** | 연계 질의 지원 ("더 싼 장비는?") |
| **SSE Streaming** | 실시간 토큰 스트리밍 UI |
| **스펙 자동 파싱** | 웨이퍼 크기, 온도, 재료 조건 자동 추출 |
| **매칭 점수** | 적합도를 퍼센트로 표시 |

## 데모 스크린샷

```
┌─────────────────────────────────────────┐
│  🤖 KION AI 장비추천      세션: a1b2c3  │
├─────────────────────────────────────────┤
│  사용자: MOCVD 장비 추천해줘              │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ [KION-101] MOCVD (6인치)   99%  │    │
│  │ 📍 한국나노기술원                │    │
│  │ 💿 4 inch, 6 inch, 8 inch      │    │
│  │ 🧪 GaN, AlGaN, InGaN           │    │
│  │ [예약 신청 →]                   │    │
│  └─────────────────────────────────┘    │
│                                         │
│  AI: 사용자님, GaN MOCVD 장비 중         │
│      6인치 웨이퍼 지원하는 장비에 대해▌   │
│      (스트리밍 중...)                    │
│                                         │
│  ⏱️ 처리 시간: 8.64초 (스트리밍)         │
│  💡 "8인치로 바꿔줘" 같은 후속 질문 가능! │
└─────────────────────────────────────────┘
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| **Backend** | FastAPI, Python 3.9+ |
| **Vector DB** | ChromaDB |
| **LLM** | Ollama (Qwen2.5:32B) |
| **Embedding** | multilingual-e5-large |
| **Search** | Hybrid (BM25 + Vector) |
| **Frontend** | Vanilla JS, SSE Streaming |

## 설치 및 실행

### 1. 요구사항

- Python 3.9+
- [Ollama](https://ollama.ai) 설치
- 48GB+ RAM (32B 모델 권장) 또는 16GB (7B 모델)

### 2. Ollama 모델 다운로드

```bash
# 32B 모델 (권장 - 품질 우수)
ollama pull qwen2.5:32b

# 또는 7B 모델 (빠른 응답)
ollama pull qwen2.5:7b
```

### 3. 프로젝트 설치

```bash
git clone https://github.com/jeromwolf/kion-rag.git
cd kion-rag

# 가상환경 생성 (선택)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 4. 서버 실행

```bash
python run.py
```

또는

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 접속

- **웹 UI**: http://localhost:8000
- **API 문서**: http://localhost:8000/docs

## API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/chat` | 장비 추천 (JSON, 세션 지원) |
| POST | `/chat/stream` | 장비 추천 (SSE 스트리밍) |
| GET | `/health` | 서버 상태 확인 |
| GET | `/policy/status` | Policy DB 상태 |

### 예시 요청 (세션 연계)

```bash
# 1차 질의
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "MOCVD 장비 추천해줘"}'

# 2차 연계 질의 (session_id 포함)
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "6인치 웨이퍼용으로 바꿔줘", "session_id": "a1b2c3d4"}'
```

### 예시 응답

```json
{
  "query": "MOCVD 장비 추천해줘",
  "recommendations": [
    {
      "equipment_id": "KION-101",
      "name": "MOCVD (6인치)",
      "category": "증착",
      "score": 0.99,
      "reason": "GaN 에피택시 성장에 최적화",
      "institution": "한국나노기술원",
      "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
      "materials": ["GaN", "AlGaN", "InGaN"]
    }
  ],
  "explanation": "사용자님, GaN MOCVD 장비를 추천드립니다...",
  "processing_time": 17.55,
  "session_id": "a1b2c3d4",
  "turn_count": 1
}
```

## 프로젝트 구조

```
kion-rag/
├── app/
│   ├── main.py           # FastAPI 앱 & 라우터
│   ├── rag.py            # RAG 파이프라인 + Hybrid Search
│   ├── hybrid_search.py  # BM25 + Vector 검색
│   ├── intent_parser.py  # LLM 의도 파악
│   ├── conversation.py   # 세션 관리
│   ├── llm.py            # LLM 서비스
│   ├── query_parser.py   # 쿼리 파싱
│   ├── filters.py        # 필터 & 리랭킹
│   └── policy.py         # Policy DB
├── data/
│   ├── kion_equipment.json   # 장비 데이터 (102개)
│   └── policy_db/            # 기관/공정 매핑
├── prompts/
│   └── *.txt                 # LLM 프롬프트
├── static/
│   ├── index.html            # 메인 UI (스트리밍)
│   ├── architecture.html     # 시스템 아키텍처
│   ├── flowchart-demo.html   # 처리 흐름도
│   ├── checklist.html        # 구현 체크리스트
│   └── budget.html           # GPU 인프라 예산 계획서
└── README.md
```

## 핵심 기능 상세

### 1. Hybrid Search (BM25 + Vector)

```python
# 50:50 가중치로 결합
hybrid_results = rag_pipeline.hybrid_search(
    query="GaN MOCVD 장비",
    vector_weight=0.5,
    bm25_weight=0.5
)
```

### 2. 연계 질의 (Session Management)

```
1차: "MOCVD 장비 추천해줘"     → Session 생성
2차: "6인치로 바꿔줘"          → 조건 병합 (condition_replace)
3차: "더 싼 장비는?"           → 이전 조건 유지 (comparison)
```

### 3. LLM Intent Parser

| 질의 유형 | 예시 | 처리 |
|----------|------|------|
| 부정문 | "CVD 말고 다른 장비" | exclude 필터 적용 |
| 복합 조건 | "GaN이나 SiC 장비" | OR 조건 처리 |
| 추상적 | "비용 효율적인 장비" | 의미 확장 검색 |

## 성능 지표

| 지표 | 7B 모델 | 32B 모델 |
|------|---------|----------|
| 응답 시간 | ~2초 | ~17초 |
| 첫 토큰 (스트리밍) | ~1초 | ~8초 |
| 한국어 품질 | 양호 | 우수 |
| 추천 정확도 | 82% | 90%+ |

## 향후 계획

- [x] Hybrid Search (BM25 + Vector)
- [x] LLM Intent Parser
- [x] Session Management
- [x] SSE Streaming UI
- [ ] 실제 KION 장비 데이터 연동
- [ ] 다국어 지원 (영어)
- [ ] KION 예약 시스템 연동

## 라이선스

MIT License

## 참고

- [KION 국가나노인프라협의체](https://www.kion.or.kr)
- [KION 팹서비스](https://fab.kion.or.kr)
- [한국나노기술원](https://www.kanc.re.kr)

---

Made with Claude Code | Powered by Qwen 2.5 32B
