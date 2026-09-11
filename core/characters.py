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


def avatar_path(name: str) -> Path | None:
    """캐릭터 이미지가 있으면 그 경로. 없으면 None (웹에서 기본 애니메이션을 대신 보여준다).

    나중에 이미지 생성 단계에서 여기에 파일을 떨궈 넣으면 그대로 교체된다.
    """
    for suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        candidate = character_dir(name) / f"avatar{suffix}"
        if candidate.exists():
            return candidate
    return None


def display_name_path(name: str) -> Path:
    return character_dir(name) / "name.txt"


def load_display_name(name: str) -> str:
    """화면에 보여줄 이름. 없으면 폴더 이름을 그대로 쓴다."""
    path = display_name_path(name)
    if path.exists():
        label = path.read_text(encoding="utf-8").strip()
        if label:
            return label
    return name


def save_display_name(name: str, label: str) -> None:
    display_name_path(name).write_text(label.strip() + "\n", encoding="utf-8")


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
