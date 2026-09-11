"""외부 정보 조회 도구. RAG(캐릭터 문서)로 답이 부족할 때 보조로 쓴다.

중요 — 여기서 가져온 내용은 전부 '출처가 불분명한 참고 자료'로 취급한다. 외부 문서에
"이전 지시를 무시하라" 같은 문장이 섞여 들어와도 모델이 지시로 받아들이면 안 되므로,
engine 쪽에서 페르소나(시스템 메시지)와 분리된 자리에 넣고 '데이터일 뿐'이라고 못박는다.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from core import obs

_TIMEOUT = 15
_UA = "llm-agent-lab/0.1 (character chat sandbox)"


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.load(resp)


@obs.retrieval(name="book_search")
def search_books(query: str, limit: int = 3) -> list[str]:
    """Open Library에서 책 정보를 찾는다. API 키가 필요 없고 상업적 이용도 허용된 공개 API."""
    params = urllib.parse.urlencode(
        {
            "q": query,
            "limit": limit,
            "fields": "title,author_name,first_publish_year,subject",
        }
    )
    try:
        data = _get_json(f"https://openlibrary.org/search.json?{params}")
    except Exception as e:  # 네트워크 실패로 대화 자체가 끊기면 안 된다
        print(f"[tools] 책 검색 실패: {e}")
        return []

    results = []
    for doc in data.get("docs", [])[:limit]:
        authors = ", ".join(doc.get("author_name", [])[:2]) or "저자 미상"
        year = doc.get("first_publish_year", "연도 미상")
        subjects = ", ".join(doc.get("subject", [])[:5])
        line = f"《{doc.get('title', '제목 미상')}》 — {authors}, {year}"
        if subjects:
            line += f" (주제: {subjects})"
        results.append(line)
    return results


@obs.retrieval(name="web_search")
def search_web(query: str, limit: int = 3) -> list[str]:
    """DuckDuckGo 웹 검색. API 키가 필요 없다."""
    try:
        from ddgs import DDGS

        hits = DDGS().text(query, max_results=limit)
    except Exception as e:
        print(f"[tools] 웹 검색 실패: {e}")
        return []

    results = []
    for hit in hits:
        body = (hit.get("body") or "").strip().replace("\n", " ")
        if body:
            results.append(f"{hit.get('title', '')}: {body[:400]}")
    return results


def gather_external(query: str, limit: int = 3) -> list[str]:
    """책 정보 + 웹 검색을 합쳐서 반환. 캐릭터 문서로 부족할 때만 호출된다."""
    return search_books(query, limit=limit) + search_web(query, limit=limit)
