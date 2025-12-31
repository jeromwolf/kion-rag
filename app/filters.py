"""
KION RAG PoC - 하드 필터 및 규칙 기반 필터링
Policy DB 통합: 정책 설정, 기관 우선순위 적용
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .query_parser import ParsedQuery


@dataclass
class FilterResult:
    """필터링 결과"""
    passed: bool
    reason: str = ""


# === Policy DB 통합 함수들 ===
def get_policy_settings():
    """PolicySettings 싱글톤 반환"""
    try:
        from .policy import get_policy_manager
        return get_policy_manager().settings
    except Exception as e:
        print(f"[Filters] Policy settings load error: {e}")
        return None


def get_institution_priority():
    """InstitutionPriority 싱글톤 반환"""
    try:
        from .policy import get_policy_manager
        return get_policy_manager().institution
    except Exception as e:
        print(f"[Filters] Institution priority load error: {e}")
        return None


def check_wafer_size(equipment: Dict[str, Any], required_sizes: List[str]) -> FilterResult:
    """
    웨이퍼 사이즈 필터
    장비가 요청된 사이즈를 지원하는지 확인
    """
    if not required_sizes:
        return FilterResult(passed=True)

    eq_sizes = equipment.get("wafer_sizes", [])
    if not eq_sizes:
        return FilterResult(passed=False, reason="웨이퍼 사이즈 정보 없음")

    # 하나라도 매칭되면 통과
    for size in required_sizes:
        if size in eq_sizes:
            return FilterResult(passed=True)

    return FilterResult(
        passed=False,
        reason=f"요청 사이즈 {required_sizes} 미지원 (지원: {eq_sizes})"
    )


def check_temperature(
    equipment: Dict[str, Any],
    temp_min: Optional[float],
    temp_max: Optional[float]
) -> FilterResult:
    """
    온도 범위 필터
    장비가 요청된 온도 범위를 지원하는지 확인
    """
    if temp_min is None and temp_max is None:
        return FilterResult(passed=True)

    eq_temp_min = equipment.get("temp_min")
    eq_temp_max = equipment.get("temp_max")

    if eq_temp_min is None or eq_temp_max is None:
        return FilterResult(passed=False, reason="온도 정보 없음")

    # 요청 최소 온도 체크: 장비가 해당 온도 이상 지원해야 함
    if temp_min is not None:
        if eq_temp_max < temp_min:
            return FilterResult(
                passed=False,
                reason=f"최대 {eq_temp_max}℃까지만 지원 (요청: {temp_min}℃ 이상)"
            )

    # 요청 최대 온도 체크: 장비가 해당 온도 이하도 지원해야 함
    if temp_max is not None:
        if eq_temp_min > temp_max:
            return FilterResult(
                passed=False,
                reason=f"최소 {eq_temp_min}℃부터 지원 (요청: {temp_max}℃ 이하)"
            )

    return FilterResult(passed=True)


def check_materials(equipment: Dict[str, Any], required_materials: List[str]) -> FilterResult:
    """
    재료/기판 필터
    장비가 요청된 재료를 처리할 수 있는지 확인
    """
    if not required_materials:
        return FilterResult(passed=True)

    eq_materials = equipment.get("materials", [])
    if not eq_materials:
        # 재료 정보가 없으면 일단 통과 (soft fail)
        return FilterResult(passed=True)

    # 대소문자 무시 비교
    eq_materials_lower = [m.lower() for m in eq_materials]

    for material in required_materials:
        if material.lower() in eq_materials_lower:
            return FilterResult(passed=True)

    return FilterResult(
        passed=False,
        reason=f"요청 재료 {required_materials} 미지원"
    )


def check_category(
    equipment: Dict[str, Any],
    required_categories: List[str],
    mapped_categories: Optional[List[str]] = None
) -> FilterResult:
    """
    카테고리 필터 (Policy DB 매핑 포함)

    Args:
        equipment: 장비 정보
        required_categories: 명시적 요청 카테고리
        mapped_categories: Policy DB에서 매핑된 카테고리 (STEP 4)
    """
    eq_category = equipment.get("category", "")
    eq_name = equipment.get("name", "").upper()

    # 명시적 카테고리 먼저 체크
    if required_categories:
        for cat in required_categories:
            if cat == eq_category:
                return FilterResult(passed=True)

    # Policy DB 매핑 카테고리 체크
    if mapped_categories:
        for cat in mapped_categories:
            # 장비 카테고리 또는 이름에 매칭
            if cat.upper() == eq_category.upper():
                return FilterResult(passed=True)
            if cat.upper() in eq_name:
                return FilterResult(passed=True)

    # 카테고리 불일치는 soft fail (점수만 낮춤)
    return FilterResult(passed=True)


def check_institution(equipment: Dict[str, Any], required_institutions: List[str]) -> FilterResult:
    """
    기관 필터
    """
    if not required_institutions:
        return FilterResult(passed=True)

    eq_institution = equipment.get("institution", "")

    for inst in required_institutions:
        if inst in eq_institution:
            return FilterResult(passed=True)

    return FilterResult(
        passed=False,
        reason=f"요청 기관 아님 (현재: {eq_institution})"
    )


def apply_hard_filters(
    equipments: List[Dict[str, Any]],
    parsed_query: ParsedQuery,
    strict_mode: bool = False
) -> List[Dict[str, Any]]:
    """
    하드 필터 적용

    Args:
        equipments: 검색된 장비 리스트
        parsed_query: 파싱된 쿼리
        strict_mode: True면 하나라도 실패시 제외

    Returns:
        필터링된 장비 리스트 (filter_passed, filter_reasons 필드 추가)
    """
    results = []

    for eq in equipments:
        filter_results = []

        # 1. 웨이퍼 사이즈 체크 (하드)
        size_check = check_wafer_size(eq, parsed_query.wafer_sizes)
        filter_results.append(("wafer_size", size_check))

        # 2. 온도 범위 체크 (하드)
        temp_check = check_temperature(eq, parsed_query.temp_min, parsed_query.temp_max)
        filter_results.append(("temperature", temp_check))

        # 3. 재료 체크 (소프트)
        material_check = check_materials(eq, parsed_query.materials)
        filter_results.append(("materials", material_check))

        # 4. 기관 체크 (하드)
        institution_check = check_institution(eq, parsed_query.institutions)
        filter_results.append(("institution", institution_check))

        # 5. 카테고리 체크 (Policy DB 매핑 포함 - STEP 4)
        mapped_cats = getattr(parsed_query, 'mapped_categories', [])
        category_check = check_category(eq, parsed_query.categories, mapped_cats)
        filter_results.append(("category", category_check))

        # 결과 집계
        all_passed = all(r.passed for _, r in filter_results)
        failed_reasons = [f"{name}: {r.reason}" for name, r in filter_results if not r.passed]

        # 장비에 필터 결과 추가
        eq_copy = eq.copy()
        eq_copy["filter_passed"] = all_passed
        eq_copy["filter_reasons"] = failed_reasons

        # strict 모드: 하나라도 실패하면 제외
        if strict_mode and not all_passed:
            continue

        results.append(eq_copy)

    # 필터 통과한 장비를 앞으로
    results.sort(key=lambda x: (not x["filter_passed"], -x.get("score", 0)))

    return results


def calculate_match_score(equipment: Dict[str, Any], parsed_query: ParsedQuery) -> float:
    """
    쿼리와의 매칭 점수 계산 (0~1)
    """
    score = 0.0
    max_score = 0.0

    # 웨이퍼 사이즈 매칭 (가중치: 0.25)
    if parsed_query.wafer_sizes:
        max_score += 0.25
        eq_sizes = equipment.get("wafer_sizes", [])
        if any(s in eq_sizes for s in parsed_query.wafer_sizes):
            score += 0.25

    # 온도 범위 매칭 (가중치: 0.25)
    if parsed_query.temp_min is not None or parsed_query.temp_max is not None:
        max_score += 0.25
        temp_check = check_temperature(equipment, parsed_query.temp_min, parsed_query.temp_max)
        if temp_check.passed:
            score += 0.25

    # 재료 매칭 (가중치: 0.25)
    if parsed_query.materials:
        max_score += 0.25
        eq_materials = [m.lower() for m in equipment.get("materials", [])]
        if any(m.lower() in eq_materials for m in parsed_query.materials):
            score += 0.25

    # 카테고리 매칭 (가중치: 0.15)
    if parsed_query.categories:
        max_score += 0.15
        if equipment.get("category") in parsed_query.categories:
            score += 0.15

    # 기관 매칭 (가중치: 0.1)
    if parsed_query.institutions:
        max_score += 0.1
        if any(inst in equipment.get("institution", "") for inst in parsed_query.institutions):
            score += 0.1

    if max_score == 0:
        return 1.0  # 조건이 없으면 만점

    return score / max_score


def rerank_with_filters(
    equipments: List[Dict[str, Any]],
    parsed_query: ParsedQuery,
    user_institution: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    필터 기반 리랭킹 (Policy DB 통합)

    Args:
        equipments: 검색된 장비 리스트 (score 필드 포함)
        parsed_query: 파싱된 쿼리
        user_institution: 사용자 소속 기관 (최우선 처리)

    Returns:
        리랭킹된 장비 리스트
    """
    # Policy DB 설정 로드
    policy_settings = get_policy_settings()
    institution_priority = get_institution_priority()

    # 하드 필터 적용
    filtered = apply_hard_filters(equipments, parsed_query, strict_mode=False)

    # STEP 5: Policy DB 하드 규칙 적용
    if policy_settings:
        # 점검 중 장비 제외
        if policy_settings.is_enabled("maintenance_exclude"):
            filtered = [e for e in filtered if not e.get("is_maintenance", False)]

        # 최소 RAG 점수 필터
        min_score = policy_settings.get("min_rag_score", 0.0)
        filtered = [e for e in filtered if e.get("score", 1.0) >= min_score]

    # 매칭 점수 계산 및 결합
    for eq in filtered:
        rag_score = eq.get("score", 0.5)
        match_score = calculate_match_score(eq, parsed_query)

        # 필터 통과 여부에 따른 가중치
        filter_weight = 1.0 if eq.get("filter_passed", True) else 0.3

        # 최종 점수: RAG 점수 + 매칭 점수 + 필터 가중치
        eq["combined_score"] = (rag_score * 0.4 + match_score * 0.6) * filter_weight
        eq["match_score"] = match_score
        eq["rag_score"] = rag_score  # Policy DB용

    # combined_score로 정렬
    filtered.sort(key=lambda x: -x.get("combined_score", 0))

    # STEP 7: 기관 우선순위 적용
    if institution_priority:
        filtered = institution_priority.apply_priority(filtered, user_institution)

    # Policy DB: 최대 추천 수 제한
    if policy_settings:
        max_rec = policy_settings.get("max_recommendations", 10)
        filtered = filtered[:max_rec]

    return filtered


# === 테스트 ===
if __name__ == "__main__":
    from .query_parser import parse_query

    # 테스트 장비 데이터
    test_equipments = [
        {
            "equipment_id": "KION-001",
            "name": "ICP-CVD",
            "category": "증착",
            "wafer_sizes": ["6 inch", "8 inch"],
            "materials": ["SiO2", "SiNx"],
            "temp_min": 100,
            "temp_max": 400,
            "institution": "광주나노기술집적센터",
            "score": 0.85
        },
        {
            "equipment_id": "KION-009",
            "name": "MOCVD",
            "category": "증착",
            "wafer_sizes": ["2 inch", "4 inch"],
            "materials": ["GaN", "AlGaN", "InGaN"],
            "temp_min": 400,
            "temp_max": 1200,
            "institution": "나노종합기술원",
            "score": 0.90
        },
        {
            "equipment_id": "KION-021",
            "name": "RTP",
            "category": "열처리",
            "wafer_sizes": ["4 inch", "6 inch", "8 inch"],
            "materials": ["Si"],
            "temp_min": 200,
            "temp_max": 1300,
            "institution": "한국나노기술원",
            "score": 0.75
        }
    ]

    # 테스트 쿼리
    test_queries = [
        "6인치 Si 웨이퍼 400도 이상 열처리",
        "GaN MOCVD 장비",
        "8인치 CVD 증착 장비",
    ]

    for q in test_queries:
        print(f"\n{'='*50}")
        print(f"질의: {q}")
        parsed = parse_query(q)
        print(f"파싱: 웨이퍼={parsed.wafer_sizes}, 온도={parsed.temp_min}~{parsed.temp_max}, 재료={parsed.materials}")

        results = rerank_with_filters(test_equipments.copy(), parsed)

        print("\n결과:")
        for eq in results:
            status = "PASS" if eq.get("filter_passed") else "FAIL"
            print(f"  [{status}] {eq['name']} - score: {eq.get('combined_score', 0):.2f}")
            if not eq.get("filter_passed"):
                print(f"       이유: {eq.get('filter_reasons')}")
