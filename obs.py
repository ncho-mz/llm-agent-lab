"""Datadog LLM Observability 계측.

DD_LLMOBS_ENABLED=1 일 때만 실제로 추적하고, 그 외엔 아무 일도 하지 않는 no-op 데코레이터가
된다 -- 로컬에서 ddtrace 없이 개발할 때도 코드를 그대로 돌리기 위해서다.

GPU 서버에서 켜려면:
    export DD_LLMOBS_ENABLED=1
    export DD_LLMOBS_AGENTLESS_ENABLED=1   # Datadog Agent 없이 직접 전송
    export DD_API_KEY=...
    export DD_SITE=datadoghq.com           # 계정 리전에 맞게
    export DD_LLMOBS_ML_APP=character-chat
"""
import os


def _noop(*args, **kwargs):
    # @deco 와 @deco(...) 두 형태 모두 지원
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def decorator(fn):
        return fn

    return decorator


def _enabled() -> bool:
    return os.environ.get("DD_LLMOBS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


if _enabled():
    from ddtrace.llmobs import LLMObs
    from ddtrace.llmobs.decorators import llm, retrieval, workflow

    LLMObs.enable(ml_app=os.environ.get("DD_LLMOBS_ML_APP", "character-chat"))
    print("[obs] Datadog LLM Observability 활성화됨")
else:
    llm = retrieval = workflow = _noop
