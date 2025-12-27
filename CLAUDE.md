# KION RAG PoC - Project Context

## 프로젝트 개요

KION(국가나노인프라협의체) 팹서비스의 장비 검색을 자연어 AI 챗봇으로 구현한 PoC 프로젝트입니다.

## 기술 스택

- **Backend**: FastAPI (Python 3.9+)
- **Vector DB**: ChromaDB (In-Memory)
- **LLM**: Ollama + Qwen 2.5:7B
- **Embedding**: nomic-embed-text
- **Frontend**: Vanilla JavaScript + CSS

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `app/main.py` | FastAPI 라우터, API 엔드포인트 |
| `app/rag.py` | RAG 파이프라인, ChromaDB 연동 |
| `app/llm.py` | Ollama LLM 호출, 프롬프트 관리 |
| `app/query_parser.py` | 자연어 쿼리 파싱 (웨이퍼, 온도, 재료 추출) |
| `app/filters.py` | 하드 필터링 & 리랭킹 |
| `data/kion_equipment.json` | 100개 장비 데이터 |
| `data/filter_rules.json` | 필터 규칙 (카테고리, 재료 매핑) |
| `prompts/*.txt` | LLM 프롬프트 템플릿 |

## API 엔드포인트

```
POST /chat          - JSON 응답
POST /chat/stream   - SSE 스트리밍
GET  /health        - 서버 상태
GET  /equipment/count - 장비 수
```

## 개발 시 주의사항

1. **중국어 필터링**: `llm.py`의 `filter_chinese()` 함수로 중국어 제거
2. **프롬프트 수정**: `prompts/` 폴더의 txt 파일 수정 후 서버 재시작 불필요 (런타임 로드)
3. **장비 데이터**: `data/kion_equipment.json` 수정 후 `/equipment/reload` 호출 또는 서버 재시작
4. **스트리밍**: SSE 방식으로 토큰 단위 실시간 응답

## 서버 실행

```bash
# Ollama 모델 필요
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 서버 실행
python3 run.py
# 또는
uvicorn app.main:app --reload --port 8000
```

## 테스트 쿼리 예시

```
MOCVD 장비 추천해줘
6인치 GaN 열처리 장비
8인치 PECVD 증착
SEM 분석 장비
나노종합기술원 스퍼터
```

## 정적 페이지

- `/` → 메인 페이지 (챗봇 위젯)
- `/static/architecture.html` → 시스템 아키텍처
- `/static/flowchart.html` → 처리 흐름도
- `/static/deployment.html` → 배포 아키텍처 (로컬/클라우드)
- `/static/sample.html` → 샘플 데이터 (100개 장비)
- `/docs` → Swagger API 문서

## 성능 지표

- 평균 응답 시간: ~5초
- 장비 데이터: 100개
- 카테고리: 14개 (증착, 분석, 식각, 열처리 등)

## GitHub

https://github.com/jeromwolf/kion-rag
