"""
KION RAG PoC - Pydantic Models
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# === Equipment Models ===

class Equipment(BaseModel):
    """장비 정보"""
    equipment_id: str = Field(..., description="장비 ID")
    name: str = Field(..., description="장비명 (국문)")
    name_en: Optional[str] = Field(None, description="장비명 (영문)")
    category: str = Field(..., description="장비 카테고리 (증착, 식각, 측정 등)")
    part: str = Field(..., description="공정 파트 (Front-end, Back-end 등)")
    wafer_sizes: List[str] = Field(default_factory=list, description="지원 웨이퍼 사이즈")
    materials: List[str] = Field(default_factory=list, description="지원 재료/기판")
    temp_min: Optional[float] = Field(None, description="최소 온도 (℃)")
    temp_max: Optional[float] = Field(None, description="최대 온도 (℃)")
    description: str = Field(..., description="장비 설명")
    tags: List[str] = Field(default_factory=list, description="태그")
    institution: str = Field(..., description="보유 기관")
    location: Optional[str] = Field(None, description="위치")
    reservation_url: Optional[str] = Field(None, description="예약 URL")


# === API Request/Response Models ===

class ChatRequest(BaseModel):
    """채팅 요청"""
    query: str = Field(..., description="사용자 질의", min_length=1)
    filters: Optional[Dict[str, Any]] = Field(None, description="필터 조건")
    top_k: Optional[int] = Field(5, description="추천 장비 수", ge=1, le=10)
    session_id: Optional[str] = Field(None, description="대화 세션 ID (연계 질의용)")


class RecommendedEquipment(BaseModel):
    """추천 장비"""
    equipment_id: str
    name: str
    category: str
    score: float = Field(..., description="유사도 점수")
    reason: str = Field(..., description="추천 이유")
    reservation_url: Optional[str] = None
    institution: Optional[str] = None
    wafer_sizes: Optional[List[str]] = None
    materials: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """채팅 응답"""
    query: str = Field(..., description="원본 질의")
    recommendations: List[RecommendedEquipment] = Field(..., description="추천 장비 목록")
    explanation: str = Field(..., description="종합 설명")
    processing_time: float = Field(..., description="처리 시간 (초)")
    session_id: Optional[str] = Field(None, description="대화 세션 ID")
    turn_count: Optional[int] = Field(None, description="대화 턴 수")


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    version: str
    ollama_status: str
    chroma_status: str
    equipment_count: int
