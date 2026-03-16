#!/usr/bin/env bash
# Deploy all CloudFormation stacks in dependency order.
# Run once for initial setup. After that, use deploy.sh for code changes.
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - Secrets stored in SSM (run ssm_put_secrets.sh first)
#   - S3 bucket for nested stack templates (set TEMPLATES_BUCKET below)
#
# Usage:
#   export TEMPLATES_BUCKET=my-cfn-templates-bucket
#   bash scripts/create_stacks.sh

set -euo pipefail

REGION=${AWS_REGION:-us-east-1}
PROJECT=byte-bot
INFRA_DIR="$(dirname "$0")/../infra"

if [[ -z "${TEMPLATES_BUCKET:-}" ]]; then
  echo "ERROR: Set TEMPLATES_BUCKET env var to your S3 bucket for CloudFormation templates."
  echo "  export TEMPLATES_BUCKET=my-bucket-name"
  exit 1
fi

echo "Uploading CloudFormation templates to s3://${TEMPLATES_BUCKET}/${PROJECT}/..."
aws s3 sync "${INFRA_DIR}/" "s3://${TEMPLATES_BUCKET}/${PROJECT}/" \
  --exclude "master.yaml" \
  --region "${REGION}"

TEMPLATES_URL="https://s3.amazonaws.com/${TEMPLATES_BUCKET}/${PROJECT}"

deploy_stack() {
  local stack_name=$1
  local template=$2
  shift 2
  local params=("$@")

  echo ""
  echo "Deploying stack: ${stack_name}..."
  aws cloudformation deploy \
    --stack-name "${stack_name}" \
    --template-file "${INFRA_DIR}/${template}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}" \
    ${params:+--parameter-overrides "${params[@]}"}
  echo "  ✓ ${stack_name}"
}

deploy_stack "${PROJECT}-vpc"        "00-vpc.yaml"
deploy_stack "${PROJECT}-ecr"        "01-ecr.yaml"
deploy_stack "${PROJECT}-dynamodb"   "02-dynamodb.yaml"
deploy_stack "${PROJECT}-iam"        "03-iam.yaml"

# After ECR is created, build and push initial image
echo ""
echo "Building and pushing initial Docker image..."
bash "$(dirname "$0")/deploy.sh" --no-ecs-update

deploy_stack "${PROJECT}-ecs"        "04-ecs.yaml" \
  "ImageUri=$(aws ecr describe-repositories --repository-names ${PROJECT} --region ${REGION} --query 'repositories[0].repositoryUri' --output text):latest"

deploy_stack "${PROJECT}-cloudwatch" "05-cloudwatch.yaml"
deploy_stack "${PROJECT}-lambda"     "06-lambda.yaml"

echo ""
echo "All stacks deployed successfully!"
echo ""
echo "Next steps:"
echo "  1. Note the ECS service is running — check CloudWatch Logs: /ecs/byte"
echo "  2. Verify Byte comes online in your Discord server"
echo "  3. Run /help in Discord to verify slash commands are registered"
