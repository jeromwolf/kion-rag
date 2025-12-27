"""
KION RAG PoC - RAG Pipeline (ChromaDB + Embeddings)
"""

import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

from .config import settings
from .models import Equipment


class RAGPipeline:
    """RAG 파이프라인 (벡터 검색 + 메타데이터 필터)"""

    def __init__(self):
        self.client = None
        self.collection = None
        self.embedding_fn = None
        self._initialized = False

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

    def get_count(self) -> int:
        """저장된 장비 수 반환"""
        if not self._initialized:
            self.initialize()
        return self.collection.count()

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
