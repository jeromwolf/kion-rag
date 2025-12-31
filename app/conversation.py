"""
KION RAG - 대화 이력 관리 (Conversation Manager)

연계 질의 처리:
- "그럼 이 조건은?" → 이전 질의의 조건 유지
- "6인치로 바꿔줘" → 이전 추천 결과에서 웨이퍼만 변경
- "더 싼 장비는?" → 이전 카테고리 유지
"""

import time
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import OrderedDict


@dataclass
class ConversationTurn:
    """대화 턴 (질의-응답 쌍)"""
    query: str
    response_summary: str  # 추천 장비 요약
    extracted_conditions: Dict[str, Any] = field(default_factory=dict)
    recommended_ids: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationSession:
    """대화 세션"""
    session_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def add_turn(self, turn: ConversationTurn) -> None:
        """턴 추가"""
        self.turns.append(turn)
        self.last_accessed = time.time()

    def get_last_conditions(self) -> Dict[str, Any]:
        """마지막 턴의 조건 반환"""
        if self.turns:
            return self.turns[-1].extracted_conditions.copy()
        return {}

    def get_last_recommendations(self) -> List[str]:
        """마지막 턴의 추천 장비 ID 반환"""
        if self.turns:
            return self.turns[-1].recommended_ids.copy()
        return []

    def get_context_summary(self, max_turns: int = 3) -> str:
        """최근 대화 컨텍스트 요약"""
        if not self.turns:
            return ""

        recent = self.turns[-max_turns:]
        summaries = []
        for i, turn in enumerate(recent):
            summaries.append(f"[{i+1}] 질의: {turn.query}")
            if turn.response_summary:
                summaries.append(f"    응답: {turn.response_summary}")

        return "\n".join(summaries)


class ConversationManager:
    """대화 세션 관리자"""

    def __init__(self, max_sessions: int = 1000, session_ttl: int = 3600):
        """
        Args:
            max_sessions: 최대 세션 수 (LRU)
            session_ttl: 세션 TTL (초, 기본 1시간)
        """
        self.sessions: OrderedDict[str, ConversationSession] = OrderedDict()
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl

    def create_session(self) -> str:
        """새 세션 생성"""
        session_id = str(uuid.uuid4())[:8]  # 짧은 ID
        self.sessions[session_id] = ConversationSession(session_id=session_id)
        self._cleanup_old_sessions()
        return session_id

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """세션 조회"""
        session = self.sessions.get(session_id)
        if session:
            # TTL 체크
            if time.time() - session.last_accessed > self.session_ttl:
                del self.sessions[session_id]
                return None
            # LRU 업데이트
            self.sessions.move_to_end(session_id)
            session.last_accessed = time.time()
        return session

    def get_or_create_session(self, session_id: Optional[str]) -> ConversationSession:
        """세션 조회 또는 생성"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        new_id = self.create_session()
        return self.sessions[new_id]

    def add_turn(
        self,
        session_id: str,
        query: str,
        response_summary: str,
        extracted_conditions: Dict[str, Any],
        recommended_ids: List[str]
    ) -> None:
        """대화 턴 추가"""
        session = self.get_session(session_id)
        if session:
            turn = ConversationTurn(
                query=query,
                response_summary=response_summary,
                extracted_conditions=extracted_conditions,
                recommended_ids=recommended_ids
            )
            session.add_turn(turn)

    def _cleanup_old_sessions(self) -> None:
        """오래된 세션 정리 (LRU + TTL)"""
        current_time = time.time()

        # TTL 만료 세션 제거
        expired = [
            sid for sid, session in self.sessions.items()
            if current_time - session.last_accessed > self.session_ttl
        ]
        for sid in expired:
            del self.sessions[sid]

        # 최대 세션 수 초과시 오래된 것 제거
        while len(self.sessions) > self.max_sessions:
            self.sessions.popitem(last=False)


# 연계 질의 패턴 감지
FOLLOWUP_PATTERNS = [
    # 조건 변경
    (r'(그럼|그러면)\s*(이|저)\s*조건', 'condition_change'),
    (r'(대신|말고)\s*(.+)(으로|로)\s*(바꿔|변경)', 'condition_replace'),
    (r'(.+)(으로|로)\s*(바꿔|변경)', 'condition_replace'),

    # 이전 결과 참조
    (r'(그|저|이)\s*장비', 'reference_previous'),
    (r'첫\s*번째|두\s*번째|세\s*번째', 'reference_previous'),
    (r'맨\s*(위|아래|처음|마지막)', 'reference_previous'),

    # 추가 조건
    (r'(거기에|추가로|더)\s*(.+)(도|만)', 'add_condition'),
    (r'(비슷한|유사한)\s*(다른|장비)', 'similar_request'),

    # 비교/평가
    (r'(더|가장)\s*(싼|비싼|좋은|빠른)', 'comparison'),
    (r'(차이|비교)', 'comparison'),

    # 범위 조정
    (r'(더|좀)\s*(넓|좁)(게|히|혀)', 'adjust_range'),
]


def detect_followup_intent(query: str) -> Dict[str, Any]:
    """
    연계 질의 의도 감지

    Returns:
        {
            "is_followup": bool,
            "intent_type": str,
            "confidence": float
        }
    """
    import re

    query_lower = query.lower()

    for pattern, intent_type in FOLLOWUP_PATTERNS:
        if re.search(pattern, query_lower):
            return {
                "is_followup": True,
                "intent_type": intent_type,
                "confidence": 0.8
            }

    # 짧은 질의는 후속 질의일 가능성 높음
    if len(query) < 20 and any(kw in query for kw in ['이거', '저거', '그거', '이건', '그건']):
        return {
            "is_followup": True,
            "intent_type": "reference_previous",
            "confidence": 0.6
        }

    return {
        "is_followup": False,
        "intent_type": None,
        "confidence": 0.0
    }


def merge_with_previous_conditions(
    current_conditions: Dict[str, Any],
    previous_conditions: Dict[str, Any],
    followup_intent: Dict[str, Any]
) -> Dict[str, Any]:
    """
    현재 조건과 이전 조건 병합

    Args:
        current_conditions: 현재 질의에서 추출된 조건
        previous_conditions: 이전 턴의 조건
        followup_intent: 연계 의도 분석 결과

    Returns:
        병합된 조건
    """
    intent_type = followup_intent.get("intent_type")

    if not followup_intent.get("is_followup"):
        # 연계 질의가 아니면 현재 조건만 사용
        return current_conditions

    merged = previous_conditions.copy()

    if intent_type == "condition_replace":
        # 조건 교체: 현재 조건으로 덮어쓰기
        merged.update(current_conditions)

    elif intent_type == "add_condition":
        # 조건 추가: 현재 조건 추가
        for key, value in current_conditions.items():
            if key in merged and isinstance(merged[key], list):
                merged[key] = list(set(merged[key] + value))
            elif value:
                merged[key] = value

    elif intent_type in ["reference_previous", "similar_request"]:
        # 이전 결과 참조: 이전 조건 유지, 현재 조건으로 필터링
        for key, value in current_conditions.items():
            if value:
                merged[key] = value

    elif intent_type == "comparison":
        # 비교: 이전 카테고리/조건 유지
        if current_conditions.get("categories"):
            merged["categories"] = current_conditions["categories"]
        else:
            # 이전 카테고리 유지
            pass

    elif intent_type == "condition_change":
        # 조건 변경: 명시된 조건만 변경
        for key, value in current_conditions.items():
            if value:
                merged[key] = value

    else:
        # 기본: 이전 조건에 현재 조건 오버라이드
        merged.update({k: v for k, v in current_conditions.items() if v})

    return merged


# 싱글톤 인스턴스
conversation_manager = ConversationManager()
