"""
임베딩 모델 비교 테스트: bge-m3 vs multilingual-e5-large

목적: PRD에서 권장한 bge-m3와 현재 사용 중인 e5-large 성능 비교
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions

# 테스트할 모델들
MODELS = {
    "e5-large": "intfloat/multilingual-e5-large",  # 현재 사용 중
    "bge-m3": "BAAI/bge-m3",                       # PRD 권장
    "ko-sroberta": "jhgan/ko-sroberta-multitask",  # 한국어 특화
}

DATA_DIR = Path(__file__).parent / "data"
EQUIPMENT_FILE = DATA_DIR / "kion_equipment.json"
TEST_QUERIES_FILE = DATA_DIR / "test_queries.json"


def load_equipment() -> List[Dict]:
    """장비 데이터 로드"""
    with open(EQUIPMENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_test_queries() -> List[Dict]:
    """테스트 쿼리 로드"""
    with open(TEST_QUERIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data["test_queries"]


def create_search_text(eq: Dict) -> str:
    """검색용 텍스트 생성"""
    parts = [
        eq.get("name", ""),
        eq.get("name_en", ""),
        eq.get("category", ""),
        eq.get("part", ""),
        eq.get("description", ""),
        " ".join(eq.get("wafer_sizes", [])),
        " ".join(eq.get("materials", [])),
        " ".join(eq.get("tags", [])),
        eq.get("institution", ""),
    ]
    return " ".join(filter(None, parts))


def build_collection(model_name: str, model_path: str, equipments: List[Dict]) -> chromadb.Collection:
    """특정 모델로 벡터 컬렉션 구축"""
    print(f"\n[{model_name}] 모델 로딩 중: {model_path}")
    start = time.time()

    # 임베딩 함수 생성
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_path
    )

    # 메모리 기반 클라이언트 (테스트용)
    client = chromadb.Client()

    collection = client.create_collection(
        name=f"test_{model_name}",
        embedding_function=embedding_fn
    )

    # 장비 데이터 추가
    ids = [eq["equipment_id"] for eq in equipments]
    documents = [create_search_text(eq) for eq in equipments]
    metadatas = [{"name": eq["name"], "category": eq["category"]} for eq in equipments]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    elapsed = time.time() - start
    print(f"[{model_name}] 인덱싱 완료: {len(ids)}개 장비, {elapsed:.2f}초")

    return collection


def search(collection: chromadb.Collection, query: str, top_k: int = 5) -> List[str]:
    """검색 실행"""
    results = collection.query(query_texts=[query], n_results=top_k)
    if results and results["ids"]:
        return results["ids"][0]
    return []


def calculate_recall(retrieved: List[str], expected: List[str], k: int) -> float:
    """Recall@K 계산"""
    if not expected:
        return 1.0  # 기대값이 없으면 성공으로 처리

    retrieved_k = retrieved[:k]
    hits = len(set(retrieved_k) & set(expected))
    return hits / min(len(expected), k)


def run_comparison():
    """비교 테스트 실행"""
    print("=" * 60)
    print("임베딩 모델 비교 테스트")
    print("=" * 60)

    # 데이터 로드
    equipments = load_equipment()
    test_queries = load_test_queries()

    print(f"\n장비 수: {len(equipments)}")
    print(f"테스트 쿼리 수: {len(test_queries)}")

    results = {}

    for model_name, model_path in MODELS.items():
        try:
            # 컬렉션 구축
            collection = build_collection(model_name, model_path, equipments)

            # 테스트 실행
            recall_1_scores = []
            recall_3_scores = []
            search_times = []

            print(f"\n[{model_name}] 테스트 실행 중...")

            for tq in test_queries:
                query = tq["query"]
                expected = tq["expected_ids"]

                start = time.time()
                retrieved = search(collection, query, top_k=5)
                elapsed = time.time() - start

                recall_1 = calculate_recall(retrieved, expected, 1)
                recall_3 = calculate_recall(retrieved, expected, 3)

                recall_1_scores.append(recall_1)
                recall_3_scores.append(recall_3)
                search_times.append(elapsed)

            avg_recall_1 = sum(recall_1_scores) / len(recall_1_scores)
            avg_recall_3 = sum(recall_3_scores) / len(recall_3_scores)
            avg_time = sum(search_times) / len(search_times)

            results[model_name] = {
                "recall@1": avg_recall_1,
                "recall@3": avg_recall_3,
                "avg_search_time": avg_time,
                "details": list(zip(
                    [tq["id"] for tq in test_queries],
                    recall_1_scores,
                    recall_3_scores
                ))
            }

            print(f"[{model_name}] 완료")
            print(f"  - Recall@1: {avg_recall_1:.2%}")
            print(f"  - Recall@3: {avg_recall_3:.2%}")
            print(f"  - 평균 검색 시간: {avg_time*1000:.2f}ms")

        except Exception as e:
            print(f"[{model_name}] 오류 발생: {e}")
            results[model_name] = {"error": str(e)}

    # 결과 비교
    print("\n" + "=" * 60)
    print("비교 결과 요약")
    print("=" * 60)

    print(f"\n{'모델':<20} {'Recall@1':<12} {'Recall@3':<12} {'검색시간':<12}")
    print("-" * 56)

    for model_name, data in results.items():
        if "error" in data:
            print(f"{model_name:<20} {'ERROR':<12}")
        else:
            print(f"{model_name:<20} {data['recall@1']:.2%}        {data['recall@3']:.2%}        {data['avg_search_time']*1000:.2f}ms")

    # 쿼리별 상세 비교 (불일치 케이스)
    print("\n" + "=" * 60)
    print("쿼리별 비교 (두 모델 결과가 다른 경우)")
    print("=" * 60)

    if "e5-large" in results and "bge-m3" in results:
        if "error" not in results["e5-large"] and "error" not in results["bge-m3"]:
            e5_details = {d[0]: (d[1], d[2]) for d in results["e5-large"]["details"]}
            bge_details = {d[0]: (d[1], d[2]) for d in results["bge-m3"]["details"]}

            diff_count = 0
            for qid in e5_details:
                e5_r1, e5_r3 = e5_details[qid]
                bge_r1, bge_r3 = bge_details[qid]

                if e5_r3 != bge_r3:
                    diff_count += 1
                    query_text = next(tq["query"] for tq in test_queries if tq["id"] == qid)
                    winner = "bge-m3" if bge_r3 > e5_r3 else "e5-large" if e5_r3 > bge_r3 else "동점"
                    print(f"\n{qid}: {query_text}")
                    print(f"  e5-large: R@3={e5_r3:.2%}, bge-m3: R@3={bge_r3:.2%} → {winner} 승")

            if diff_count == 0:
                print("\n모든 쿼리에서 동일한 결과!")

    # 결과 저장
    output_file = DATA_DIR / "embedding_comparison_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        # details를 직렬화 가능하게 변환
        save_results = {}
        for k, v in results.items():
            if "error" in v:
                save_results[k] = v
            else:
                save_results[k] = {
                    "recall@1": v["recall@1"],
                    "recall@3": v["recall@3"],
                    "avg_search_time": v["avg_search_time"],
                }
        json.dump(save_results, f, ensure_ascii=False, indent=2)

    print(f"\n결과 저장: {output_file}")

    return results


if __name__ == "__main__":
    run_comparison()
