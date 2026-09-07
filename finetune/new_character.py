"""새 캐릭터 폴더 골격을 만든다. 이후 persona.md / docs / train.jsonl은 직접 채워 넣는다
(나중에 UI가 생기면 "캐릭터 스크립트 작성" 화면이 이 파일들을 채우게 될 자리).

실행: python finetune/new_character.py <name>
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import characters

PERSONA_TEMPLATE = """당신은 <캐릭터 이름>입니다. <성격/말투/배경을 1인칭 지시문으로 서술>.
"""

TRAIN_TEMPLATE = (
    '{"instruction": "당신은 누구십니까?", "response": "<이 캐릭터라면 할 법한 대답>"}\n'
)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python finetune/new_character.py <name>")
    name = sys.argv[1]

    char_dir = characters.character_dir(name)
    if char_dir.exists():
        raise SystemExit(f"{char_dir} 가 이미 있습니다.")

    characters.docs_dir(name).mkdir(parents=True)
    characters.persona_path(name).write_text(PERSONA_TEMPLATE, encoding="utf-8")
    characters.train_data_path(name).write_text(TRAIN_TEMPLATE, encoding="utf-8")
    (characters.docs_dir(name) / ".gitkeep").touch()

    print(f"생성됨: {char_dir}")
    print("다음을 채우세요:")
    print(f"  1. {characters.persona_path(name)}  (성격/말투)")
    print(f"  2. {characters.docs_dir(name)}/*.md  (참고 문서, RAG용)")
    print(f"  3. {characters.train_data_path(name)}  (대화 예시, 파인튜닝용)")
    print(f"그 다음: python rag/build_index.py --character {name}")
    print(f"        python finetune/train_qlora.py --character {name}")
    print(f"        python agent/app.py --character {name}")


if __name__ == "__main__":
    main()
