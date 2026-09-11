from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]  # core/ 한 단계 위가 저장소 루트


def load_config(path: str = "configs/model.yaml") -> dict:
    with open(REPO_ROOT / path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
