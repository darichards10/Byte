#!/usr/bin/env bash
# Build the Docker image, push to ECR, and force a new ECS deployment.
# Run this after every code change.
#
# Usage:
#   bash scripts/deploy.sh              # full deploy
#   bash scripts/deploy.sh --no-ecs-update  # build + push only (used by create_stacks.sh)

set -euo pipefail

REGION=${AWS_REGION:-us-east-1}
PROJECT=byte-bot
CLUSTER=byte-cluster
SERVICE=byte-bot-service
NO_ECS_UPDATE=false

for arg in "$@"; do
  [[ "$arg" == "--no-ecs-update" ]] && NO_ECS_UPDATE=true
done

# Get ECR URI
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${PROJECT}"

echo "Building Docker image..."
docker build -t "${PROJECT}:latest" .
echo "  ✓ Build complete"

echo "Logging in to ECR..."
aws ecr get-login-password --region "${REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Tagging and pushing to ECR..."
docker tag "${PROJECT}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"
echo "  ✓ Pushed: ${ECR_URI}:latest"

if [[ "${NO_ECS_UPDATE}" == "true" ]]; then
  echo "Skipping ECS update (--no-ecs-update)"
  exit 0
fi

echo "Forcing new ECS deployment..."
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${SERVICE}" \
  --force-new-deployment \
  --region "${REGION}" \
  --output json | python3 -c "import sys,json; s=json.load(sys.stdin)['service']; print(f'  Status: {s[\"status\"]} | Running: {s[\"runningCount\"]} | Desired: {s[\"desiredCount\"]}')"

echo ""
echo "Deployment initiated. ECS will pull the new image and replace the running task."
echo "Monitor progress:"
echo "  aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${REGION}"
echo "  aws logs tail /ecs/byte --follow --region ${REGION}"
