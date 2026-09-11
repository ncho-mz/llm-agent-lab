"""CLI 챗봇. 실제 동작은 agent/engine.py의 CharacterEngine이 담당한다.

실행: python agent/app.py [--character odysseus] [--adapter adapters/persona_skill]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Windows 콘솔은 기본 코드페이지(cp949 등)로 stdin/stdout을 열어서, 리다이렉트/파이프로
# UTF-8 한글 입력이 들어오면 깨진 서로게이트 문자로 디코딩됨 -> 강제로 UTF-8 지정.
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

from agent.engine import CharacterEngine
from config import load_config


def main(character: str, adapter_path: str | None):
    cfg = load_config()
    engine = CharacterEngine(cfg, adapter_path)
    history: list[dict] = []

    print(f"[{character}] 질문을 입력하세요 (종료: exit, 대화 기억 초기화: reset)")
    while True:
        question = input("\n> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if question.lower() == "reset":
            history.clear()
            print("[대화 기억을 지웠습니다]")
            continue
        if not question:
            continue

        answer = engine.chat(character, question, history)
        print(f"\n{answer}")

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    cfg = load_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--character", default=cfg["active_character"])
    parser.add_argument("--adapter", default=None, help="어댑터 경로 (예: adapters/persona_skill)")
    args = parser.parse_args()
    main(args.character, args.adapter)
