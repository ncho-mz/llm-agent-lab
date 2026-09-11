"""링크(URL)를 캐릭터의 배경 지식 문서로 가져온다.

가져오기 전에 robots.txt를 확인한다 -- 사이트가 명시적으로 수집을 막아둔 경우가 실제로
있었고(예: AI 봇 전면 차단), 그런 곳의 내용을 긁어오는 건 운영자의 의사에 반한다.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

USER_AGENT = "llm-agent-lab"


_AI_AGENTS = ("ClaudeBot", "GPTBot", "CCBot")


def _robots_allows(url: str) -> tuple[bool, str]:
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))

    parser = urllib.robotparser.RobotFileParser()
    try:
        # RobotFileParser.read()는 기본 urllib UA를 쓰는데, 그걸 403으로 막는 사이트가 있다.
        # 그러면 robotparser가 "전체 금지"로 해석해버리므로 직접 받아서 넘긴다.
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            parser.parse(resp.read().decode("utf-8", errors="replace").splitlines())
    except Exception:
        # robots.txt가 없거나 못 읽으면 차단으로 보지 않는다
        return True, ""

    if not parser.can_fetch(USER_AGENT, url) or not parser.can_fetch("*", url):
        return False, f"{parts.netloc} 의 robots.txt가 이 주소의 수집을 허용하지 않습니다."

    # 사이트가 AI 크롤러를 지목해 막아뒀다면, 우리 이름이 그 목록에 없더라도 같은 취급을 한다.
    # 우리도 결국 LLM에 먹이려고 가져가는 것이라, 이름만 바꿔 통과하는 건 의도를 우회하는 것.
    for bot in _AI_AGENTS:
        if not parser.can_fetch(bot, url):
            return False, f"{parts.netloc} 은 AI 크롤러의 수집을 거부하고 있습니다 ({bot} 차단)."
    return True, ""


def _safe_filename(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    stem = f"{parts.netloc}{parts.path}".strip("/") or parts.netloc
    stem = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", stem).strip("_")
    return f"{stem[:80] or 'link'}.md"


def fetch_url_to_docs(url: str, docs_dir: Path) -> tuple[bool, str]:
    """URL 본문을 추출해 docs_dir에 .md로 저장한다. (성공여부, 메시지)"""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False, "⚠️ http:// 또는 https:// 로 시작하는 주소를 넣어주세요."

    allowed, reason = _robots_allows(url)
    if not allowed:
        return False, f"⚠️ {reason}"

    try:
        import trafilatura

        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded) if downloaded else None
    except Exception as e:
        return False, f"⚠️ 가져오기 실패: {e}"

    if not text or len(text.strip()) < 100:
        return False, "⚠️ 본문을 충분히 추출하지 못했습니다 (로그인이 필요하거나 스크립트로 그려지는 페이지일 수 있어요)."

    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / _safe_filename(url)
    path.write_text(f"출처: {url}\n\n{text.strip()}\n", encoding="utf-8")
    return True, f"✅ '{path.name}' 저장 ({len(text):,}자)"
