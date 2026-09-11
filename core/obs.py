"""Datadog LLM Observability 계측.

DD_LLMOBS_ENABLED=1 일 때만 실제로 추적하고, 그 외엔 아무 일도 하지 않는 no-op 데코레이터가
된다 -- 로컬에서 ddtrace 없이 개발할 때도 코드를 그대로 돌리기 위해서다.

APM은 SSI(Single Step Instrumentation)로 주입하지 않고 ddtrace-run으로 직접 건다. SSI를 켜면
Agent가 받아둔 ddtrace가 PYTHONPATH를 통해 venv 것보다 먼저 잡혀서, 아래 import가 실제로
어떤 버전을 집어오는지 알 수 없게 된다 (requirements.txt 참고).

호스트에 Datadog Agent가 떠 있을 때:
    export DD_LLMOBS_ENABLED=1 DD_TRACE_ENABLED=true
    export DD_LLMOBS_ML_APP=character-chat DD_SERVICE=character-chat DD_ENV=dev
    ddtrace-run python web/app.py --adapter adapters/persona_skill --port 8111

Agent 없이 Datadog으로 바로 보낼 때(agentless):
    export DD_LLMOBS_AGENTLESS_ENABLED=1 DD_API_KEY=... DD_SITE=datadoghq.com
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
