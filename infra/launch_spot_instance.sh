#!/usr/bin/env bash
# g4dn.xlarge(기본) 스팟 인스턴스를 띄운다. 실행 전에 infra/README.md의 0~1단계
# (AWS CLI 설정, GPU 쿼터 승인)가 끝나 있어야 한다.
#
# 실행: cd infra && ./launch_spot_instance.sh
set -euo pipefail

INSTANCE_TYPE="${INSTANCE_TYPE:-g4dn.xlarge}"   # 메모리 부족하면 g5.xlarge로 변경
MARKET_TYPE="${MARKET_TYPE:-spot}"              # spot 쿼터 승인 전엔 MARKET_TYPE=on-demand 로 실행
KEY_NAME="llm-agent-lab-key"
SG_NAME="llm-agent-lab-sg"
REGION="$(aws configure get region)"

echo "== 자격증명 확인 =="
aws sts get-caller-identity --output text >/dev/null

echo "== 키 페어 확인/생성 =="
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query 'KeyMaterial' --output text > "${KEY_NAME}.pem"
  chmod 400 "${KEY_NAME}.pem"
  echo "새 키 페어 생성: ${KEY_NAME}.pem (이 파일로 SSH 접속함, 잃어버리지 말 것)"
else
  echo "기존 키 페어 사용: $KEY_NAME"
fi

echo "== 내 퍼블릭 IP 확인 =="
MY_IP="$(curl -s https://checkip.amazonaws.com)"
echo "내 IP: ${MY_IP}"

echo "== 보안그룹 확인/생성 (내 IP에서만 SSH 허용) =="
SG_ID="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")"
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
  SG_ID="$(aws ec2 create-security-group --group-name "$SG_NAME" \
    --description "llm-agent-lab: SSH only" --vpc-id "$VPC_ID" --query 'GroupId' --output text)"
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port 22 --cidr "${MY_IP}/32" >/dev/null
  echo "새 보안그룹 생성: $SG_ID (SSH를 ${MY_IP}/32 에서만 허용)"
else
  echo "기존 보안그룹 사용: $SG_ID"
fi

echo "== 최신 Deep Learning AMI(Ubuntu, CUDA) 조회 =="
AMI_ID="$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=Deep Learning AMI GPU PyTorch*Ubuntu*" "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)"
echo "AMI: $AMI_ID"

echo "== 인스턴스 요청 (${INSTANCE_TYPE}, ${MARKET_TYPE}) =="
MARKET_OPTS=()
if [ "$MARKET_TYPE" = "spot" ]; then
  MARKET_OPTS=(--instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time"}}')
fi
INSTANCE_ID="$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  "${MARKET_OPTS[@]}" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llm-agent-lab}]' \
  --query 'Instances[0].InstanceId' --output text)"
echo "인스턴스 ID: $INSTANCE_ID (running 상태 대기 중...)"

aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"

echo ""
echo "== 완료 =="
echo "인스턴스 ID: $INSTANCE_ID"
echo "퍼블릭 IP:   $PUBLIC_IP"
echo "접속 명령:   ssh -i ${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo "$INSTANCE_ID" > .last_instance_id
