# CUDA 런타임 베이스. 모델 가중치(약 16GB)는 이미지에 넣지 않고 호스트의 HF 캐시를
# 볼륨 마운트해서 쓴다 -- 이미지에 넣으면 20GB가 넘어가고 빌드/배포가 매번 무거워진다.
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    HF_HOME=/root/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# 의존성만 먼저 복사해서 레이어 캐시를 살린다 (코드만 바뀌면 재설치 안 함)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8111

# 캐릭터 데이터(characters/)와 어댑터(adapters/)는 볼륨으로 마운트하는 것을 전제로 한다.
# 웹에서 페르소나를 수정하거나 문서를 업로드하면 컨테이너 밖에 남아야 하기 때문.
# ddtrace-run으로 띄우되, DD_TRACE_ENABLED가 false면(기본값) 아무것도 추적하지 않는다.
# SSI 주입 대신 이 방식을 쓰는 이유는 requirements.txt의 ddtrace 항목 참고.
CMD ["ddtrace-run", "python", "web/app.py", "--adapter", "adapters/persona_skill", "--port", "8111"]
