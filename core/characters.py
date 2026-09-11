"""캐릭터별 파일 경로 규칙. 캐릭터는 코드가 아니라 characters/<name>/ 밑의
데이터(페르소나, 참고문서, 학습데이터)로 정의된다 -> 새 캐릭터 = 새 폴더."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]  # core/ 한 단계 위가 저장소 루트
CHARACTERS_DIR = REPO_ROOT / "characters"


def character_dir(name: str) -> Path:
    return CHARACTERS_DIR / name


def persona_path(name: str) -> Path:
    return character_dir(name) / "persona.md"


def docs_dir(name: str) -> Path:
    return character_dir(name) / "docs"


def chroma_dir(name: str) -> Path:
    return character_dir(name) / "chroma_db"


def train_data_path(name: str) -> Path:
    return character_dir(name) / "train.jsonl"


def adapter_dir(name: str) -> Path:
    return character_dir(name) / "adapter"


def load_persona(name: str) -> str:
    path = persona_path(name)
    if not path.exists():
        raise SystemExit(f"{path} 가 없습니다. characters/{name}/persona.md 를 먼저 작성하세요.")
    return path.read_text(encoding="utf-8").strip()


def list_characters() -> list[str]:
    """persona.md와 train.jsonl을 둘 다 가진, 학습에 쓸 수 있는 캐릭터 이름 목록."""
    if not CHARACTERS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in CHARACTERS_DIR.iterdir()
        if d.is_dir() and persona_path(d.name).exists() and train_data_path(d.name).exists()
    )
