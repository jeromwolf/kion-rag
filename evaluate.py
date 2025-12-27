#!/usr/bin/env python3
"""
KION RAG PoC - 평가 스크립트
Top-3 Recall, 응답 시간, 엣지케이스 평가
"""

import json
import time
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional


BASE_URL = "http://localhost:8000"
DATA_DIR = Path(__file__).parent / "data"


def load_test_queries():
    """테스트 질의 세트 로드"""
    with open(DATA_DIR / "test_queries.json", "r", encoding="utf-8") as f:
        return json.load(f)


def run_single_query(query: str, filters: Optional[dict] = None) -> dict:
    """단일 질의 실행"""
    payload = {"query": query}
    if filters:
        payload["filters"] = filters

    start_time = time.time()
    try:
        response = httpx.post(
            f"{BASE_URL}/chat",
            json=payload,
            timeout=120.0
        )
        end_time = time.time()

        if response.status_code == 200:
            result = response.json()
            result["actual_time"] = end_time - start_time
            return result
        else:
            return {
                "error": f"HTTP {response.status_code}",
                "actual_time": end_time - start_time
            }
    except Exception as e:
        return {
            "error": str(e),
            "actual_time": time.time() - start_time
        }


def calculate_recall_at_k(expected_ids: list, actual_ids: list, k: int = 3) -> float:
    """Top-K Recall 계산"""
    if not expected_ids:
        return 1.0 if not actual_ids else 0.0

    top_k_ids = actual_ids[:k]
    hits = sum(1 for eid in expected_ids if eid in top_k_ids)
    return hits / len(expected_ids)


def evaluate_standard_queries(test_data: dict) -> dict:
    """표준 테스트 질의 평가"""
    results = []
    total_recall_1 = 0
    total_recall_3 = 0
    total_time = 0

    queries = test_data["test_queries"]

    print(f"\n{'='*60}")
    print(f"표준 테스트 질의 평가 ({len(queries)}개)")
    print(f"{'='*60}\n")

    for i, tc in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {tc['id']}: {tc['query'][:40]}...", end=" ")

        response = run_single_query(tc["query"])

        if "error" in response:
            print(f"오류: {response['error']}")
            results.append({
                "id": tc["id"],
                "query": tc["query"],
                "status": "error",
                "error": response["error"],
                "time": response["actual_time"]
            })
            continue

        # 추천 결과에서 장비 ID 추출
        recommendations = response.get("recommendations", [])
        actual_ids = [r["equipment_id"] for r in recommendations]

        # Recall 계산
        recall_1 = calculate_recall_at_k(tc["expected_ids"], actual_ids, k=1)
        recall_3 = calculate_recall_at_k(tc["expected_ids"], actual_ids, k=3)

        total_recall_1 += recall_1
        total_recall_3 += recall_3
        total_time += response["actual_time"]

        # Hit 여부 표시
        hit_status = "HIT" if recall_1 == 1.0 else ("PARTIAL" if recall_3 > 0 else "MISS")
        print(f"{hit_status} (R@1={recall_1:.2f}, R@3={recall_3:.2f}, {response['actual_time']:.1f}s)")

        results.append({
            "id": tc["id"],
            "query": tc["query"],
            "category": tc["category"],
            "difficulty": tc["difficulty"],
            "expected_ids": tc["expected_ids"],
            "actual_ids": actual_ids[:5],
            "recall_at_1": recall_1,
            "recall_at_3": recall_3,
            "time": response["actual_time"],
            "status": hit_status
        })

    # 전체 통계
    n = len(queries)
    stats = {
        "total_queries": n,
        "avg_recall_at_1": total_recall_1 / n if n > 0 else 0,
        "avg_recall_at_3": total_recall_3 / n if n > 0 else 0,
        "avg_response_time": total_time / n if n > 0 else 0,
        "total_time": total_time,
        "hit_count": sum(1 for r in results if r.get("status") == "HIT"),
        "partial_count": sum(1 for r in results if r.get("status") == "PARTIAL"),
        "miss_count": sum(1 for r in results if r.get("status") == "MISS"),
        "error_count": sum(1 for r in results if r.get("status") == "error")
    }

    return {"results": results, "stats": stats}


def evaluate_edge_cases(test_data: dict) -> dict:
    """엣지케이스 평가"""
    results = []
    edge_cases = test_data["edge_cases"]

    print(f"\n{'='*60}")
    print(f"엣지케이스 평가 ({len(edge_cases)}개)")
    print(f"{'='*60}\n")

    for i, ec in enumerate(edge_cases, 1):
        print(f"[{i}/{len(edge_cases)}] {ec['id']}: {ec['query']}")
        print(f"  카테고리: {ec['category']}")
        print(f"  기대 동작: {ec['expected_behavior']}")

        response = run_single_query(ec["query"])

        if "error" in response:
            print(f"  결과: 오류 - {response['error']}\n")
            results.append({
                "id": ec["id"],
                "query": ec["query"],
                "status": "error",
                "error": response["error"]
            })
            continue

        recommendations = response.get("recommendations", [])
        explanation = response.get("explanation", "")[:200]

        print(f"  추천 수: {len(recommendations)}")
        print(f"  응답: {explanation}...")
        print()

        results.append({
            "id": ec["id"],
            "query": ec["query"],
            "category": ec["category"],
            "expected_behavior": ec["expected_behavior"],
            "recommendation_count": len(recommendations),
            "actual_ids": [r["equipment_id"] for r in recommendations[:3]],
            "explanation_snippet": explanation,
            "time": response.get("actual_time", 0)
        })

    return {"results": results}


def evaluate_by_category(standard_results: list) -> dict:
    """카테고리별 성능 분석"""
    category_stats = {}

    for r in standard_results:
        if r.get("status") == "error":
            continue

        cat = r.get("category", "기타")
        if cat not in category_stats:
            category_stats[cat] = {
                "count": 0,
                "recall_1_sum": 0,
                "recall_3_sum": 0,
                "time_sum": 0
            }

        category_stats[cat]["count"] += 1
        category_stats[cat]["recall_1_sum"] += r["recall_at_1"]
        category_stats[cat]["recall_3_sum"] += r["recall_at_3"]
        category_stats[cat]["time_sum"] += r["time"]

    # 평균 계산
    for cat, stats in category_stats.items():
        n = stats["count"]
        stats["avg_recall_1"] = stats["recall_1_sum"] / n if n > 0 else 0
        stats["avg_recall_3"] = stats["recall_3_sum"] / n if n > 0 else 0
        stats["avg_time"] = stats["time_sum"] / n if n > 0 else 0

    return category_stats


def evaluate_by_difficulty(standard_results: list) -> dict:
    """난이도별 성능 분석"""
    difficulty_stats = {}

    for r in standard_results:
        if r.get("status") == "error":
            continue

        diff = r.get("difficulty", "unknown")
        if diff not in difficulty_stats:
            difficulty_stats[diff] = {
                "count": 0,
                "recall_1_sum": 0,
                "recall_3_sum": 0
            }

        difficulty_stats[diff]["count"] += 1
        difficulty_stats[diff]["recall_1_sum"] += r["recall_at_1"]
        difficulty_stats[diff]["recall_3_sum"] += r["recall_at_3"]

    # 평균 계산
    for diff, stats in difficulty_stats.items():
        n = stats["count"]
        stats["avg_recall_1"] = stats["recall_1_sum"] / n if n > 0 else 0
        stats["avg_recall_3"] = stats["recall_3_sum"] / n if n > 0 else 0

    return difficulty_stats


def print_summary(evaluation: dict):
    """평가 결과 요약 출력"""
    stats = evaluation["standard"]["stats"]

    print(f"\n{'='*60}")
    print("평가 결과 요약")
    print(f"{'='*60}")

    print(f"\n[전체 성능]")
    print(f"  총 질의 수: {stats['total_queries']}")
    print(f"  HIT: {stats['hit_count']} | PARTIAL: {stats['partial_count']} | MISS: {stats['miss_count']} | ERROR: {stats['error_count']}")
    print(f"  평균 Recall@1: {stats['avg_recall_at_1']:.2%}")
    print(f"  평균 Recall@3: {stats['avg_recall_at_3']:.2%}")
    print(f"  평균 응답 시간: {stats['avg_response_time']:.2f}초")
    print(f"  총 소요 시간: {stats['total_time']:.1f}초")

    print(f"\n[카테고리별 Recall@3]")
    for cat, cs in evaluation["by_category"].items():
        print(f"  {cat}: {cs['avg_recall_3']:.2%} ({cs['count']}개)")

    print(f"\n[난이도별 Recall@3]")
    for diff, ds in evaluation["by_difficulty"].items():
        print(f"  {diff}: {ds['avg_recall_3']:.2%} ({ds['count']}개)")

    print(f"\n{'='*60}\n")


def save_report(evaluation: dict, output_path: Path):
    """평가 보고서 저장"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_queries": evaluation["standard"]["stats"]["total_queries"],
            "avg_recall_at_1": evaluation["standard"]["stats"]["avg_recall_at_1"],
            "avg_recall_at_3": evaluation["standard"]["stats"]["avg_recall_at_3"],
            "avg_response_time": evaluation["standard"]["stats"]["avg_response_time"],
        },
        "standard_tests": evaluation["standard"],
        "edge_cases": evaluation["edge_cases"],
        "by_category": evaluation["by_category"],
        "by_difficulty": evaluation["by_difficulty"]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"평가 보고서 저장: {output_path}")


def main():
    print("\nKION RAG PoC 평가 시작")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 서버 상태 확인
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=5.0)
        if health.status_code != 200:
            print("서버가 응답하지 않습니다. run.py를 먼저 실행하세요.")
            return
        print(f"서버 상태: {health.json()}")
    except Exception as e:
        print(f"서버 연결 실패: {e}")
        print("run.py를 먼저 실행하세요: python poc/run.py")
        return

    # 테스트 데이터 로드
    test_data = load_test_queries()
    print(f"테스트 질의: {len(test_data['test_queries'])}개")
    print(f"엣지케이스: {len(test_data['edge_cases'])}개")

    # 평가 실행
    evaluation = {}

    # 1. 표준 질의 평가
    evaluation["standard"] = evaluate_standard_queries(test_data)

    # 2. 엣지케이스 평가
    evaluation["edge_cases"] = evaluate_edge_cases(test_data)

    # 3. 카테고리별 분석
    evaluation["by_category"] = evaluate_by_category(evaluation["standard"]["results"])

    # 4. 난이도별 분석
    evaluation["by_difficulty"] = evaluate_by_difficulty(evaluation["standard"]["results"])

    # 결과 요약 출력
    print_summary(evaluation)

    # 보고서 저장
    report_path = DATA_DIR / f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_report(evaluation, report_path)

    print("평가 완료!")


if __name__ == "__main__":
    main()
