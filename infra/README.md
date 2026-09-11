# 인프라 세팅 체크리스트

목표: 최대한 저렴하게 GPU 스팟 인스턴스를 띄워서 `llm-agent-lab`을 돌릴 수 있는 상태로 만든다.
아래 순서대로 진행하면 된다. 1번(쿼터 요청)이 승인까지 시간이 걸릴 수 있는 유일한 병목이라 제일 먼저 넣어두는 게 좋다.

## 0. 준비물

- AWS 계정 (콘솔 로그인 가능해야 함)
- IAM 사용자의 **프로그래밍 방식 액세스 키**(access key / secret key). 없다면:
  IAM 콘솔 → Users → 본인 사용자 → Security credentials → Create access key
- 로컬에 AWS CLI 설치:
  ```bash
  pip install awscli
  aws configure   # access key, secret key, region(예: us-east-1) 입력
  ```

## 1. GPU 인스턴스 쿼터 확인/신청 (제일 먼저, 지금 바로)

신규/기존 계정 모두 GPU 인스턴스(G 계열) 쿼터가 기본 0인 경우가 많다. 콘솔에서:

1. **Service Quotas** 콘솔 → **Amazon Elastic Compute Cloud (Amazon EC2)** 검색
2. 아래 두 항목을 확인:
   - `Running On-Demand G and VT instances`
   - `All G and VT Spot Instance Requests`
3. 현재 값이 0이거나 4(vCPU) 미만이면 **Request increase at account level**로 4~8 vCPU 정도 요청
   (g4dn.xlarge/g5.xlarge는 vCPU 4개짜리라 4면 충분)
4. 승인 대기 (몇 분~며칠 소요될 수 있음, AWS가 이메일로 알려줌)

CLI로 현재 값 확인만 하고 싶으면 (자격증명 설정 후):
```bash
aws service-quotas get-service-quota --service-code ec2 --quota-code L-3819A6DF --region us-east-1  # On-Demand G/VT
aws service-quotas get-service-quota --service-code ec2 --quota-code L-3819A6DF --region us-east-1  # (Spot 쿼타 코드는 콘솔에서 확인 권장, 리전/계정별로 코드가 조금씩 다를 수 있음)
```

## 2. 스팟 인스턴스 띄우기 (쿼터 승인 후)

`infra/launch_instance.sh` 실행 — 자동으로:
- 이 랩 전용 키 페어(`llm-agent-lab-key`) 생성 (없으면)
- 내 현재 IP만 SSH(22번 포트) 허용하는 보안그룹 생성 (없으면)
- 최신 AWS Deep Learning AMI(Ubuntu, CUDA 포함) 조회
- g4dn.xlarge **스팟** 인스턴스 요청

```bash
cd infra
chmod +x launch_instance.sh
./launch_instance.sh
```

스팟 쿼터가 아직 승인 안 됐으면(Service Quotas에서 "All G and VT Spot Instance Requests"가 0), 온디맨드로 대신 실행:
```bash
MARKET_TYPE=on-demand ./launch_instance.sh
```
(스팟 쿼터 증설은 신청해두고 기다리면서, 그동안은 온디맨드로 진행하면 됨. "Running On-Demand G and VT instances" 쿼터가 이미 있으면 바로 가능.)

인스턴스가 뜨면 스크립트가 퍼블릭 IP를 출력한다. 접속:
```bash
ssh -i llm-agent-lab-key.pem ubuntu@<출력된 IP>
```

## 3. Datadog Agent 설치 (선택, 관측을 붙일 때)

### SSI는 쓰지 않는다

설치 스크립트에 `DD_APM_INSTRUMENTATION_ENABLED=host`와 `DD_APM_INSTRUMENTATION_LIBRARIES=python:N`을
주면(Single Step Instrumentation) Agent가 자체 ddtrace를 `/opt/datadog-packages/` 밑에 받아두고,
`/etc/ld.so.preload`로 모든 프로세스의 exec을 가로채 `PYTHONPATH`에 그 경로를 꽂는다.
`PYTHONPATH`는 venv의 site-packages보다 **앞**이라, venv를 activate해도 `import ddtrace`는
주입된 쪽을 집어온다. 그러면 `pip show ddtrace`가 보여주는 버전과 실제로 도는 버전이 달라져서
`core/obs.py`가 왜 깨지는지 추적할 수 없게 된다. 그래서 APM은 앱을 `ddtrace-run`으로 띄워서 직접 건다.

### Agent 설치 (APM 주입 없이)

```bash
DD_API_KEY=<키> DD_SITE="datadoghq.com" DD_ENV=dev bash -c "$(curl -L https://install.datadoghq.com/scripts/install_script_agent7.sh)"
```

`DD_APM_INSTRUMENTATION_*` 변수가 없는 것이 핵심이다.

### APM 수신 켜기

`/etc/datadog-agent/datadog.yaml`:
```yaml
apm_config:
  enabled: true
```

### GPU 모니터링 켜기 (NVML 인티그레이션)

> 먼저 시도했던 Datadog 내장 GPU Monitoring(eBPF 기반)은 이 환경에서 동작하지 않았다.
> Amazon Linux 2023 / 커널 6.12.103 / Tesla T4 / Agent 7.83.1 / SELinux Permissive로 요구사항을
> 전부 충족하고, sysprobe 로그에도 `Agent found NVML library`와 `module gpu started`가 찍히는데도
> `datadog-agent status`의 `Discovered GPUs`가 끝까지 비어 있었다. 게다가 문서가 안내하는
> `enable_nvml_detection` 키는 7.83에서 `Unknown key in config file` 경고가 난다 -- 이미 없어진 키다.
> 그래서 eBPF를 타지 않고 NVML만 읽는 community 인티그레이션으로 간다.

`nvidia-smi`가 GPU를 보는지 먼저 확인한다. 여기서 안 보이면 Datadog 문제가 아니다.
```bash
nvidia-smi
```

인티그레이션과 의존성 설치:
```bash
sudo -u dd-agent datadog-agent integration install -t datadog-nvml==1.0.9
sudo -u dd-agent /opt/datadog-agent/embedded/bin/pip install pynvml grpcio
```

설정 파일:
```bash
sudo tee /etc/datadog-agent/conf.d/nvml.d/conf.yaml >/dev/null <<'YAML'
init_config:

instances:
  - {}
YAML
sudo chown dd-agent:dd-agent /etc/datadog-agent/conf.d/nvml.d/conf.yaml
sudo chmod 0640 /etc/datadog-agent/conf.d/nvml.d/conf.yaml
```

**protobuf 우회가 필요하다.** 이 인티그레이션의 `api_pb2.py`는 옛날 protoc로 생성된 것이라
Agent에 들어있는 최신 protobuf(Python 3.13)와 충돌해서 import 자체가 깨진다
(`TypeError: Descriptors cannot be created directly`). 쿠버네티스 pod-resource 매핑용 코드라
EC2에서는 쓰지도 않지만 모듈 최상단에서 import된다. 순수 파이썬 파싱으로 돌리면 통과한다:
```bash
sudo mkdir -p /etc/systemd/system/datadog-agent.service.d
printf '[Service]
Environment="PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python"
'   | sudo tee /etc/systemd/system/datadog-agent.service.d/protobuf.conf >/dev/null
sudo systemctl daemon-reload && sudo systemctl restart datadog-agent
```

확인 -- 재시작을 기다리지 않고 체크만 바로 돌려볼 수 있다:
```bash
sudo -u dd-agent env PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python datadog-agent check nvml
sudo datadog-agent status | grep -A6 "nvml ("
```
`Instance ID: nvml:... [OK]` 와 `Metric Samples`가 나오면 된다. `nvml.gpu_utilization`,
`nvml.fb_used`, `nvml.temperature` 등이 들어온다.

### 손대지 말 것

- `/etc/datadog-agent/conf.d/nvidia.d/` -- `nvidia`라는 체크는 존재하지 않는다(있는 건
  `nvidia_nim`, `nvidia_triton`, `dcgm`). 디렉터리를 만들어두면 `Check nvidia not found in Catalog`
  에러만 계속 찍힌다.
- `enable_nvml_detection` -- 7.83에는 없는 키다.
- sysprobe는 부팅 시 자동 시작이 아닐 수 있다. 내장 GPU Monitoring을 쓸 거라면
  `sudo systemctl enable datadog-agent-sysprobe`를 꼭 같이 해야 재부팅 후에도 살아난다.

### 앱을 APM과 함께 띄우기

```bash
export DD_LLMOBS_ENABLED=1 DD_TRACE_ENABLED=true
export DD_LLMOBS_ML_APP=character-chat DD_SERVICE=character-chat DD_ENV=dev
ddtrace-run python web/app.py --adapter adapters/persona_skill --port 8111
```

의도한 ddtrace가 잡혔는지 확인 (경로가 venv 안이어야 한다):
```bash
python -c "import ddtrace; print(ddtrace.__version__, ddtrace.__file__)"
```

## 4. 사용 후 정리 (비용 관리, 매번 잊지 말 것)

```bash
cd infra
./terminate_instance.sh
```

인스턴스를 완전히 종료(terminate)한다. 잠깐 쉬었다가 이어서 쓸 거면 콘솔에서 stop만 해도 되지만,
스팟 인스턴스는 stop이 아니라 보통 terminate로 관리하는 게 깔끔하다(재시작 시 새 스팟 요청).

## 참고: g4dn.xlarge로 메모리가 부족하면

`infra/launch_instance.sh` 상단의 `INSTANCE_TYPE` 값을 `g5.xlarge`로 바꿔서 다시 실행하면 된다
(A10G 24GB, 스팟 기준 시간당 약 $0.44 — g4dn 대비 조금 더 비싸지만 메모리 여유가 큼).
