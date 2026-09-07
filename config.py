from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent


def load_config(path: str = "configs/model.yaml") -> dict:
    with open(REPO_ROOT / path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
