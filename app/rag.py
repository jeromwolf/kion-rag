"""
KION RAG PoC - RAG Pipeline (ChromaDB + Embeddings + Hybrid Search)
"""

import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

from .config import settings
from .models import Equipment
from .hybrid_search import hybrid_searcher


class RAGPipeline:
    """RAG 파이프라인 (벡터 검색 + BM25 하이브리드)"""

    def __init__(self):
        self.client = None
        self.collection = None
        self.embedding_fn = None
        self._initialized = False
        self._hybrid_initialized = False

    def initialize(self):
        """RAG 파이프라인 초기화"""
        if self._initialized:
            return

        # ChromaDB 클라이언트 생성
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(persist_dir))

        # 임베딩 함수 설정 (multilingual-e5-large)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )

        # 컬렉션 가져오기 또는 생성
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "KION 팹서비스 장비 데이터"}
        )

        self._initialized = True
        print(f"[RAG] Initialized. Collection: {settings.CHROMA_COLLECTION_NAME}, Documents: {self.collection.count()}")

    def add_equipment(self, equipment: Equipment) -> None:
        """장비 데이터 추가"""
        if not self._initialized:
            self.initialize()

        # 검색용 텍스트 생성
        search_text = self._create_search_text(equipment)

        # 메타데이터 생성
        metadata = {
            "equipment_id": equipment.equipment_id,
            "name": equipment.name,
            "category": equipment.category,
            "part": equipment.part,
            "wafer_sizes": ",".join(equipment.wafer_sizes),
            "materials": ",".join(equipment.materials),
            "temp_min": equipment.temp_min or 0,
            "temp_max": equipment.temp_max or 9999,
            "institution": equipment.institution,
            "tags": ",".join(equipment.tags),
        }

        # ChromaDB에 추가
        self.collection.upsert(
            ids=[equipment.equipment_id],
            documents=[search_text],
            metadatas=[metadata]
        )

    def add_equipments_batch(self, equipments: List[Equipment]) -> int:
        """장비 데이터 일괄 추가"""
        if not self._initialized:
            self.initialize()

        ids = []
        documents = []
        metadatas = []

        for eq in equipments:
            ids.append(eq.equipment_id)
            documents.append(self._create_search_text(eq))
            metadatas.append({
                "equipment_id": eq.equipment_id,
                "name": eq.name,
                "name_en": eq.name_en or "",
                "category": eq.category,
                "part": eq.part,
                "wafer_sizes": ",".join(eq.wafer_sizes),
                "materials": ",".join(eq.materials),
                "temp_min": eq.temp_min or 0,
                "temp_max": eq.temp_max or 9999,
                "institution": eq.institution,
                "location": eq.location or "",
                "tags": ",".join(eq.tags),
                "reservation_url": eq.reservation_url or "",
                "description": eq.description[:500],  # 설명은 500자 제한
            })

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )

        return len(ids)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        장비 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            filters: 메타데이터 필터 (예: {"category": "증착"})

        Returns:
            검색된 장비 리스트
        """
        if not self._initialized:
            self.initialize()

        # ChromaDB where 필터 구성
        where_filter = None
        if filters:
            where_conditions = []
            for key, value in filters.items():
                if key == "wafer_size" and value:
                    # 웨이퍼 사이즈는 포함 여부로 검색
                    where_conditions.append({"wafer_sizes": {"$contains": value}})
                elif key == "material" and value:
                    where_conditions.append({"materials": {"$contains": value}})
                elif key == "temp_min" and value:
                    where_conditions.append({"temp_max": {"$gte": float(value)}})
                elif key == "temp_max" and value:
                    where_conditions.append({"temp_min": {"$lte": float(value)}})
                elif key == "category" and value:
                    where_conditions.append({"category": {"$eq": value}})
                elif key == "institution" and value:
                    where_conditions.append({"institution": {"$eq": value}})

            if len(where_conditions) == 1:
                where_filter = where_conditions[0]
            elif len(where_conditions) > 1:
                where_filter = {"$and": where_conditions}

        # 검색 실행
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )

        # 결과 포맷팅
        equipments = []
        if results and results["ids"] and results["ids"][0]:
            for i, eq_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0

                # 유사도 점수 계산 (거리 → 유사도)
                similarity = max(0, 1 - distance / 2)

                equipments.append({
                    "equipment_id": eq_id,
                    "name": metadata.get("name", ""),
                    "name_en": metadata.get("name_en", ""),
                    "category": metadata.get("category", ""),
                    "part": metadata.get("part", ""),
                    "wafer_sizes": metadata.get("wafer_sizes", "").split(",") if metadata.get("wafer_sizes") else [],
                    "materials": metadata.get("materials", "").split(",") if metadata.get("materials") else [],
                    "temp_min": metadata.get("temp_min"),
                    "temp_max": metadata.get("temp_max"),
                    "institution": metadata.get("institution", ""),
                    "location": metadata.get("location", ""),
                    "description": metadata.get("description", ""),
                    "tags": metadata.get("tags", "").split(",") if metadata.get("tags") else [],
                    "reservation_url": metadata.get("reservation_url", ""),
                    "score": round(similarity, 4),
                })

        return equipments

    def initialize_hybrid_search(self) -> None:
        """하이브리드 검색을 위한 BM25 인덱스 초기화"""
        if not self._initialized:
            self.initialize()

        # ChromaDB에서 모든 문서 가져오기
        all_docs = self.collection.get(include=["documents", "metadatas"])

        if not all_docs or not all_docs.get("ids"):
            print("[RAG] No documents to initialize hybrid search")
            return

        # BM25용 문서 구성
        documents = []
        for i, doc_id in enumerate(all_docs["ids"]):
            text = all_docs["documents"][i] if all_docs.get("documents") else ""
            metadata = all_docs["metadatas"][i] if all_docs.get("metadatas") else {}

            documents.append({
                "id": doc_id,
                "text": text,
                "metadata": metadata
            })

        # 하이브리드 검색 초기화
        hybrid_searcher.initialize(documents)
        self._hybrid_initialized = True
        print(f"[RAG] Hybrid search initialized with {len(documents)} documents")

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        하이브리드 검색 (BM25 + 벡터)

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            filters: 메타데이터 필터
            vector_weight: 벡터 검색 가중치 (기본 0.5)
            bm25_weight: BM25 가중치 (기본 0.5)

        Returns:
            hybrid_score가 포함된 검색 결과
        """
        if not self._initialized:
            self.initialize()

        if not self._hybrid_initialized:
            self.initialize_hybrid_search()

        # 1. 벡터 검색 (더 많이 가져옴)
        vector_results = self.search(
            query=query,
            top_k=top_k * 2,
            filters=filters
        )

        # 2. 하이브리드 결합
        hybrid_results = hybrid_searcher.hybrid_search(
            query=query,
            vector_results=vector_results,
            top_k=top_k,
            vector_weight=vector_weight,
            bm25_weight=bm25_weight
        )

        return hybrid_results

    def get_count(self) -> int:
        """저장된 장비 수 반환"""
        if not self._initialized:
            self.initialize()
        return self.collection.count()

    def get_all(self) -> list:
        """모든 장비 메타데이터 반환"""
        if not self._initialized:
            self.initialize()
        results = self.collection.get()
        equipment_list = []
        if results and results.get("ids"):
            for i, eq_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results.get("metadatas") else {}
                equipment_list.append({
                    "id": eq_id,
                    "name": meta.get("name", ""),
                    "category": meta.get("category", ""),
                    "part": meta.get("part", ""),
                    "institution": meta.get("institution", ""),
                })
        return equipment_list

    def clear(self) -> None:
        """모든 데이터 삭제"""
        if not self._initialized:
            self.initialize()
        # 컬렉션 삭제 후 재생성
        self.client.delete_collection(settings.CHROMA_COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"description": "KION 팹서비스 장비 데이터"}
        )

    def _create_search_text(self, equipment: Equipment) -> str:
        """검색용 텍스트 생성"""
        parts = [
            equipment.name,
            equipment.name_en or "",
            equipment.category,
            equipment.part,
            equipment.description,
            " ".join(equipment.wafer_sizes),
            " ".join(equipment.materials),
            " ".join(equipment.tags),
            equipment.institution,
        ]
        return " ".join(filter(None, parts))


# 싱글톤 인스턴스
rag_pipeline = RAGPipeline()
