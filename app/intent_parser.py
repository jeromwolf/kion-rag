"""
KION RAG - LLM 기반 의도 파악 (Intent Parser)

복잡한 질의 처리:
- 복합 질의: "A 공정과 B 공정 장비 둘 다"
- 부정문: "800도 장비는 아니였으면"
- OR 조건: "이 조건이거나 저 조건"
- 추상적 질의: "이런 상황에서 활용할 장비"
"""

import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import ollama
from .config import settings


@dataclass
class ParsedIntent:
    """파싱된 의도 결과"""
    query_type: str = "simple"  # simple, compound, negative, abstract
    intent: str = "equipment_search"  # equipment_search, comparison, general_question

    # 추출된 조건
    wafer_sizes: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    processes: List[str] = field(default_factory=list)

    # 온도 조건
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None

    # 부정 조건 (제외할 것)
    exclude_materials: List[str] = field(default_factory=list)
    exclude_categories: List[str] = field(default_factory=list)
    exclude_temp_min: Optional[float] = None
    exclude_temp_max: Optional[float] = None

    # 기관
    institution: Optional[str] = None

    # OR 조건 (여러 조건 중 하나)
    or_conditions: List[Dict[str, Any]] = field(default_factory=list)

    # 원본 쿼리
    original_query: str = ""

    # 검색용 쿼리 (LLM이 정제한)
    search_query: str = ""

    # 신뢰도
    confidence: float = 0.0


INTENT_PROMPT = """당신은 반도체/디스플레이 장비 검색 시스템의 의도 파악 모듈입니다.
사용자의 질의를 분석하여 JSON 형태로 구조화된 정보를 추출하세요.

## 추출해야 할 정보:
1. query_type: 질의 유형
   - "simple": 단순 검색 (예: "MOCVD 장비 추천해줘")
   - "compound": 복합 조건 (예: "A와 B 둘 다", "A 또는 B")
   - "negative": 부정 조건 포함 (예: "~가 아닌", "~없는", "~제외")
   - "abstract": 추상적 질의 (예: "이런 상황에서", "어떤 장비가 좋을까")

2. intent: 사용자 의도
   - "equipment_search": 장비 검색/추천
   - "comparison": 장비 비교
   - "general_question": 일반 질문

3. 조건 추출:
   - wafer_sizes: 웨이퍼 사이즈 (예: ["6 inch", "8 inch"])
   - materials: 재료 (예: ["Si", "GaN", "GaAs"])
   - categories: 장비 카테고리 (예: ["증착", "열처리", "식각"])
   - processes: 공정 (예: ["MOCVD", "RTA", "PECVD"])
   - temp_min, temp_max: 온도 범위
   - institution: 기관명

4. 부정 조건 (제외할 것):
   - exclude_materials: 제외할 재료
   - exclude_categories: 제외할 카테고리
   - exclude_temp_min, exclude_temp_max: 제외할 온도 범위

5. search_query: 검색에 사용할 정제된 쿼리

## 예시:

입력: "6인치 Si 웨이퍼용 RTA 장비 찾아줘"
출력:
{
  "query_type": "simple",
  "intent": "equipment_search",
  "wafer_sizes": ["6 inch"],
  "materials": ["Si"],
  "processes": ["RTA"],
  "categories": ["열처리"],
  "search_query": "6인치 Si RTA 열처리 장비"
}

입력: "800도 이하로만 동작하는 열처리 장비"
출력:
{
  "query_type": "negative",
  "intent": "equipment_search",
  "categories": ["열처리"],
  "temp_max": 800,
  "exclude_temp_min": 800,
  "search_query": "800도 이하 열처리 장비"
}

입력: "MOCVD랑 PECVD 장비 둘 다 추천해줘"
출력:
{
  "query_type": "compound",
  "intent": "equipment_search",
  "processes": ["MOCVD", "PECVD"],
  "categories": ["증착"],
  "or_conditions": [{"process": "MOCVD"}, {"process": "PECVD"}],
  "search_query": "MOCVD PECVD 증착 장비"
}

입력: "GaN 에피 성장하려는데 어떤 장비가 좋을까?"
출력:
{
  "query_type": "abstract",
  "intent": "equipment_search",
  "materials": ["GaN"],
  "processes": ["에피택시", "MOCVD"],
  "categories": ["증착"],
  "search_query": "GaN 에피택시 MOCVD 증착 장비"
}

## 사용자 질의:
{query}

## JSON 응답 (반드시 유효한 JSON만 출력):
"""


def parse_intent_with_llm(query: str) -> ParsedIntent:
    """
    LLM을 사용하여 질의 의도 파악

    Args:
        query: 사용자 질의

    Returns:
        ParsedIntent 객체
    """
    result = ParsedIntent(original_query=query, search_query=query)

    try:
        # LLM 호출
        response = ollama.generate(
            model=settings.OLLAMA_MODEL,
            prompt=INTENT_PROMPT.format(query=query),
            options={
                "temperature": 0.1,  # 낮은 온도로 일관된 출력
                "num_predict": 500,
            }
        )

        response_text = response.get("response", "")

        # JSON 추출 (중첩 객체 포함)
        # 방법 1: 가장 바깥 {} 찾기
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            json_str = json_match.group()
            # 중첩된 {} 처리를 위해 마지막 } 위치 조정
            brace_count = 0
            end_pos = 0
            for i, c in enumerate(json_str):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break
            json_str = json_str[:end_pos]
            parsed = json.loads(json_str)

            # 결과 매핑
            result.query_type = parsed.get("query_type", "simple")
            result.intent = parsed.get("intent", "equipment_search")
            result.wafer_sizes = parsed.get("wafer_sizes", [])
            result.materials = parsed.get("materials", [])
            result.categories = parsed.get("categories", [])
            result.processes = parsed.get("processes", [])
            result.temp_min = parsed.get("temp_min")
            result.temp_max = parsed.get("temp_max")
            result.exclude_materials = parsed.get("exclude_materials", [])
            result.exclude_categories = parsed.get("exclude_categories", [])
            result.exclude_temp_min = parsed.get("exclude_temp_min")
            result.exclude_temp_max = parsed.get("exclude_temp_max")
            result.institution = parsed.get("institution")
            result.or_conditions = parsed.get("or_conditions", [])
            result.search_query = parsed.get("search_query", query)
            result.confidence = 0.9

            print(f"[IntentParser] Type: {result.query_type}, Intent: {result.intent}")
            print(f"[IntentParser] Conditions: wafer={result.wafer_sizes}, materials={result.materials}, categories={result.categories}")
            if result.exclude_temp_min or result.exclude_temp_max:
                print(f"[IntentParser] Exclude: temp_min={result.exclude_temp_min}, temp_max={result.exclude_temp_max}")

    except json.JSONDecodeError as e:
        print(f"[IntentParser] JSON parse error: {e}")
        result.confidence = 0.5
    except Exception as e:
        print(f"[IntentParser] Error: {e}")
        result.confidence = 0.3

    return result


def apply_intent_filters(
    results: List[Dict[str, Any]],
    intent: ParsedIntent
) -> List[Dict[str, Any]]:
    """
    의도 기반 필터 적용 (부정 조건, OR 조건 등)

    Args:
        results: 검색 결과
        intent: 파싱된 의도

    Returns:
        필터링된 결과
    """
    if not results:
        return results

    filtered = []

    for item in results:
        include = True

        # 부정 온도 조건 적용
        if intent.exclude_temp_min is not None:
            temp_min = item.get("temp_min", 0)
            if temp_min and temp_min >= intent.exclude_temp_min:
                include = False

        if intent.exclude_temp_max is not None:
            temp_max = item.get("temp_max", 9999)
            if temp_max and temp_max <= intent.exclude_temp_max:
                include = False

        # 부정 재료 조건
        if intent.exclude_materials:
            item_materials = item.get("materials", [])
            if isinstance(item_materials, str):
                item_materials = item_materials.split(",")
            for excl in intent.exclude_materials:
                if excl.lower() in [m.lower() for m in item_materials]:
                    include = False
                    break

        # 부정 카테고리 조건
        if intent.exclude_categories:
            item_category = item.get("category", "").lower()
            for excl in intent.exclude_categories:
                if excl.lower() in item_category:
                    include = False
                    break

        if include:
            # OR 조건 처리 - 하나라도 만족하면 점수 부스트
            if intent.or_conditions:
                boost = 0
                for cond in intent.or_conditions:
                    if "process" in cond:
                        if cond["process"].lower() in item.get("name", "").lower():
                            boost += 0.1
                    if "category" in cond:
                        if cond["category"].lower() in item.get("category", "").lower():
                            boost += 0.1
                if boost > 0:
                    item["score"] = min(1.0, item.get("score", 0.5) + boost)

            filtered.append(item)

    # 부정 조건으로 필터링된 경우 로그
    if len(filtered) < len(results):
        print(f"[IntentParser] Filtered: {len(results)} -> {len(filtered)} (excluded by negative conditions)")

    return filtered


def quick_intent_check(query: str) -> Dict[str, Any]:
    """
    빠른 의도 확인 (LLM 없이 규칙 기반)

    복잡한 질의인지 빠르게 판단하여 LLM 호출 여부 결정
    """
    query_lower = query.lower()

    # 부정 패턴
    negative_patterns = [
        r'아니[였었]',
        r'제외',
        r'없[는이]',
        r'빼고',
        r'말고',
        r'이하로?만',
        r'미만',
        r'안\s?되',
    ]

    # 복합 패턴
    compound_patterns = [
        r'[과와랑].*둘\s?다',
        r'이거나|또는',
        r'[과와랑].*함께',
        r'동시에',
    ]

    # 추상적 패턴
    abstract_patterns = [
        r'어떤.*좋을까',
        r'뭐가\s?있',
        r'추천.*해\s?줘',
        r'상황에서',
    ]

    is_negative = any(re.search(p, query_lower) for p in negative_patterns)
    is_compound = any(re.search(p, query_lower) for p in compound_patterns)
    is_abstract = any(re.search(p, query_lower) for p in abstract_patterns)

    return {
        "needs_llm_parsing": is_negative or is_compound or is_abstract,
        "is_negative": is_negative,
        "is_compound": is_compound,
        "is_abstract": is_abstract
    }
