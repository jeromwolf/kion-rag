# Policy DB 상세 설계

## 개요

Policy DB는 RAG 시스템의 비즈니스 룰과 정책을 관리하는 데이터베이스입니다.

---

## 처리 순서도 (Flow Chart)

### 전체 파이프라인에서 Policy DB 적용 시점

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        사용자 쿼리 처리 파이프라인                            │
└─────────────────────────────────────────────────────────────────────────────┘

사용자 입력: "6인치 GaN 에피 성장 장비 추천해줘"
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: 쿼리 파싱 (query_parser.py)                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  입력: "6인치 GaN 에피 성장 장비 추천해줘"                                     │
│  출력: {                                                                     │
│          wafer_size: "6 inch",                                              │
│          material: "GaN",                                                   │
│          original_query: "6인치 GaN 에피 성장 장비 추천해줘"                   │
│        }                                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: 공정↔장비 매핑 적용 ★ Policy DB #1                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  "에피 성장" 키워드 감지                                                      │
│  ↓                                                                          │
│  process_equipment_mapping.json 조회                                        │
│  ↓                                                                          │
│  mapped_categories: ["MOCVD", "MBE"] 추가                                   │
│                                                                             │
│  출력: {                                                                     │
│          wafer_size: "6 inch",                                              │
│          material: "GaN",                                                   │
│          mapped_categories: ["MOCVD", "MBE"],  ← 추가됨                      │
│          original_query: "..."                                              │
│        }                                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: RAG 벡터 검색 (rag.py)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  3-1. 쿼리 임베딩 생성                                                       │
│  3-2. ChromaDB 벡터 검색 (Top 20)                                           │
│  3-3. 메타데이터 필터 적용                                                    │
│       - wafer_size == "6 inch"                                              │
│       - material contains "GaN"                                             │
│  3-4. 카테고리 부스팅 (mapped_categories 우선)                                │
│       - MOCVD, MBE 장비 점수 +0.2                                           │
│                                                                             │
│  출력: [장비1, 장비2, 장비3, ...] (rag_score 포함)                            │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: 정책 필터 적용 ★ Policy DB #2                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  policy_settings.json 조회                                                  │
│                                                                             │
│  4-1. maintenance_exclude = true                                            │
│       → is_maintenance=true 장비 제거                                        │
│                                                                             │
│  4-2. external_visible = true                                               │
│       → 외부 기관 장비 포함 (false면 제거)                                    │
│                                                                             │
│  4-3. min_rag_score = 0.3                                                   │
│       → rag_score < 0.3 장비 제거                                           │
│                                                                             │
│  출력: [필터링된 장비 리스트]                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: 기관 우선순위 적용 ★ Policy DB #3                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  institution_priority.json 조회                                             │
│                                                                             │
│  5-1. 사용자 소속 기관 확인 (user_context)                                    │
│       → 소속 기관 장비 priority = 0 (최우선)                                  │
│                                                                             │
│  5-2. 기관별 priority 점수 부여                                              │
│       나노종합기술원: 10                                                     │
│       한국나노기술원: 20                                                     │
│       KIST: 30                                                              │
│       ...                                                                   │
│                                                                             │
│  5-3. 정렬: priority ASC, rag_score DESC                                    │
│                                                                             │
│  출력: [우선순위 정렬된 장비 리스트]                                          │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: 리랭킹 (filters.py)                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  최종 점수 계산:                                                             │
│  final_score = rag_score × 0.7 + priority_score × 0.3                       │
│                                                                             │
│  출력: [최종 정렬된 장비 리스트]                                              │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: 결과 제한 ★ Policy DB #4                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  max_recommendations = 5                                                    │
│  → 상위 5개만 LLM에 전달                                                     │
│                                                                             │
│  출력: [Top 5 장비]                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 8: LLM 응답 생성 (llm.py)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  시스템 프롬프트 + 장비 리스트 → LLM                                          │
│  → 추천 이유 설명 생성                                                       │
│                                                                             │
│  출력: "GaN 에피 성장에는 MOCVD 장비를 추천드립니다..."                        │
└─────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
   응답 반환


┌─────────────────────────────────────────────────────────────────────────────┐
│                         Policy DB 적용 시점 요약                              │
├──────────┬──────────────────────────┬───────────────────────────────────────┤
│   시점    │       적용 내용           │              목적                     │
├──────────┼──────────────────────────┼───────────────────────────────────────┤
│ STEP 2   │ 공정↔장비 매핑            │ 검색 정확도 향상 (키워드→카테고리)      │
│ STEP 4   │ 정책 필터                 │ 비즈니스 룰 적용 (점검중 제외 등)       │
│ STEP 5   │ 기관 우선순위             │ 기관별 장비 우선 표시                  │
│ STEP 7   │ 결과 제한                 │ LLM 입력 최적화                       │
└──────────┴──────────────────────────┴───────────────────────────────────────┘
```

### 상세 시퀀스 다이어그램

```
User        API         QueryParser    PolicyDB      RAG         Reranker      LLM
 │           │              │             │           │             │           │
 │──쿼리────▶│              │             │           │             │           │
 │           │──파싱───────▶│             │           │             │           │
 │           │              │             │           │             │           │
 │           │◀─파싱결과────│             │           │             │           │
 │           │              │             │           │             │           │
 │           │──매핑조회────────────────▶│           │             │           │
 │           │              │             │           │             │           │
 │           │◀─카테고리────────────────│           │             │           │
 │           │              │             │           │             │           │
 │           │──벡터검색─────────────────────────▶│             │           │
 │           │              │             │           │             │           │
 │           │◀─검색결과────────────────────────│             │           │
 │           │              │             │           │             │           │
 │           │──정책필터────────────────▶│           │             │           │
 │           │              │             │           │             │           │
 │           │◀─필터결과────────────────│           │             │           │
 │           │              │             │           │             │           │
 │           │──우선순위────────────────▶│           │             │           │
 │           │              │             │           │             │           │
 │           │◀─정렬결과────────────────│           │             │           │
 │           │              │             │           │             │           │
 │           │──리랭킹──────────────────────────────────────▶│           │
 │           │              │             │           │             │           │
 │           │◀─최종순위───────────────────────────────────│           │
 │           │              │             │           │             │           │
 │           │──응답생성────────────────────────────────────────────▶│
 │           │              │             │           │             │           │
 │           │◀─추천응답───────────────────────────────────────────│
 │           │              │             │           │             │           │
 │◀──응답───│              │             │           │             │           │
```

```
┌─────────────────────────────────────────────────────────────┐
│                      POLICY DB                               │
├─────────────────┬─────────────────┬─────────────────────────┤
│  기관 우선순위   │   정책 설정      │   공정↔장비 매핑        │
│  (Priority)     │   (Settings)    │   (Mapping)             │
└─────────────────┴─────────────────┴─────────────────────────┘
```

---

## 1. 기관 우선순위 테이블

### 1.1 목적
- 검색 결과에서 특정 기관의 장비를 우선 표시
- 사용자 소속 기관 장비 우선 추천

### 1.2 테이블 스키마

```sql
CREATE TABLE institution_priority (
    id              INTEGER PRIMARY KEY,
    institution_id  VARCHAR(50) NOT NULL UNIQUE,  -- 기관 코드
    name            VARCHAR(100) NOT NULL,         -- 기관명
    name_short      VARCHAR(50),                   -- 약칭
    priority        INTEGER DEFAULT 100,           -- 우선순위 (낮을수록 높음)
    is_active       BOOLEAN DEFAULT TRUE,          -- 활성 여부
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

### 1.3 샘플 데이터

| id | institution_id | name | name_short | priority | is_active |
|----|----------------|------|------------|----------|-----------|
| 1 | NNFC | 나노종합기술원 | 나노종합 | 10 | TRUE |
| 2 | KANC | 한국나노기술원 | 한국나노 | 20 | TRUE |
| 3 | KIST | 한국과학기술연구원 | KIST | 30 | TRUE |
| 4 | ETRI | 한국전자통신연구원 | ETRI | 30 | TRUE |
| 5 | KAIST | 한국과학기술원 | KAIST | 40 | TRUE |

### 1.4 적용 로직

```python
def apply_institution_priority(equipment_list: list, user_institution: str = None) -> list:
    """
    검색 결과에 기관 우선순위 적용

    Args:
        equipment_list: RAG 검색 결과 장비 리스트
        user_institution: 사용자 소속 기관 (있으면 최우선)

    Returns:
        우선순위가 적용된 장비 리스트
    """
    # 1. 기관별 우선순위 로드
    priorities = load_institution_priorities()  # {institution_id: priority}

    # 2. 사용자 소속 기관이 있으면 최우선 (priority = 0)
    if user_institution:
        priorities[user_institution] = 0

    # 3. 장비별 우선순위 점수 계산
    for equip in equipment_list:
        inst_id = equip.get('institution_id', 'UNKNOWN')
        equip['_priority_score'] = priorities.get(inst_id, 999)

    # 4. 우선순위 + RAG 점수 조합하여 정렬
    # 공식: final_score = rag_score * 0.7 + (100 - priority_score) * 0.3
    sorted_list = sorted(equipment_list,
                         key=lambda x: (x['_priority_score'], -x.get('rag_score', 0)))

    return sorted_list
```

### 1.5 적용 시점

```
사용자 쿼리 → 쿼리 파싱 → RAG 검색 → [기관 우선순위 적용] → 리랭킹 → LLM → 응답
```

---

## 2. 정책 설정 테이블

### 2.1 목적
- 시스템 동작 정책을 ON/OFF로 관리
- 관리자가 실시간으로 정책 변경 가능

### 2.2 테이블 스키마

```sql
CREATE TABLE policy_settings (
    id              INTEGER PRIMARY KEY,
    policy_key      VARCHAR(50) NOT NULL UNIQUE,   -- 정책 키
    policy_name     VARCHAR(100) NOT NULL,          -- 정책명 (표시용)
    description     TEXT,                           -- 설명
    value           VARCHAR(200) NOT NULL,          -- 값 (true/false 또는 숫자/문자열)
    value_type      VARCHAR(20) DEFAULT 'boolean',  -- boolean, integer, string
    category        VARCHAR(50),                    -- 카테고리 (filter, display, etc.)
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

### 2.3 샘플 데이터

| policy_key | policy_name | value | value_type | category |
|------------|-------------|-------|------------|----------|
| maintenance_exclude | 점검 중 장비 제외 | true | boolean | filter |
| reservation_check | 예약 가능 여부 표시 | true | boolean | display |
| cost_display | 비용 정보 표시 | false | boolean | display |
| external_visible | 외부 기관 장비 표시 | true | boolean | filter |
| max_recommendations | 최대 추천 수 | 5 | integer | limit |
| min_rag_score | 최소 RAG 점수 | 0.3 | float | filter |
| priority_weight | 우선순위 가중치 | 0.3 | float | scoring |

### 2.4 적용 로직

```python
class PolicyManager:
    """정책 설정 관리자"""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5분 캐시
        self._last_load = 0

    def get(self, key: str, default=None):
        """정책 값 조회"""
        self._refresh_cache_if_needed()
        policy = self._cache.get(key)
        if policy is None:
            return default
        return self._parse_value(policy['value'], policy['value_type'])

    def _parse_value(self, value: str, value_type: str):
        """값 타입에 따라 파싱"""
        if value_type == 'boolean':
            return value.lower() == 'true'
        elif value_type == 'integer':
            return int(value)
        elif value_type == 'float':
            return float(value)
        return value

    def is_enabled(self, key: str) -> bool:
        """불리언 정책 확인"""
        return self.get(key, False) == True


# 사용 예시
policy = PolicyManager()

def filter_equipment(equipment_list: list) -> list:
    """정책에 따라 장비 필터링"""
    result = equipment_list.copy()

    # 점검 중 장비 제외
    if policy.is_enabled('maintenance_exclude'):
        result = [e for e in result if not e.get('is_maintenance', False)]

    # 외부 기관 장비 필터
    if not policy.is_enabled('external_visible'):
        result = [e for e in result if e.get('is_internal', True)]

    # 최소 RAG 점수 필터
    min_score = policy.get('min_rag_score', 0.0)
    result = [e for e in result if e.get('rag_score', 0) >= min_score]

    # 최대 추천 수 제한
    max_rec = policy.get('max_recommendations', 5)
    result = result[:max_rec]

    return result
```

### 2.5 적용 시점

```
                    ┌─────────────────┐
                    │  Policy Cache   │
                    └────────┬────────┘
                             │ 조회
                             ▼
사용자 쿼리 → 파싱 → RAG → [정책 필터링] → 우선순위 → 리랭킹 → LLM
                             │
                    ┌────────┴────────┐
                    │ maintenance_exclude
                    │ external_visible
                    │ min_rag_score
                    │ max_recommendations
                    └─────────────────┘
```

---

## 3. 공정↔장비 매핑 테이블

### 3.1 목적
- 사용자가 입력한 공정 키워드를 장비 카테고리로 매핑
- 검색 정확도 향상

### 3.2 테이블 스키마

```sql
CREATE TABLE process_equipment_mapping (
    id              INTEGER PRIMARY KEY,
    process_keyword VARCHAR(100) NOT NULL,         -- 공정 키워드
    equipment_category VARCHAR(100) NOT NULL,      -- 장비 카테고리
    priority        INTEGER DEFAULT 100,           -- 매핑 우선순위
    is_exact_match  BOOLEAN DEFAULT FALSE,         -- 정확 매칭 여부
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),

    UNIQUE(process_keyword, equipment_category)
);

-- 인덱스
CREATE INDEX idx_process_keyword ON process_equipment_mapping(process_keyword);
```

### 3.3 샘플 데이터

| process_keyword | equipment_category | priority | is_exact_match |
|-----------------|-------------------|----------|----------------|
| 에피 성장 | MOCVD | 10 | FALSE |
| 에피 성장 | MBE | 20 | FALSE |
| epitaxy | MOCVD | 10 | FALSE |
| 박막 증착 | Sputter | 10 | FALSE |
| 박막 증착 | PECVD | 20 | FALSE |
| 박막 증착 | ALD | 30 | FALSE |
| CVD | PECVD | 10 | FALSE |
| CVD | MOCVD | 20 | FALSE |
| CVD | LPCVD | 30 | FALSE |
| 열처리 | RTA | 10 | FALSE |
| 열처리 | Furnace | 20 | FALSE |
| annealing | RTA | 10 | FALSE |
| 식각 | ICP-RIE | 10 | FALSE |
| 식각 | RIE | 20 | FALSE |
| etching | ICP-RIE | 10 | FALSE |
| 표면 분석 | SEM | 10 | FALSE |
| 표면 분석 | AFM | 20 | FALSE |
| 표면 분석 | XPS | 30 | FALSE |
| SEM | SEM | 1 | TRUE |
| MOCVD | MOCVD | 1 | TRUE |
| RTA | RTA | 1 | TRUE |

### 3.4 적용 로직

```python
class ProcessEquipmentMapper:
    """공정-장비 매핑 관리자"""

    def __init__(self):
        self._mappings = {}  # {keyword: [(category, priority), ...]}
        self._load_mappings()

    def _load_mappings(self):
        """DB에서 매핑 로드"""
        # SELECT * FROM process_equipment_mapping WHERE is_active = TRUE
        rows = db.query(...)

        for row in rows:
            keyword = row['process_keyword'].lower()
            if keyword not in self._mappings:
                self._mappings[keyword] = []
            self._mappings[keyword].append({
                'category': row['equipment_category'],
                'priority': row['priority'],
                'is_exact': row['is_exact_match']
            })

        # 우선순위로 정렬
        for keyword in self._mappings:
            self._mappings[keyword].sort(key=lambda x: x['priority'])

    def get_categories(self, query: str) -> list:
        """
        쿼리에서 공정 키워드를 찾아 장비 카테고리 반환

        Args:
            query: 사용자 입력 쿼리

        Returns:
            [(category, priority, is_exact), ...]
        """
        query_lower = query.lower()
        matched_categories = []

        for keyword, mappings in self._mappings.items():
            if keyword in query_lower:
                for m in mappings:
                    matched_categories.append({
                        'keyword': keyword,
                        'category': m['category'],
                        'priority': m['priority'],
                        'is_exact': m['is_exact']
                    })

        # 정확 매칭 우선, 그 다음 priority 순
        matched_categories.sort(key=lambda x: (not x['is_exact'], x['priority']))

        return matched_categories

    def enhance_query(self, parsed_query: dict) -> dict:
        """
        파싱된 쿼리에 매핑된 카테고리 추가

        Args:
            parsed_query: 쿼리 파서 출력

        Returns:
            카테고리가 추가된 쿼리
        """
        original_query = parsed_query.get('original_query', '')
        categories = self.get_categories(original_query)

        if categories:
            # 상위 3개 카테고리만 사용
            top_categories = [c['category'] for c in categories[:3]]
            parsed_query['mapped_categories'] = top_categories

        return parsed_query


# 사용 예시
mapper = ProcessEquipmentMapper()

def process_query(user_query: str) -> dict:
    """쿼리 처리 파이프라인"""

    # 1. 기본 파싱
    parsed = query_parser.parse(user_query)
    # {'wafer_size': '6 inch', 'temperature': 400, 'original_query': '...'}

    # 2. 공정-장비 매핑 적용
    parsed = mapper.enhance_query(parsed)
    # {'wafer_size': '6 inch', 'temperature': 400, 'mapped_categories': ['MOCVD', 'MBE'], ...}

    # 3. RAG 검색 시 매핑된 카테고리로 필터링/부스팅
    results = rag_search(parsed)

    return results
```

### 3.5 적용 시점

```
사용자 쿼리 → [쿼리 파싱] → [매핑 적용] → RAG 검색
                  │              │
                  ▼              ▼
            웨이퍼, 온도 등    공정 키워드 →
            하드 조건 추출     장비 카테고리 변환
```

---

## 4. 통합 파이프라인

### 4.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Policy DB 적용 파이프라인                         │
└─────────────────────────────────────────────────────────────────────────┘

사용자 쿼리: "6인치 GaN 에피 성장 장비 추천해줘"
     │
     ▼
┌─────────────────┐
│  1. 쿼리 파싱    │  wafer_size: "6 inch", material: "GaN"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. 매핑 적용    │  mapped_categories: ["MOCVD", "MBE"]  ← 공정↔장비 매핑
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. RAG 검색    │  벡터 검색 + 메타 필터 (카테고리 부스팅)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. 정책 필터    │  maintenance_exclude, min_rag_score  ← 정책 설정
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. 우선순위     │  기관별 정렬, 사용자 소속 우선       ← 기관 우선순위
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. 리랭킹      │  최종 스코어 계산
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. LLM 생성    │  추천 + 설명 생성
└────────┬────────┘
         │
         ▼
      응답 반환
```

### 4.2 구현 예시

```python
class PolicyAwareRAG:
    """Policy DB가 적용된 RAG 파이프라인"""

    def __init__(self):
        self.query_parser = QueryParser()
        self.mapper = ProcessEquipmentMapper()
        self.policy = PolicyManager()
        self.rag = RAGEngine()
        self.reranker = Reranker()
        self.llm = LLMClient()

    def search(self, user_query: str, user_context: dict = None) -> dict:
        """
        Policy DB가 적용된 검색

        Args:
            user_query: 사용자 쿼리
            user_context: 사용자 컨텍스트 (소속 기관 등)
        """
        # 1. 쿼리 파싱
        parsed = self.query_parser.parse(user_query)

        # 2. 공정-장비 매핑 적용
        parsed = self.mapper.enhance_query(parsed)

        # 3. RAG 검색
        results = self.rag.search(
            query=user_query,
            filters=parsed,
            boost_categories=parsed.get('mapped_categories', [])
        )

        # 4. 정책 필터 적용
        results = self._apply_policy_filters(results)

        # 5. 기관 우선순위 적용
        user_institution = user_context.get('institution') if user_context else None
        results = apply_institution_priority(results, user_institution)

        # 6. 리랭킹
        results = self.reranker.rerank(results, parsed)

        # 7. LLM 응답 생성
        response = self.llm.generate_recommendation(
            query=user_query,
            equipment_list=results[:self.policy.get('max_recommendations', 5)]
        )

        return response

    def _apply_policy_filters(self, results: list) -> list:
        """정책 필터 적용"""
        filtered = results.copy()

        if self.policy.is_enabled('maintenance_exclude'):
            filtered = [e for e in filtered if not e.get('is_maintenance')]

        if not self.policy.is_enabled('external_visible'):
            filtered = [e for e in filtered if e.get('is_internal', True)]

        min_score = self.policy.get('min_rag_score', 0.0)
        filtered = [e for e in filtered if e.get('rag_score', 0) >= min_score]

        return filtered
```

---

## 5. 데이터 파일 구조 (JSON)

PoC에서는 SQLite 대신 JSON 파일로 관리:

```
data/
├── policy/
│   ├── institution_priority.json
│   ├── policy_settings.json
│   └── process_equipment_mapping.json
```

### 5.1 institution_priority.json

```json
{
  "institutions": [
    {"id": "NNFC", "name": "나노종합기술원", "priority": 10, "is_active": true},
    {"id": "KANC", "name": "한국나노기술원", "priority": 20, "is_active": true},
    {"id": "KIST", "name": "한국과학기술연구원", "priority": 30, "is_active": true}
  ],
  "updated_at": "2025-12-29T00:00:00Z"
}
```

### 5.2 policy_settings.json

```json
{
  "policies": [
    {"key": "maintenance_exclude", "value": true, "type": "boolean"},
    {"key": "reservation_check", "value": true, "type": "boolean"},
    {"key": "external_visible", "value": true, "type": "boolean"},
    {"key": "max_recommendations", "value": 5, "type": "integer"},
    {"key": "min_rag_score", "value": 0.3, "type": "float"}
  ],
  "updated_at": "2025-12-29T00:00:00Z"
}
```

### 5.3 process_equipment_mapping.json

```json
{
  "mappings": [
    {"keyword": "에피 성장", "categories": ["MOCVD", "MBE"]},
    {"keyword": "epitaxy", "categories": ["MOCVD", "MBE"]},
    {"keyword": "박막 증착", "categories": ["Sputter", "PECVD", "ALD"]},
    {"keyword": "CVD", "categories": ["PECVD", "MOCVD", "LPCVD"]},
    {"keyword": "열처리", "categories": ["RTA", "Furnace"]},
    {"keyword": "annealing", "categories": ["RTA", "Furnace"]},
    {"keyword": "식각", "categories": ["ICP-RIE", "RIE"]},
    {"keyword": "etching", "categories": ["ICP-RIE", "RIE"]},
    {"keyword": "표면 분석", "categories": ["SEM", "AFM", "XPS"]}
  ],
  "exact_matches": ["SEM", "MOCVD", "RTA", "PECVD", "MBE", "ALD"],
  "updated_at": "2025-12-29T00:00:00Z"
}
```

---

## 6. 관리자 API

### 6.1 엔드포인트

```
# 기관 우선순위
GET    /admin/policy/institutions          # 목록 조회
PUT    /admin/policy/institutions/{id}     # 수정
POST   /admin/policy/institutions          # 추가

# 정책 설정
GET    /admin/policy/settings              # 목록 조회
PUT    /admin/policy/settings/{key}        # 수정

# 공정-장비 매핑
GET    /admin/policy/mappings              # 목록 조회
PUT    /admin/policy/mappings/{id}         # 수정
POST   /admin/policy/mappings              # 추가
DELETE /admin/policy/mappings/{id}         # 삭제
```

---

*작성일: 2025-12-29*
