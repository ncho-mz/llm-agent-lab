import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent

# 환경변수로 덮어쓸 수 있는 값들. GPU 서버에서는 configs/model.yaml을 직접 고치는 대신
# 이 환경변수를 쓰면 된다 -- 파일을 수정해두면 git pull이 매번 충돌로 막히기 때문.
_ENV_OVERRIDES = {
    "base_model": "LLM_LAB_BASE_MODEL",
    "load_in_4bit": "LLM_LAB_LOAD_IN_4BIT",
    "max_new_tokens": "LLM_LAB_MAX_NEW_TOKENS",
    "active_character": "LLM_LAB_CHARACTER",
}


def _coerce(key: str, raw: str):
    if key == "load_in_4bit":
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if key == "max_new_tokens":
        return int(raw)
    return raw


def load_config(path: str = "configs/model.yaml") -> dict:
    with open(REPO_ROOT / path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for key, env_name in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is not None:
            cfg[key] = _coerce(key, raw)
    return cfg
