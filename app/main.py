"""
KION RAG PoC - FastAPI Main Application
"""

import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager

from .config import settings
from .models import ChatRequest, ChatResponse, HealthResponse, RecommendedEquipment
from .rag import rag_pipeline
from .llm import generate_recommendation, generate_recommendation_stream, check_ollama_status
from .query_parser import parse_query, parsed_to_filters
from .filters import rerank_with_filters
from .policy import get_policy_manager  # Policy DB 통합
from .intent_parser import quick_intent_check, parse_intent_with_llm, apply_intent_filters
from .conversation import conversation_manager, detect_followup_intent, merge_with_previous_conditions
from fastapi.responses import StreamingResponse
import json

# Static files directory
STATIC_DIR = Path(__file__).parent.parent / "static"
DATA_DIR = Path(__file__).parent.parent / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 실행"""
    # Startup
    print(f"[{settings.APP_NAME}] Starting up...")
    rag_pipeline.initialize()

    # Policy DB 초기화
    pm = get_policy_manager()
    print(f"[PolicyDB] Loaded: {len(pm.institution.get_all())} institutions, "
          f"{len(pm.settings.get_all())} policies, "
          f"{len(pm.mapper.get_all_mappings())} mappings")

    yield
    # Shutdown
    print(f"[{settings.APP_NAME}] Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="KION 팹서비스 장비 추천 AI 챗봇 PoC",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mount
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Data files mount
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/", tags=["Root"])
async def root():
    """챗봇 UI로 리다이렉트"""
    return RedirectResponse(url="/static/index.html")


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """헬스 체크"""
    ollama_ok = check_ollama_status()

    return HealthResponse(
        status="healthy" if ollama_ok else "degraded",
        version=settings.APP_VERSION,
        ollama_status="connected" if ollama_ok else "disconnected",
        chroma_status="connected",
        equipment_count=rag_pipeline.get_count()
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    장비 추천 채팅

    사용자 질의를 받아 적합한 장비를 추천합니다.

    예시 질의:
    - "6 inch Si 웨이퍼용 RTA 장비 찾아줘"
    - "GaN HEMT 에피 성장용 MOCVD 장비 추천해줘"
    - "400도 이상 열처리 가능한 장비"
    """
    start_time = time.time()

    try:
        # -1. 세션 관리 (연계 질의 지원)
        session = conversation_manager.get_or_create_session(request.session_id)
        session_id = session.session_id

        # -0.5 연계 질의 감지
        followup_intent = detect_followup_intent(request.query)
        if followup_intent["is_followup"]:
            print(f"[Chat] Followup query detected: {followup_intent['intent_type']}")

        # 0. 쿼리 파싱 (하드 제약조건 추출)
        parsed = parse_query(request.query)
        chroma_filters = parsed_to_filters(parsed)

        # 0.25 연계 질의인 경우 이전 조건과 병합
        if followup_intent["is_followup"] and session.turns:
            prev_conditions = session.get_last_conditions()
            current_conditions = {
                "wafer_sizes": parsed.wafer_sizes,
                "materials": parsed.materials,
                "temp_min": parsed.temp_min,
                "temp_max": parsed.temp_max,
                "categories": getattr(parsed, 'mapped_categories', [])
            }
            merged = merge_with_previous_conditions(
                current_conditions, prev_conditions, followup_intent
            )
            # 병합된 조건 적용
            if merged.get("wafer_sizes"):
                parsed.wafer_sizes = merged["wafer_sizes"]
            if merged.get("materials"):
                parsed.materials = merged["materials"]
            if merged.get("temp_min"):
                parsed.temp_min = merged["temp_min"]
            if merged.get("temp_max"):
                parsed.temp_max = merged["temp_max"]
            # 필터 재구성
            chroma_filters = parsed_to_filters(parsed)
            print(f"[Chat] Merged conditions: {merged}")

        # 0.5 복잡한 질의 체크 및 LLM 의도 파악
        intent_check = quick_intent_check(request.query)
        intent = None
        search_query = request.query

        if intent_check["needs_llm_parsing"]:
            print(f"[Chat] Complex query detected: negative={intent_check['is_negative']}, compound={intent_check['is_compound']}")
            intent = parse_intent_with_llm(request.query)
            search_query = intent.search_query or request.query

        # 사용자 필터와 병합
        if request.filters:
            chroma_filters.update(request.filters)

        # STEP 2: Policy DB 공정-장비 매핑 결과 로깅
        mapped_cats = getattr(parsed, 'mapped_categories', [])
        print(f"[Chat] 파싱 결과: 웨이퍼={parsed.wafer_sizes}, 온도={parsed.temp_min}~{parsed.temp_max}, 재료={parsed.materials}")
        if mapped_cats:
            print(f"[Chat] Policy DB 매핑: {mapped_cats}")

        # 1. 하이브리드 검색 (벡터 + BM25)
        search_results = rag_pipeline.hybrid_search(
            query=search_query,  # 의도 파악된 검색 쿼리 사용
            top_k=(request.top_k or settings.TOP_K) * 2,  # 필터링 고려해 2배로 검색
            filters=chroma_filters if chroma_filters else None,
            vector_weight=0.5,
            bm25_weight=0.5
        )

        if not search_results:
            return ChatResponse(
                query=request.query,
                recommendations=[],
                explanation="검색 조건에 맞는 장비를 찾지 못했습니다. 다른 조건으로 다시 검색해주세요.",
                processing_time=round(time.time() - start_time, 2)
            )

        # 1.5. 하드 필터 + 리랭킹 적용
        filtered_results = rerank_with_filters(search_results, parsed)

        # 1.6. 의도 기반 필터 적용 (부정 조건, OR 조건 등)
        if intent:
            filtered_results = apply_intent_filters(filtered_results, intent)

        # 필터 통과한 장비만 추출 (상위 N개)
        top_k = request.top_k or settings.TOP_K
        passed_results = [eq for eq in filtered_results if eq.get("filter_passed", True)][:top_k]

        # 모두 필터 실패시 원본 사용
        if not passed_results:
            passed_results = filtered_results[:top_k]

        # 2. LLM으로 추천 생성
        llm_result = generate_recommendation(request.query, passed_results)

        # 3. 결과 매핑
        recommendations = []
        for rec in llm_result.get("recommendations", []):
            eq_id = rec.get("equipment_id")
            # 필터된 결과에서 해당 장비 찾기
            matched_eq = next((eq for eq in passed_results if eq["equipment_id"] == eq_id), None)

            if matched_eq:
                # combined_score 사용 (필터 점수 반영)
                final_score = matched_eq.get("combined_score", matched_eq.get("score", 0.5))
                recommendations.append(RecommendedEquipment(
                    equipment_id=eq_id,
                    name=matched_eq["name"],
                    category=matched_eq["category"],
                    score=round(final_score, 2),
                    reason=rec.get("reason", ""),
                    reservation_url=matched_eq.get("reservation_url"),
                    institution=matched_eq.get("institution"),
                    wafer_sizes=matched_eq.get("wafer_sizes"),
                    materials=matched_eq.get("materials")
                ))

        # LLM이 추천을 못 만든 경우 필터된 결과 상위 3개 사용
        if not recommendations and passed_results:
            for eq in passed_results[:3]:
                final_score = eq.get("combined_score", eq.get("score", 0.5))
                recommendations.append(RecommendedEquipment(
                    equipment_id=eq["equipment_id"],
                    name=eq["name"],
                    category=eq["category"],
                    score=round(final_score, 2),
                    reason=f"{eq['category']} 장비로, 요청 조건과 유사합니다.",
                    reservation_url=eq.get("reservation_url"),
                    institution=eq.get("institution"),
                    wafer_sizes=eq.get("wafer_sizes"),
                    materials=eq.get("materials")
                ))

        # 대화 이력 저장
        extracted_conditions = {
            "wafer_sizes": parsed.wafer_sizes,
            "materials": parsed.materials,
            "temp_min": parsed.temp_min,
            "temp_max": parsed.temp_max,
            "categories": getattr(parsed, 'mapped_categories', [])
        }
        recommended_ids = [r.equipment_id for r in recommendations]
        response_summary = ", ".join([r.name for r in recommendations[:3]])

        conversation_manager.add_turn(
            session_id=session_id,
            query=request.query,
            response_summary=response_summary,
            extracted_conditions=extracted_conditions,
            recommended_ids=recommended_ids
        )

        return ChatResponse(
            query=request.query,
            recommendations=recommendations,
            explanation=llm_result.get("explanation", "위 장비들을 추천드립니다."),
            processing_time=round(time.time() - start_time, 2),
            session_id=session_id,
            turn_count=len(session.turns)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(request: ChatRequest):
    """
    스트리밍 장비 추천 채팅 (SSE)

    실시간으로 응답을 스트리밍합니다.
    """
    # 0. 쿼리 파싱
    parsed = parse_query(request.query)
    chroma_filters = parsed_to_filters(parsed)

    # 0.5 복잡한 질의 체크 및 LLM 의도 파악
    intent_check = quick_intent_check(request.query)
    intent = None
    search_query = request.query

    if intent_check["needs_llm_parsing"]:
        print(f"[Stream] Complex query detected: negative={intent_check['is_negative']}, compound={intent_check['is_compound']}")
        intent = parse_intent_with_llm(request.query)
        search_query = intent.search_query or request.query

    if request.filters:
        chroma_filters.update(request.filters)

    # 1. 하이브리드 검색 (벡터 + BM25)
    search_results = rag_pipeline.hybrid_search(
        query=search_query,
        top_k=(request.top_k or settings.TOP_K) * 2,
        filters=chroma_filters if chroma_filters else None,
        vector_weight=0.5,
        bm25_weight=0.5
    )

    # 1.5. 필터 + 리랭킹
    filtered_results = rerank_with_filters(search_results, parsed) if search_results else []

    # 1.6. 의도 기반 필터 적용 (부정 조건, OR 조건 등)
    if intent:
        filtered_results = apply_intent_filters(filtered_results, intent)

    top_k = request.top_k or settings.TOP_K
    passed_results = [eq for eq in filtered_results if eq.get("filter_passed", True)][:top_k]
    if not passed_results:
        passed_results = filtered_results[:top_k]

    def generate():
        # 표시할 장비 (상위 3개로 제한)
        display_results = passed_results[:3]

        # 장비 정보 먼저 전송
        if display_results:
            equipment_info = {
                "type": "equipment",
                "data": [
                    {
                        "equipment_id": eq["equipment_id"],
                        "name": eq["name"],
                        "category": eq["category"],
                        "score": round(eq.get("combined_score", eq.get("score", 0.5)), 2),
                        "institution": eq.get("institution"),
                        "wafer_sizes": eq.get("wafer_sizes"),
                        "materials": eq.get("materials"),
                        "reservation_url": eq.get("reservation_url")
                    }
                    for eq in display_results
                ]
            }
            yield f"data: {json.dumps(equipment_info, ensure_ascii=False)}\n\n"

        # LLM 스트리밍 응답 (동일한 장비만 전달하여 일치시킴)
        for token in generate_recommendation_stream(request.query, display_results):
            chunk = {"type": "token", "data": token}
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        # 완료 신호
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/equipment/count", tags=["Equipment"])
async def get_equipment_count():
    """저장된 장비 수 조회"""
    return {"count": rag_pipeline.get_count()}


@app.get("/equipment/list", tags=["Equipment"])
async def get_equipment_list():
    """모든 장비 목록 조회"""
    return {"equipment": rag_pipeline.get_all()}


@app.post("/equipment/reload", tags=["Equipment"])
async def reload_equipment():
    """샘플 장비 데이터 다시 로드"""
    from .data_loader import load_sample_data
    count = load_sample_data()
    return {"message": f"{count}개 장비 데이터가 로드되었습니다."}


# === Policy DB Admin API ===
@app.post("/policy/reload", tags=["Policy"])
async def reload_policy():
    """Policy DB 데이터 리로드"""
    pm = get_policy_manager()
    pm.reload_all()
    return {
        "message": "Policy DB reloaded",
        "institutions": len(pm.institution.get_all()),
        "policies": len(pm.settings.get_all()),
        "mappings": len(pm.mapper.get_all_mappings())
    }


@app.get("/policy/status", tags=["Policy"])
async def get_policy_status():
    """Policy DB 상태 조회"""
    pm = get_policy_manager()
    return {
        "institutions": pm.institution.get_all(),
        "policies": pm.settings.get_all(),
        "mapping_count": len(pm.mapper.get_all_mappings())
    }


@app.get("/policy/test-mapping", tags=["Policy"])
async def test_policy_mapping(query: str):
    """쿼리에 대한 공정-장비 매핑 테스트"""
    pm = get_policy_manager()
    categories = pm.mapper.get_categories(query)
    return {
        "query": query,
        "mapped_categories": [c["category"] for c in categories],
        "details": categories[:5]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
