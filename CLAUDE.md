# KION RAG PoC - Project Context

## 프로젝트 개요

KION(국가나노인프라협의체) 팹서비스의 장비 검색을 자연어 AI 챗봇으로 구현한 PoC 프로젝트입니다.

## 기술 스택

- **Backend**: FastAPI (Python 3.9+)
- **Vector DB**: ChromaDB (PersistentClient)
- **LLM**: Ollama + Qwen 2.5:32B (품질 향상)
- **Embedding**: intfloat/multilingual-e5-large
- **Frontend**: Vanilla JavaScript + CSS (SSE Streaming)

## 핵심 기능 (PoC 구현 완료)

| 기능 | 설명 | 파일 |
|------|------|------|
| **Hybrid Search** | BM25 + Vector 결합 검색 | `app/hybrid_search.py` |
| **LLM Intent Parser** | 부정/복합/추상적 질의 감지 | `app/intent_parser.py` |
| **Session Management** | 연계 질의 지원 (대화 이력) | `app/conversation.py` |
| **SSE Streaming** | 실시간 토큰 스트리밍 UI | `static/index.html` |

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `app/main.py` | FastAPI 라우터, API 엔드포인트 |
| `app/rag.py` | RAG 파이프라인, ChromaDB 연동, Hybrid Search |
| `app/hybrid_search.py` | BM25 + Vector 하이브리드 검색 |
| `app/llm.py` | Ollama LLM 호출, 프롬프트 관리 |
| `app/query_parser.py` | 자연어 쿼리 파싱 (웨이퍼, 온도, 재료 추출) |
| `app/intent_parser.py` | LLM 의도 파악 (부정문, 복합 조건) |
| `app/conversation.py` | 세션 관리, 연계 질의 처리 |
| `app/filters.py` | 하드 필터링 & 리랭킹 |
| `app/policy.py` | Policy DB (기관/공정 매핑) |
| `data/kion_equipment.json` | 102개 장비 데이터 |
| `prompts/*.txt` | LLM 프롬프트 템플릿 |

## API 엔드포인트

```
POST /chat          - JSON 응답 (세션 지원)
POST /chat/stream   - SSE 스트리밍
GET  /health        - 서버 상태
GET  /equipment/count - 장비 수
GET  /policy/status - Policy DB 상태
```

## 개발 시 주의사항

1. **중국어 필터링**: `llm.py`의 `filter_chinese()` 함수로 중국어 제거
2. **프롬프트 수정**: `prompts/` 폴더의 txt 파일 수정 후 서버 재시작 불필요 (런타임 로드)
3. **장비 데이터**: `data/kion_equipment.json` 수정 후 `/equipment/reload` 호출 또는 서버 재시작
4. **스트리밍**: SSE 방식으로 토큰 단위 실시간 응답
5. **세션**: `session_id`를 요청에 포함하면 연계 질의 가능

## 서버 실행

```bash
# Ollama LLM 모델 필요 (32B 권장)
ollama pull qwen2.5:32b

# 임베딩 모델은 sentence-transformers에서 자동 다운로드
# (intfloat/multilingual-e5-large)

# 서버 실행
python3 run.py
# 또는
uvicorn app.main:app --reload --port 8000
```

## 테스트 쿼리 예시

```
# 기본 질의
MOCVD 장비 추천해줘

# 연계 질의 (세션 유지)
6인치 웨이퍼용으로 바꿔줘
더 싼 장비는 없어?

# 부정 질의
CVD 말고 다른 증착 장비

# 복합 조건
GaN이나 SiC 에피 성장 장비
```

## 정적 페이지

- `/` → 메인 페이지 (챗봇 위젯 + 스트리밍)
- `/static/architecture.html` → 시스템 아키텍처
- `/static/flowchart-demo.html` → 처리 흐름도 (NEW)
- `/static/checklist.html` → 구현 체크리스트
- `/static/deployment.html` → 배포 아키텍처
- `/docs` → Swagger API 문서

## 성능 지표 (M4 Pro 48GB 기준)

| 모델 | 응답 시간 | 한국어 품질 |
|------|----------|------------|
| 7B | ~2초 | 양호 |
| **32B** | **~17초** | **우수** |
| 32B (스트리밍) | 첫 토큰 8초 | 우수 |

## 임베딩 모델 비교 (2025-12-29)

| 모델 | Recall@3 | 상태 |
|------|----------|------|
| **multilingual-e5-large** | **82.67%** | 현재 사용 중 |
| bge-m3 | 80.00% | PRD 권장 |
| ko-sroberta-multitask | 76.00% | PRD 권장 |

## GitHub

https://github.com/jeromwolf/kion-rag
