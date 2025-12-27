#!/usr/bin/env python3
"""
KION RAG PoC - 채팅 테스트 스크립트
"""

import httpx
import json

BASE_URL = "http://localhost:8000"


def test_health():
    """헬스 체크"""
    print("=== 헬스 체크 ===")
    response = httpx.get(f"{BASE_URL}/health")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    print()


def test_chat(query: str, filters: dict = None):
    """채팅 테스트"""
    print(f"=== 질의: {query} ===")

    payload = {"query": query}
    if filters:
        payload["filters"] = filters

    response = httpx.post(
        f"{BASE_URL}/chat",
        json=payload,
        timeout=60.0
    )

    result = response.json()
    print(f"처리 시간: {result.get('processing_time', 0)}초")
    print(f"\n{result.get('explanation', '')}\n")

    for rec in result.get("recommendations", []):
        print(f"  [{rec['equipment_id']}] {rec['name']}")
        print(f"    - 카테고리: {rec['category']}")
        print(f"    - 점수: {rec['score']}")
        print(f"    - 이유: {rec['reason']}")
        print()

    print("-" * 50)
    print()


def main():
    print("KION RAG PoC 테스트\n")

    # 헬스 체크
    test_health()

    # 테스트 질의들
    test_cases = [
        "6 inch Si 웨이퍼용 RTA 장비 찾아줘",
        "GaN HEMT 에피 성장용 MOCVD 장비 추천해줘",
        "400도 이상 열처리 가능한 장비",
        "반도체 식각 장비 알려줘",
        "박막 두께 측정 장비",
        "8인치 웨이퍼 지원하는 증착 장비",
    ]

    for query in test_cases:
        try:
            test_chat(query)
        except Exception as e:
            print(f"오류: {e}\n")


if __name__ == "__main__":
    main()
