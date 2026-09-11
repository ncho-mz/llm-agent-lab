# llm-agent-lab

RAG + QLoRA 파인튜닝으로 나만의 캐릭터를 만드는 학습용 샌드박스. 저렴한 AWS GPU 스팟 인스턴스 위에서
Hugging Face 오픈 웨이트 모델(`Qwen/Qwen3-8B`, Apache 2.0)을 캐릭터 말투로 QLoRA 파인튜닝하고,
RAG로 그 캐릭터의 설정 문서를 검색해서 답변하는 CLI 챗봇까지 만들어본다.

## 구조

캐릭터는 코드가 아니라 **데이터**다 — 새 캐릭터를 만드는 건 `characters/` 밑에 새 폴더를 만드는 것.

```
configs/model.yaml          # 모델/RAG 설정 (모든 캐릭터 공통)
characters.py                # 캐릭터별 경로 규칙
characters/
  <이름>/
    persona.md                # 성격/말투 (시스템 프롬프트)
    docs/                      # RAG용 참고 문서
    train.jsonl                # QLoRA 학습용 대화 예시
    chroma_db/                 # build_index.py 실행 결과 (자동 생성)
    adapter/                    # train_qlora.py 실행 결과 (자동 생성)
rag/                          # 문서 임베딩 -> 벡터 인덱스 -> 검색
finetune/
  new_character.py             # 새 캐릭터 폴더 골격 생성
  train_qlora.py                # QLoRA 학습
agent/app.py                   # RAG + (있으면) 파인튜닝 어댑터를 붙인 CLI 챗봇
```

새 캐릭터 만들기: `python finetune/new_character.py <이름>` 으로 골격을 만들고,
`persona.md` / `docs/*.md` / `train.jsonl`을 채우면 된다. 이후 모든 명령에 `--character <이름>`을
붙이면 그 캐릭터로 동작한다 (생략하면 `configs/model.yaml`의 `active_character` 사용).

## 1단계: 로컬에서 파이프라인 검증 (비용 $0, GPU 불필요)

`configs/model.yaml`이 기본값(`Qwen/Qwen3-0.6B`, `load_in_4bit: false`)이면 GPU 없이도 전부 돌아간다.
목적은 "코드가 제대로 붙어있는지" 확인하는 것이지, 답변 품질을 보는 게 아니다 (0.6B는 작아서 품질은 낮음).

```bash
python -m venv .venv
.venv\Scripts\activate          # (Windows) / source .venv/bin/activate (Linux/Mac)
pip install -r requirements.txt

python rag/build_index.py --character odysseus
python agent/app.py --character odysseus       # RAG만 붙은 상태로 대화 (아직 어댑터 없음)
```

여기까지 에러 없이 돌면 GPU로 넘어갈 준비가 된 것.

## 2단계: AWS GPU 스팟 인스턴스에서 진짜로 학습

### 인스턴스 띄우기

1. **쿼터 확인**: 신규/기존 계정 모두 GPU 인스턴스(G 계열) 서비스 쿼터가 0으로 잡혀있는 경우가 많다.
   AWS 콘솔 → Service Quotas → EC2 → "Running On-Demand G and VT instances" (스팟도 별도로 "All G and VT Spot Instance Requests" 쿼터 확인) 에서 증설 요청부터 넣어둔다. 승인까지 시간이 걸릴 수 있다.
2. **인스턴스 시작**: `cd infra && ./launch_spot_instance.sh` (스팟 쿼터 승인 전이면 `MARKET_TYPE=on-demand ./launch_spot_instance.sh`). 자세한 건 `infra/README.md` 참고.
3. SSH로 접속 후:
   ```bash
   git clone <이 저장소>
   cd llm-agent-lab
   pip install -r requirements.txt
   ```

### 실행

```bash
# configs/model.yaml 을 다음처럼 수정:
#   base_model: Qwen/Qwen3-8B
#   load_in_4bit: true

python rag/build_index.py --character odysseus
python finetune/train_qlora.py --character odysseus   # 완료되면 characters/odysseus/adapter 생성
python agent/app.py --character odysseus                # 어댑터가 있으면 자동으로 적용됨
```

`characters/<이름>/adapter`가 있고 없고에 따라 `agent/app.py`가 자동으로 다르게 동작하니,
어댑터 생성 전/후로 같은 질문을 던져보면 파인튜닝이 실제로 뭘 바꾸는지 눈으로 확인할 수 있다.

### 비용 관리 (중요)

- **다 쓰면 바로 `cd infra && ./terminate_instance.sh` 로 종료한다.** 켜둔 채로 방치하면 계속 과금된다.
- 학습 자체는 보통 몇 분~1시간 이내로 끝난다 (예시 데이터셋이 작음). 하루 종일 켜둘 필요 없음.
- 스팟 인스턴스는 중간에 회수(interrupt)될 수 있다 — 지금 데이터셋 규모라면 크게 문제되지 않지만, 데이터셋을 키운다면 체크포인트 저장 로직을 추가하는 걸 권장.

## 3단계: 웹 앱 + 컨테이너

### 직접 실행
```bash
python web/app.py --adapter adapters/persona_skill --port 8111
```

### Docker로 실행
```bash
# 호스트에 nvidia-container-toolkit이 설치돼 있어야 컨테이너가 GPU를 본다
docker compose up --build
```

모델 가중치(약 16GB)는 이미지에 넣지 않고 호스트의 `~/.cache/huggingface`를 마운트해서 쓴다.
`characters/`와 `adapters/`도 마운트하므로, 웹에서 페르소나를 수정하거나 문서를 업로드하면
컨테이너를 지워도 남는다.

### 접속
EC2 보안그룹에서 **8111 포트를 내 IP에만** 열고 `http://<퍼블릭IP>:8111` 로 접속한다.
0.0.0.0/0으로 열면 누구나 이 GPU로 추론을 돌릴 수 있으니 피할 것.

### 관측 (Datadog, 선택)
```bash
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_AGENTLESS_ENABLED=1    # Datadog Agent 없이 직접 전송
export DD_API_KEY=...
```
켜지 않으면 `obs.py`가 no-op으로 동작하므로 ddtrace 설정 없이도 그대로 돌아간다.
계측 지점은 RAG 검색(retrieval), 모델 생성(llm), 요청 전체(workflow) 세 곳이다.

## 다음 단계 아이디어

- `characters/<이름>/train.jsonl`에 대화 예시를 더 추가해보며 결과 비교
- `finetune/train_qlora.py`의 `target_modules`, `r`, 에폭 수 등을 조정해보며 결과 비교
- `agent/app.py`에 도구 호출(tool use)을 추가해서 진짜 "에이전트"로 확장
- 캐릭터를 하나 더 만들어서 (`python finetune/new_character.py <이름>`) 같은 파이프라인이 다른 캐릭터에도 그대로 재사용되는지 확인
