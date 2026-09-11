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

### GPU 모니터링 켜기

요구사항: Agent v7.80 이상(7.82.0은 커널 패닉 이슈로 피할 것), 커널 5.8 이상, NVIDIA 드라이버 450.51 이상.
g4dn + Deep Learning AMI면 드라이버/커널은 이미 충족한다.

`/etc/datadog-agent/datadog.yaml` — `gpu.enabled`만 중첩이고 나머지 둘은 최상위 키다:
```yaml
gpu:
  enabled: true
collect_gpu_tags: true
enable_nvml_detection: true
```

`/etc/datadog-agent/system-probe.yaml` (없으면 예제에서 만든다):
```bash
sudo -u dd-agent install -m 0640 /etc/datadog-agent/system-probe.yaml.example /etc/datadog-agent/system-probe.yaml
```
```yaml
gpu_monitoring:
  enabled: true
```

`datadog.yaml`만 고치면 eBPF 모듈이 로드되지 않아 **메트릭이 하나도 안 들어온다.** 둘 다 필요하다.

```bash
sudo systemctl restart datadog-agent
sudo systemctl restart datadog-agent-sysprobe
sudo datadog-agent status
```

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
