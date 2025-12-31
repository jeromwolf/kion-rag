"""
Policy DB 관리 모듈

기관 우선순위, 정책 설정, 공정-장비 매핑을 관리합니다.
"""

import json
import os
import time
from typing import Dict, List, Optional, Any
from pathlib import Path

# 데이터 파일 경로
POLICY_DATA_DIR = Path(__file__).parent.parent / "data" / "policy"


class InstitutionPriority:
    """기관 우선순위 관리"""

    def __init__(self):
        self._data: Dict[str, dict] = {}
        self._load()

    def _load(self):
        """JSON 파일에서 데이터 로드"""
        file_path = POLICY_DATA_DIR / "institution_priority.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for inst in data.get("institutions", []):
                    if inst.get("is_active", True):
                        self._data[inst["id"]] = inst

    def reload(self):
        """데이터 리로드"""
        self._data = {}
        self._load()

    def get_priority(self, institution_id: str) -> int:
        """기관 우선순위 조회 (없으면 999 반환)"""
        inst = self._data.get(institution_id)
        return inst["priority"] if inst else 999

    def get_all(self) -> List[dict]:
        """모든 기관 목록 반환"""
        return list(self._data.values())

    def apply_priority(self, equipment_list: List[dict],
                       user_institution: Optional[str] = None) -> List[dict]:
        """
        검색 결과에 기관 우선순위 적용

        Args:
            equipment_list: 장비 리스트
            user_institution: 사용자 소속 기관 (최우선 처리)

        Returns:
            우선순위가 적용된 장비 리스트
        """
        if not equipment_list:
            return equipment_list

        # 우선순위 점수 계산
        for equip in equipment_list:
            inst_id = equip.get("institution", equip.get("institution_id", ""))

            # 사용자 소속 기관이면 최우선 (0)
            if user_institution and inst_id == user_institution:
                priority_score = 0
            else:
                priority_score = self.get_priority(inst_id)

            equip["_priority_score"] = priority_score

        # 우선순위 점수로 정렬 (낮을수록 먼저)
        # 동일 우선순위면 RAG 점수로 정렬
        sorted_list = sorted(
            equipment_list,
            key=lambda x: (x.get("_priority_score", 999), -x.get("rag_score", 0))
        )

        return sorted_list


class PolicySettings:
    """정책 설정 관리"""

    def __init__(self):
        self._data: Dict[str, dict] = {}
        self._cache_ttl = 300  # 5분 캐시
        self._last_load = 0
        self._load()

    def _load(self):
        """JSON 파일에서 데이터 로드"""
        file_path = POLICY_DATA_DIR / "policy_settings.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for policy in data.get("policies", []):
                    self._data[policy["key"]] = policy
        self._last_load = time.time()

    def _refresh_if_needed(self):
        """캐시 만료 시 리로드"""
        if time.time() - self._last_load > self._cache_ttl:
            self._load()

    def reload(self):
        """데이터 리로드"""
        self._data = {}
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """정책 값 조회"""
        self._refresh_if_needed()
        policy = self._data.get(key)
        if policy is None:
            return default
        return self._parse_value(policy["value"], policy.get("type", "string"))

    def _parse_value(self, value: Any, value_type: str) -> Any:
        """값 타입에 따라 파싱"""
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() == "true"
        elif value_type == "integer":
            return int(value)
        elif value_type == "float":
            return float(value)
        return value

    def is_enabled(self, key: str) -> bool:
        """불리언 정책 확인"""
        return self.get(key, False) == True

    def get_all(self) -> List[dict]:
        """모든 정책 목록 반환"""
        self._refresh_if_needed()
        return list(self._data.values())

    def apply_filters(self, equipment_list: List[dict]) -> List[dict]:
        """
        정책에 따라 장비 필터링

        Args:
            equipment_list: 장비 리스트

        Returns:
            필터링된 장비 리스트
        """
        if not equipment_list:
            return equipment_list

        result = equipment_list.copy()

        # 점검 중 장비 제외
        if self.is_enabled("maintenance_exclude"):
            result = [e for e in result if not e.get("is_maintenance", False)]

        # 외부 기관 장비 필터
        if not self.is_enabled("external_visible"):
            result = [e for e in result if e.get("is_internal", True)]

        # 최소 RAG 점수 필터
        min_score = self.get("min_rag_score", 0.0)
        result = [e for e in result if e.get("rag_score", 1.0) >= min_score]

        # 최대 추천 수 제한
        max_rec = self.get("max_recommendations", 5)
        result = result[:max_rec]

        return result


class ProcessEquipmentMapper:
    """공정-장비 매핑 관리"""

    def __init__(self):
        self._mappings: Dict[str, List[str]] = {}
        self._exact_matches: set = set()
        self._load()

    def _load(self):
        """JSON 파일에서 데이터 로드"""
        file_path = POLICY_DATA_DIR / "process_equipment_mapping.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

                # 매핑 로드
                for mapping in data.get("mappings", []):
                    keyword = mapping["keyword"].lower()
                    categories = mapping.get("categories", [])
                    self._mappings[keyword] = categories

                    # 영문 키워드도 추가
                    if "keyword_en" in mapping:
                        self._mappings[mapping["keyword_en"].lower()] = categories

                # 정확 매칭 키워드 로드
                self._exact_matches = set(
                    k.lower() for k in data.get("exact_matches", [])
                )

    def reload(self):
        """데이터 리로드"""
        self._mappings = {}
        self._exact_matches = set()
        self._load()

    def get_categories(self, query: str) -> List[dict]:
        """
        쿼리에서 공정 키워드를 찾아 장비 카테고리 반환

        Args:
            query: 사용자 입력 쿼리

        Returns:
            매칭된 카테고리 정보 리스트
        """
        query_lower = query.lower()
        matched = []

        # 정확 매칭 먼저 확인
        for exact in self._exact_matches:
            if exact in query_lower:
                matched.append({
                    "keyword": exact,
                    "category": exact.upper(),
                    "is_exact": True,
                    "priority": 1
                })

        # 키워드 매핑 확인
        for keyword, categories in self._mappings.items():
            if keyword in query_lower:
                for idx, cat in enumerate(categories):
                    # 이미 정확 매칭된 카테고리는 제외
                    if not any(m["category"] == cat and m["is_exact"] for m in matched):
                        matched.append({
                            "keyword": keyword,
                            "category": cat,
                            "is_exact": False,
                            "priority": 10 + idx
                        })

        # 우선순위로 정렬
        matched.sort(key=lambda x: x["priority"])

        return matched

    def enhance_query(self, parsed_query: dict) -> dict:
        """
        파싱된 쿼리에 매핑된 카테고리 추가

        Args:
            parsed_query: 쿼리 파서 출력

        Returns:
            카테고리가 추가된 쿼리
        """
        original_query = parsed_query.get("original_query", "")
        if not original_query:
            original_query = parsed_query.get("query", "")

        categories = self.get_categories(original_query)

        if categories:
            # 중복 제거하여 상위 카테고리만 추출
            unique_categories = []
            seen = set()
            for c in categories:
                if c["category"] not in seen:
                    unique_categories.append(c["category"])
                    seen.add(c["category"])

            parsed_query["mapped_categories"] = unique_categories[:5]  # 최대 5개
            parsed_query["category_details"] = categories[:10]

        return parsed_query

    def get_all_mappings(self) -> Dict[str, List[str]]:
        """모든 매핑 반환"""
        return self._mappings.copy()


class PolicyManager:
    """Policy DB 통합 관리자"""

    def __init__(self):
        self.institution = InstitutionPriority()
        self.settings = PolicySettings()
        self.mapper = ProcessEquipmentMapper()

    def reload_all(self):
        """모든 정책 데이터 리로드"""
        self.institution.reload()
        self.settings.reload()
        self.mapper.reload()

    def apply_policies(self, equipment_list: List[dict],
                       user_institution: Optional[str] = None) -> List[dict]:
        """
        모든 정책을 순차적으로 적용

        Args:
            equipment_list: 장비 리스트
            user_institution: 사용자 소속 기관

        Returns:
            정책이 적용된 장비 리스트
        """
        if not equipment_list:
            return equipment_list

        # 1. 정책 설정 필터 적용
        result = self.settings.apply_filters(equipment_list)

        # 2. 기관 우선순위 적용
        result = self.institution.apply_priority(result, user_institution)

        return result

    def enhance_query(self, parsed_query: dict) -> dict:
        """쿼리에 공정-장비 매핑 적용"""
        return self.mapper.enhance_query(parsed_query)


# 싱글톤 인스턴스
_policy_manager: Optional[PolicyManager] = None


def get_policy_manager() -> PolicyManager:
    """PolicyManager 싱글톤 반환"""
    global _policy_manager
    if _policy_manager is None:
        _policy_manager = PolicyManager()
    return _policy_manager


# 편의 함수들
def apply_institution_priority(equipment_list: List[dict],
                                user_institution: Optional[str] = None) -> List[dict]:
    """기관 우선순위 적용"""
    return get_policy_manager().institution.apply_priority(equipment_list, user_institution)


def apply_policy_filters(equipment_list: List[dict]) -> List[dict]:
    """정책 필터 적용"""
    return get_policy_manager().settings.apply_filters(equipment_list)


def get_mapped_categories(query: str) -> List[str]:
    """쿼리에서 매핑된 카테고리 추출"""
    categories = get_policy_manager().mapper.get_categories(query)
    return [c["category"] for c in categories]


def enhance_query_with_mapping(parsed_query: dict) -> dict:
    """쿼리에 공정-장비 매핑 적용"""
    return get_policy_manager().enhance_query(parsed_query)


if __name__ == "__main__":
    # 테스트
    pm = PolicyManager()

    print("=== 기관 우선순위 ===")
    for inst in pm.institution.get_all():
        print(f"  {inst['name']}: {inst['priority']}")

    print("\n=== 정책 설정 ===")
    for policy in pm.settings.get_all():
        print(f"  {policy['key']}: {policy['value']}")

    print("\n=== 공정-장비 매핑 테스트 ===")
    test_queries = [
        "6인치 GaN 에피 성장 장비",
        "MOCVD 장비 추천",
        "박막 증착 PECVD",
        "열처리 RTA 장비",
        "표면 분석 SEM"
    ]

    for query in test_queries:
        categories = pm.mapper.get_categories(query)
        cats = [c["category"] for c in categories[:3]]
        print(f"  '{query}' → {cats}")
