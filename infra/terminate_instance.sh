#!/usr/bin/env bash
# launch_instance.sh로 띄운 인스턴스를 완전히 종료(terminate)한다.
# 비용이 계속 나가는 걸 막으려면 쓸 때마다 잊지 말고 실행할 것.
#
# 실행: cd infra && ./terminate_instance.sh
set -euo pipefail

if [ ! -f .last_instance_id ]; then
  echo "종료할 인스턴스 ID를 못 찾았어요 (.last_instance_id 없음)."
  echo "AWS 콘솔 EC2 화면에서 직접 확인해서 종료해주세요."
  exit 1
fi

INSTANCE_ID="$(cat .last_instance_id)"
echo "종료할 인스턴스: $INSTANCE_ID"
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
echo "종료 완료."
rm -f .last_instance_id
