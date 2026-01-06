"""
KION RAG PoC - LLM Service (Ollama)
"""

import ollama
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from .config import settings


# === 프롬프트 로드 ===
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(name: str) -> str:
    """프롬프트 파일 로드"""
    prompt_file = PROMPTS_DIR / f"{name}.txt"
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"[Warning] Prompt file not found: {prompt_file}")
        return ""

# 프롬프트 로드 (모듈 로드 시)
SYSTEM_PROMPT = load_prompt("recommendation_json")
STREAM_SYSTEM_PROMPT = load_prompt("recommendation_stream")


def reload_prompts():
    """프롬프트 다시 로드 (런타임 중 수정 시)"""
    global SYSTEM_PROMPT, STREAM_SYSTEM_PROMPT
    SYSTEM_PROMPT = load_prompt("recommendation_json")
    STREAM_SYSTEM_PROMPT = load_prompt("recommendation_stream")
    print("[LLM] Prompts reloaded")


# Simple in-memory cache
_cache: Dict[str, tuple] = {}  # key -> (result, timestamp)
CACHE_TTL = 300  # 5 minutes


def _get_cache_key(query: str, eq_ids: List[str]) -> str:
    """Generate cache key from query and equipment IDs"""
    key_str = f"{query}|{'|'.join(sorted(eq_ids))}"
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_from_cache(key: str) -> Optional[Dict[str, Any]]:
    """Get cached result if still valid"""
    if key in _cache:
        result, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return result
        del _cache[key]
    return None


def _set_cache(key: str, result: Dict[str, Any]):
    """Store result in cache"""
    _cache[key] = (result, time.time())




def format_equipment_context(equipments: List[Dict[str, Any]]) -> str:
    """장비 정보를 LLM 컨텍스트 포맷으로 변환"""
    context_parts = []

    for eq in equipments:
        temp_range = ""
        if eq.get("temp_min") or eq.get("temp_max"):
            temp_range = f"{eq.get('temp_min', '?')}~{eq.get('temp_max', '?')}℃"

        context = f"""[{eq['equipment_id']}] {eq['name']}
- 카테고리: {eq.get('category', '-')}
- 파트: {eq.get('part', '-')}
- 웨이퍼: {', '.join(eq.get('wafer_sizes', []))}
- 재료: {', '.join(eq.get('materials', []))}
- 온도: {temp_range}
- 용도: {eq.get('description', '-')[:200]}
- 기관: {eq.get('institution', '-')}
"""
        context_parts.append(context)

    return "\n".join(context_parts)


def generate_recommendation(query: str, equipments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    LLM을 사용하여 장비 추천 생성

    Args:
        query: 사용자 질의
        equipments: 검색된 장비 리스트

    Returns:
        추천 결과 (recommendations, explanation)
    """
    if not equipments:
        return {
            "recommendations": [],
            "explanation": "검색 조건에 맞는 장비를 찾지 못했습니다. 다른 조건으로 다시 검색해주세요."
        }

    # Check cache first
    eq_ids = [eq["equipment_id"] for eq in equipments]
    cache_key = _get_cache_key(query, eq_ids)
    cached = _get_from_cache(cache_key)
    if cached:
        print(f"[LLM] Cache hit for query: {query[:30]}...")
        return cached

    # 장비 컨텍스트 생성
    equipment_context = format_equipment_context(equipments)

    # 프롬프트 구성
    user_prompt = f"""사용자 질의: {query}

검색된 장비 목록:
{equipment_context}

위 장비들 중에서 사용자 질의에 가장 적합한 장비를 추천해주세요.
반드시 JSON 형식으로 응답하세요."""

    try:
        response = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            options={
                "temperature": 0.3,
                "num_predict": 1024,
            }
        )

        content = response.message.content

        # JSON 파싱 시도
        import json
        import re

        # JSON 블록 추출
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 중국어 필터링 후 재시도
                filtered_content = filter_chinese(content)
                json_match = re.search(r'\{[\s\S]*\}', filtered_content)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = {"recommendations": [], "explanation": filter_chinese(content)}

            # 결과 내 중국어 필터링
            if "explanation" in result:
                result["explanation"] = filter_chinese(result["explanation"])
            if "recommendations" in result:
                for rec in result["recommendations"]:
                    if "reason" in rec:
                        rec["reason"] = filter_chinese(rec["reason"])
            _set_cache(cache_key, result)
            return result
        else:
            result = {
                "recommendations": [],
                "explanation": filter_chinese(content)
            }
            _set_cache(cache_key, result)
            return result

    except Exception as e:
        return {
            "recommendations": [],
            "explanation": f"LLM 응답 생성 중 오류가 발생했습니다: {str(e)}"
        }


def generate_recommendation_stream(query: str, equipments: List[Dict[str, Any]]):
    """
    LLM 스트리밍 응답 생성 (Generator)

    Args:
        query: 사용자 질의
        equipments: 검색된 장비 리스트

    Yields:
        스트리밍 토큰
    """
    if not equipments:
        yield "검색 조건에 맞는 장비를 찾지 못했습니다."
        return

    # 장비 컨텍스트 생성
    equipment_context = format_equipment_context(equipments)
    equipment_count = len(equipments)

    # 사용자 프롬프트
    user_prompt = f"""사용자 질의: {query}

검색된 장비 목록 (총 {equipment_count}개):
{equipment_context}

[중요] 위 {equipment_count}개 장비만 추천하세요. 같은 장비를 여러 번 설명하지 마세요."""

    try:
        stream = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": STREAM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            options={
                "temperature": 0.3,
                "num_predict": 1024,
            },
            stream=True
        )

        for chunk in stream:
            if chunk.message.content:
                # 중국어 문자 필터링
                content = filter_chinese(chunk.message.content)
                if content:
                    yield content

    except Exception as e:
        yield f"\n\n오류 발생: {str(e)}"


def filter_chinese(text: str) -> str:
    """중국어 문자를 필터링 (모든 CJK 문자 제거, 띄어쓰기 보존)"""
    import re

    # 중국어 특유의 문장 부호를 먼저 변환 (공백 포함)
    chinese_punct = {
        '：': ': ', '，': ', ', '。': '. ', '！': '! ', '？': '? ',
        '；': '; ', '"': '"', '"': '"', ''': "'", ''': "'",
        '【': '[', '】': ']', '（': '(', '）': ')',
        '、': ', ', '…': '...', '～': '~', '·': ' ',
    }
    result = text
    for ch, repl in chinese_punct.items():
        result = result.replace(ch, repl)

    # 모든 CJK 문자를 공백으로 대체 (띄어쓰기 보존)
    # U+4E00-U+9FFF: CJK Unified Ideographs
    # U+3400-U+4DBF: CJK Unified Ideographs Extension A
    # U+F900-U+FAFF: CJK Compatibility Ideographs
    result = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+', ' ', result)

    # 빈 구두점 패턴 정리 (중국어 제거 후 남은 잔여물)
    result = re.sub(r',\s*,', ',', result)  # ,, → ,
    result = re.sub(r'\.\s*\.', '.', result)  # .. → .
    result = re.sub(r',\s*\.', '.', result)  # ,. → .
    result = re.sub(r'\s*,\s*$', '', result)  # 끝의 쉼표 제거
    result = re.sub(r'^\s*,\s*', '', result)  # 시작의 쉼표 제거
    result = re.sub(r'\(\s*\)', '', result)  # 빈 괄호 제거
    result = re.sub(r'\[\s*\]', '', result)  # 빈 대괄호 제거
    result = re.sub(r':\s*$', '', result)  # 끝의 콜론 제거
    result = re.sub(r'-\s*\.', '.', result)  # -. → .
    result = re.sub(r'\s{2,}', ' ', result)  # 다중 공백 → 단일 공백
    result = re.sub(r'\s+([,.\!\?])', r'\1', result)  # 구두점 앞 공백 제거

    return result


def check_ollama_status() -> bool:
    """Ollama 서버 상태 확인"""
    try:
        ollama.list()
        return True
    except Exception:
        return False
