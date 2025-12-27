# KION RAG - AI 반도체 장비 추천 시스템

> 자연어 기반 반도체/디스플레이 공정 장비 추천 AI 챗봇

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-LLM-purple.svg)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 개요

KION RAG는 [국가나노인프라협의체(KION)](https://www.kion.or.kr) 팹서비스의 장비 검색을 자연어 AI 챗봇으로 구현한 PoC(Proof of Concept) 프로젝트입니다.

기존의 키워드 기반 검색 대신, 사용자가 **"6인치 Si 웨이퍼용 MOCVD 장비 추천해줘"** 같은 자연어로 질문하면 AI가 최적의 장비를 추천하고 이유를 설명합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| **자연어 검색** | 복잡한 필터 없이 자연어로 장비 검색 |
| **AI 맞춤 추천** | RAG 기반 컨텍스트 이해 + LLM 추천 |
| **스펙 자동 파싱** | 웨이퍼 크기, 온도, 재료 조건 자동 추출 |
| **실시간 스트리밍** | 응답을 실시간으로 확인 |
| **매칭 점수** | 적합도를 퍼센트로 표시 |
| **예약 연동** | 장비 카드에서 바로 예약 페이지 이동 |

## 데모 스크린샷

```
┌─────────────────────────────────────────┐
│  🤖 KION AI 장비추천                     │
├─────────────────────────────────────────┤
│  사용자: MOCVD 장비 추천해줘              │
│                                         │
│  AI: 사용자님, MOCVD 장비에 대해          │
│      추천드립니다.                        │
│                                         │
│  1. **[KION-009]** MOCVD 장비는          │
│     III-V 화합물 반도체 에피택시...        │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ [KION-009] MOCVD         97%   │    │
│  │ 📍 나노종합기술원                │    │
│  │ 💿 2 inch, 4 inch              │    │
│  │ 🧪 GaN, AlGaN, InGaN           │    │
│  │ [예약 신청 →]                   │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| **Backend** | FastAPI, Python 3.9+ |
| **Vector DB** | ChromaDB |
| **LLM** | Ollama (Qwen2.5:7b) |
| **Embedding** | nomic-embed-text |
| **Frontend** | Vanilla JS, CSS |

## 설치 및 실행

### 1. 요구사항

- Python 3.9+
- [Ollama](https://ollama.ai) 설치

### 2. Ollama 모델 다운로드

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
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
| POST | `/chat` | 장비 추천 (JSON 응답) |
| POST | `/chat/stream` | 장비 추천 (SSE 스트리밍) |
| GET | `/equipment/count` | 저장된 장비 수 조회 |
| POST | `/equipment/reload` | 장비 데이터 리로드 |
| GET | `/health` | 서버 상태 확인 |

### 예시 요청

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "6인치 GaN MOCVD 장비 추천해줘"}'
```

### 예시 응답

```json
{
  "query": "6인치 GaN MOCVD 장비 추천해줘",
  "recommendations": [
    {
      "equipment_id": "KION-009",
      "name": "MOCVD",
      "category": "증착",
      "score": 0.97,
      "reason": "GaN 기반 III-V 화합물 반도체 에피택시 성장에 최적화",
      "institution": "나노종합기술원",
      "wafer_sizes": ["2 inch", "4 inch"],
      "materials": ["GaN", "AlGaN", "InGaN", "AlN"]
    }
  ],
  "explanation": "KION-009 MOCVD 장비는 GaN 기반 LED, HEMT, 파워소자용 에피 성장에 적합합니다.",
  "processing_time": 5.12
}
```

## 프로젝트 구조

```
kion-rag/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 앱 & 라우터
│   ├── config.py         # 환경 설정
│   ├── models.py         # Pydantic 모델
│   ├── rag.py            # RAG 파이프라인
│   ├── llm.py            # LLM 서비스
│   ├── query_parser.py   # 쿼리 파싱 & 필터
│   ├── filters.py        # 하드 필터 & 리랭킹
│   └── data_loader.py    # 데이터 로더
├── data/
│   ├── kion_equipment.json   # 장비 데이터 (100개)
│   └── filter_rules.json     # 필터 규칙
├── prompts/
│   ├── recommendation_json.txt    # JSON 응답용 프롬프트
│   └── recommendation_stream.txt  # 스트리밍용 프롬프트
├── static/
│   ├── index.html        # 메인 페이지 & 챗봇
│   ├── reservation.html  # 예약 페이지
│   ├── architecture.html # 시스템 아키텍처
│   ├── flowchart.html    # 처리 흐름도
│   ├── deployment.html   # 배포 아키텍처 (로컬/클라우드)
│   └── sample.html       # 샘플 데이터 (100개 장비)
├── requirements.txt
├── run.py
├── CLAUDE.md             # 프로젝트 컨텍스트
└── README.md
```

## 문서 페이지

| 페이지 | URL | 설명 |
|--------|-----|------|
| 시스템 아키텍처 | `/static/architecture.html` | RAG 파이프라인 구조 |
| 처리 흐름도 | `/static/flowchart.html` | 쿼리→추천 상세 흐름 |
| 배포 아키텍처 | `/static/deployment.html` | 로컬 vs 클라우드 비교 |
| 샘플 데이터 | `/static/sample.html` | 100개 장비 & 필터 룰 |

## 쿼리 파싱 예시

| 입력 | 파싱 결과 |
|------|----------|
| "6인치 Si 웨이퍼" | wafer: 6 inch, material: Si |
| "400도 이상 열처리" | temp_min: 400 |
| "GaN MOCVD 장비" | material: GaN, category: 증착 |
| "나노종합기술원 SEM" | institution: 나노종합기술원, category: 분석 |

## 테스트 결과

100개 쿼리 테스트 결과:

| 지표 | 결과 |
|------|------|
| 성공률 | 100% |
| 평균 응답 시간 | 5.16초 |
| 중국어 필터링 | 100% |
| 장비-설명 일치율 | 100% |

## 향후 계획

- [ ] 실제 KION 장비 데이터 연동
- [ ] 응답 시간 3초 이하로 최적화
- [ ] 다국어 지원 (영어)
- [ ] 사용자 피드백 기반 추천 개선
- [ ] KION 예약 시스템 실제 연동

## 라이선스

MIT License

## 참고

- [KION 국가나노인프라협의체](https://www.kion.or.kr)
- [KION 팹서비스](https://fab.kion.or.kr)
- [한국나노기술원](https://www.kanc.re.kr)
- [나노종합기술원](https://www.nnfc.re.kr)

---

Made with ❤️ by Kelly | Powered by Claude Code
