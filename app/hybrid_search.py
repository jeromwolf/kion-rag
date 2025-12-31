"""
KION RAG - Hybrid Search (BM25 + Vector Search)

하이브리드 검색: 키워드 기반(BM25) + 시멘틱(벡터) 검색 결합
- 기술 용어, 스펙 검색에 강한 BM25
- 의미 기반 검색에 강한 벡터 검색
- 두 결과를 결합하여 최종 순위 결정
"""

from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
import re
from collections import defaultdict


class HybridSearcher:
    """하이브리드 검색 (BM25 + Vector)"""

    def __init__(self):
        self.bm25 = None
        self.documents = []  # 원본 문서 (토큰화 전)
        self.doc_ids = []    # 문서 ID
        self.doc_metadata = {}  # ID -> metadata
        self.tokenized_docs = []  # 토큰화된 문서
        self._initialized = False

    def initialize(self, documents: List[Dict[str, Any]]) -> None:
        """
        BM25 인덱스 초기화

        Args:
            documents: [{"id": "...", "text": "...", "metadata": {...}}, ...]
        """
        self.documents = []
        self.doc_ids = []
        self.doc_metadata = {}
        self.tokenized_docs = []

        for doc in documents:
            doc_id = doc.get("id", "")
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})

            self.doc_ids.append(doc_id)
            self.documents.append(text)
            self.doc_metadata[doc_id] = metadata

            # 토큰화 (한국어 + 영어 + 숫자 + 특수 단위)
            tokens = self._tokenize(text)
            self.tokenized_docs.append(tokens)

        # BM25 인덱스 생성
        if self.tokenized_docs:
            self.bm25 = BM25Okapi(self.tokenized_docs)

        self._initialized = True
        print(f"[HybridSearch] Initialized with {len(self.doc_ids)} documents")

    def _tokenize(self, text: str) -> List[str]:
        """
        텍스트 토큰화 (기술 용어 보존)

        - 숫자+단위 보존 (6inch, 400℃, 5nm 등)
        - 영문 약어 보존 (MOCVD, RTA, PECVD 등)
        - 한글 단어 분리
        """
        if not text:
            return []

        text = text.lower()

        # 특수 패턴 보존 (숫자+단위)
        # 6 inch -> 6inch, 400 ℃ -> 400℃
        text = re.sub(r'(\d+)\s*(inch|인치|nm|um|mm|cm|℃|도|°c|°)', r'\1\2', text)

        # 토큰 분리
        # 영문, 숫자+단위, 한글 단어 추출
        tokens = re.findall(r'[a-zA-Z]+[\d]*|[\d]+[a-zA-Z℃°]+|[가-힣]+', text)

        # 불용어 제거
        stopwords = {'의', '가', '이', '은', '는', '을', '를', '에', '에서', '로', '으로',
                     '와', '과', '도', '만', '까지', 'the', 'a', 'an', 'is', 'are', 'for'}
        tokens = [t for t in tokens if t not in stopwords and len(t) > 1]

        return tokens

    def search_bm25(self, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        """
        BM25 키워드 검색

        Returns:
            [{"id": "...", "score": 0.85, "metadata": {...}}, ...]
        """
        if not self._initialized or not self.bm25:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # BM25 점수 계산
        scores = self.bm25.get_scores(query_tokens)

        # 결과 정렬
        scored_docs = list(zip(self.doc_ids, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        # 상위 K개 반환
        results = []
        max_score = max(scores) if scores.any() else 1

        for doc_id, score in scored_docs[:top_k]:
            if score > 0:  # 0점 제외
                normalized_score = score / max_score if max_score > 0 else 0
                results.append({
                    "id": doc_id,
                    "bm25_score": round(normalized_score, 4),
                    "metadata": self.doc_metadata.get(doc_id, {})
                })

        return results

    def hybrid_search(
        self,
        query: str,
        vector_results: List[Dict[str, Any]],
        top_k: int = 10,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        하이브리드 검색 (BM25 + Vector 결합)

        Args:
            query: 검색 쿼리
            vector_results: 벡터 검색 결과 [{"equipment_id": "...", "score": 0.9, ...}, ...]
            top_k: 반환할 결과 수
            vector_weight: 벡터 검색 가중치 (기본 0.5)
            bm25_weight: BM25 가중치 (기본 0.5)

        Returns:
            결합된 결과 (hybrid_score 포함)
        """
        # BM25 검색
        bm25_results = self.search_bm25(query, top_k=top_k * 2)

        # 결과 통합을 위한 딕셔너리
        combined = defaultdict(lambda: {
            "vector_score": 0,
            "bm25_score": 0,
            "data": None
        })

        # 벡터 검색 결과 추가
        for item in vector_results:
            eq_id = item.get("equipment_id", "")
            combined[eq_id]["vector_score"] = item.get("score", 0)
            combined[eq_id]["data"] = item

        # BM25 결과 추가
        for item in bm25_results:
            eq_id = item.get("id", "")
            combined[eq_id]["bm25_score"] = item.get("bm25_score", 0)
            if combined[eq_id]["data"] is None:
                # 벡터 검색에 없던 항목 (BM25에서만 발견)
                combined[eq_id]["data"] = {
                    "equipment_id": eq_id,
                    **item.get("metadata", {})
                }

        # 하이브리드 점수 계산
        results = []
        for eq_id, scores in combined.items():
            if scores["data"] is None:
                continue

            hybrid_score = (
                scores["vector_score"] * vector_weight +
                scores["bm25_score"] * bm25_weight
            )

            result = scores["data"].copy()
            result["hybrid_score"] = round(hybrid_score, 4)
            result["vector_score"] = round(scores["vector_score"], 4)
            result["bm25_score"] = round(scores["bm25_score"], 4)

            # 기존 score를 hybrid_score로 대체
            result["score"] = result["hybrid_score"]

            results.append(result)

        # 하이브리드 점수로 정렬
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)

        return results[:top_k]

    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> None:
        """단일 문서 추가 (인덱스 재구축 필요)"""
        self.doc_ids.append(doc_id)
        self.documents.append(text)
        self.doc_metadata[doc_id] = metadata or {}
        self.tokenized_docs.append(self._tokenize(text))

        # BM25 재구축
        if self.tokenized_docs:
            self.bm25 = BM25Okapi(self.tokenized_docs)

    def rebuild_index(self) -> None:
        """BM25 인덱스 재구축"""
        if self.tokenized_docs:
            self.bm25 = BM25Okapi(self.tokenized_docs)
            print(f"[HybridSearch] Index rebuilt with {len(self.doc_ids)} documents")


# 싱글톤 인스턴스
hybrid_searcher = HybridSearcher()
