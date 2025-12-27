"""
KION RAG PoC - Query Parser
정규식 기반 파라미터 추출 및 용어 정규화
필터 룰은 외부 JSON 파일에서 로드
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ParsedQuery:
    """파싱된 쿼리 결과"""
    original: str
    normalized: str
    wafer_sizes: List[str] = field(default_factory=list)
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    materials: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    institutions: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


# === 필터 룰 로드 ===
FILTER_RULES_PATH = Path(__file__).parent.parent / "data" / "filter_rules.json"

def load_filter_rules() -> Dict[str, Any]:
    """filter_rules.json에서 룰 로드"""
    try:
        with open(FILTER_RULES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[Warning] filter_rules.json not found at {FILTER_RULES_PATH}, using defaults")
        return {}
    except json.JSONDecodeError as e:
        print(f"[Warning] filter_rules.json parse error: {e}, using defaults")
        return {}

# 룰 로드 (모듈 로드 시 한번만)
_rules = load_filter_rules()

# 기본값 (JSON 로드 실패 시 폴백)
DEFAULT_VALID_WAFER_SIZES = ["2 inch", "3 inch", "4 inch", "6 inch", "8 inch", "12 inch"]
DEFAULT_MM_TO_INCH = {
    "50mm": "2 inch", "75mm": "3 inch", "100mm": "4 inch",
    "150mm": "6 inch", "200mm": "8 inch", "300mm": "12 inch"
}
DEFAULT_HIGH_TEMP = 500
DEFAULT_LOW_TEMP = 200

# JSON에서 룰 추출 (또는 기본값 사용)
VALID_WAFER_SIZES = _rules.get("wafer_sizes", {}).get("valid_sizes", DEFAULT_VALID_WAFER_SIZES)
MM_TO_INCH = _rules.get("wafer_sizes", {}).get("mm_to_inch", DEFAULT_MM_TO_INCH)
TEMP_CONFIG = _rules.get("temperature", {})
HIGH_TEMP_THRESHOLD = TEMP_CONFIG.get("high_temp_threshold", DEFAULT_HIGH_TEMP)
LOW_TEMP_THRESHOLD = TEMP_CONFIG.get("low_temp_threshold", DEFAULT_LOW_TEMP)
MATERIAL_MAPPING = _rules.get("materials", {})
CATEGORY_MAPPING = _rules.get("categories", {})
INSTITUTION_MAPPING = _rules.get("institutions", {})


def reload_rules():
    """룰 다시 로드 (런타임 중 JSON 수정 시)"""
    global _rules, VALID_WAFER_SIZES, MM_TO_INCH, TEMP_CONFIG
    global HIGH_TEMP_THRESHOLD, LOW_TEMP_THRESHOLD
    global MATERIAL_MAPPING, CATEGORY_MAPPING, INSTITUTION_MAPPING

    _rules = load_filter_rules()
    VALID_WAFER_SIZES = _rules.get("wafer_sizes", {}).get("valid_sizes", DEFAULT_VALID_WAFER_SIZES)
    MM_TO_INCH = _rules.get("wafer_sizes", {}).get("mm_to_inch", DEFAULT_MM_TO_INCH)
    TEMP_CONFIG = _rules.get("temperature", {})
    HIGH_TEMP_THRESHOLD = TEMP_CONFIG.get("high_temp_threshold", DEFAULT_HIGH_TEMP)
    LOW_TEMP_THRESHOLD = TEMP_CONFIG.get("low_temp_threshold", DEFAULT_LOW_TEMP)
    MATERIAL_MAPPING = _rules.get("materials", {})
    CATEGORY_MAPPING = _rules.get("categories", {})
    INSTITUTION_MAPPING = _rules.get("institutions", {})
    print("[QueryParser] Rules reloaded from JSON")


# === 웨이퍼 사이즈 추출 ===
def extract_wafer_sizes(text: str) -> List[str]:
    """웨이퍼 사이즈 추출 및 정규화"""
    sizes = set()
    text_lower = text.lower()

    # inch 표기 추출
    inch_matches = re.findall(r'(\d+)\s*(?:인치|inch|")', text_lower)
    for match in inch_matches:
        size = f"{match} inch"
        if size in VALID_WAFER_SIZES:
            sizes.add(size)

    # mm 표기 -> inch 변환
    for mm_pattern, inch_size in MM_TO_INCH.items():
        mm_value = mm_pattern.replace("mm", "")
        if re.search(rf'{mm_value}\s*mm', text_lower):
            sizes.add(inch_size)

    return list(sizes)


# === 온도 추출 ===
def extract_temperature(text: str) -> tuple:
    """온도 범위 추출"""
    temp_min = None
    temp_max = None

    # 범위 패턴 먼저 체크
    range_match = re.search(r'(\d+)\s*[~～-]\s*(\d+)\s*(?:도|℃|°C|°)', text)
    if range_match:
        temp_min = float(range_match.group(1))
        temp_max = float(range_match.group(2))
        return temp_min, temp_max

    # 이상/초과
    min_match = re.search(r'(\d+)\s*(?:도|℃|°C|°)\s*(?:이상|초과)', text)
    if min_match:
        temp_min = float(min_match.group(1))

    # 이하/미만/까지
    max_match = re.search(r'(\d+)\s*(?:도|℃|°C|°)\s*(?:이하|미만|까지)', text)
    if not max_match:
        max_match = re.search(r'[~～](\d+)\s*(?:도|℃|°C|°)', text)
    if max_match:
        temp_max = float(max_match.group(1))

    # 고온/저온 키워드
    if '고온' in text and temp_min is None:
        temp_min = float(HIGH_TEMP_THRESHOLD)
    if '저온' in text and temp_max is None:
        temp_max = float(LOW_TEMP_THRESHOLD)

    return temp_min, temp_max


# === 재료/기판 추출 ===
def extract_materials(text: str) -> List[str]:
    """재료/기판 추출"""
    materials = set()
    text_lower = text.lower()

    for key, normalized in MATERIAL_MAPPING.items():
        # 단어 경계 체크 (영문)
        if re.search(rf'\b{re.escape(key)}\b', text_lower):
            materials.add(normalized)
        # 한글은 단어 경계 없이
        elif key in text_lower and not key.isascii():
            materials.add(normalized)

    return list(materials)


# === 장비 카테고리/공정 추출 ===
def extract_categories(text: str) -> List[str]:
    """장비 카테고리 추출"""
    categories = set()
    text_lower = text.lower()

    for key, category in CATEGORY_MAPPING.items():
        if key in text_lower:
            categories.add(category)

    return list(categories)


# === 기관 추출 ===
def extract_institutions(text: str) -> List[str]:
    """기관 추출"""
    institutions = set()

    for key, institution in INSTITUTION_MAPPING.items():
        if key in text:
            institutions.add(institution)

    return list(institutions)


# === 메인 파서 ===
def parse_query(query: str) -> ParsedQuery:
    """
    사용자 질의를 파싱하여 구조화된 정보 추출

    Args:
        query: 원본 사용자 질의

    Returns:
        ParsedQuery: 파싱된 결과
    """
    # 정규화된 쿼리 (소문자, 공백 정리)
    normalized = ' '.join(query.lower().split())

    # 각 파라미터 추출
    wafer_sizes = extract_wafer_sizes(query)
    temp_min, temp_max = extract_temperature(query)
    materials = extract_materials(query)
    categories = extract_categories(query)
    institutions = extract_institutions(query)

    # 주요 키워드 추출 (간단한 토큰화)
    keywords = [w for w in query.split() if len(w) >= 2]

    return ParsedQuery(
        original=query,
        normalized=normalized,
        wafer_sizes=wafer_sizes,
        temp_min=temp_min,
        temp_max=temp_max,
        materials=materials,
        categories=categories,
        institutions=institutions,
        keywords=keywords
    )


def parsed_to_filters(parsed: ParsedQuery) -> Dict[str, Any]:
    """ParsedQuery를 ChromaDB 필터 조건으로 변환"""
    filters = {}

    if parsed.wafer_sizes:
        filters["wafer_sizes"] = parsed.wafer_sizes

    if parsed.categories:
        filters["category"] = parsed.categories[0]  # 첫 번째 카테고리 사용

    if parsed.institutions:
        filters["institution"] = parsed.institutions[0]

    return filters


def get_hard_constraints(parsed: ParsedQuery) -> Dict[str, Any]:
    """하드 제약조건 추출 (반드시 만족해야 하는 조건)"""
    constraints = {}

    if parsed.wafer_sizes:
        constraints["wafer_sizes"] = parsed.wafer_sizes

    if parsed.temp_min is not None:
        constraints["temp_min"] = parsed.temp_min

    if parsed.temp_max is not None:
        constraints["temp_max"] = parsed.temp_max

    if parsed.materials:
        constraints["materials"] = parsed.materials

    return constraints


# === 테스트 ===
if __name__ == "__main__":
    print(f"Filter rules loaded from: {FILTER_RULES_PATH}")
    print(f"  Materials: {len(MATERIAL_MAPPING)} entries")
    print(f"  Categories: {len(CATEGORY_MAPPING)} entries")
    print(f"  Institutions: {len(INSTITUTION_MAPPING)} entries")
    print()

    test_queries = [
        "6인치 Si 웨이퍼용 RTA 장비",
        "GaN MOCVD 장비 추천해줘",
        "400도 이상 열처리 가능한 장비",
        "나노종합기술원 SEM 장비",
        "8인치 알루미늄 스퍼터 장비",
        "200mm 웨이퍼 PECVD",
        "고온 산화 공정용 확산로",
        "사파이어 기판 에피 성장 장비",
    ]

    for q in test_queries:
        parsed = parse_query(q)
        print(f"\n질의: {q}")
        print(f"  웨이퍼: {parsed.wafer_sizes}")
        print(f"  온도: {parsed.temp_min}~{parsed.temp_max}")
        print(f"  재료: {parsed.materials}")
        print(f"  카테고리: {parsed.categories}")
        print(f"  기관: {parsed.institutions}")
