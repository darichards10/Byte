#!/usr/bin/env bash
# One-time setup: store secrets in AWS SSM Parameter Store.
# Run this before deploying CloudFormation stacks.
# Never commit this file with real values — use environment variables instead.
#
# Usage:
#   export DISCORD_TOKEN="your_token"
#   export ANTHROPIC_API_KEY="your_key"
#   export DISCORD_WEBHOOK_URL="your_webhook_url"
#   bash scripts/ssm_put_secrets.sh

set -euo pipefail

REGION=${AWS_REGION:-us-east-1}
PREFIX="/byte/prod"

if [[ -z "${DISCORD_TOKEN:-}" || -z "${ANTHROPIC_API_KEY:-}" || -z "${DISCORD_WEBHOOK_URL:-}" ]]; then
  echo "ERROR: Set these environment variables before running:"
  echo "  export DISCORD_TOKEN=..."
  echo "  export ANTHROPIC_API_KEY=..."
  echo "  export DISCORD_WEBHOOK_URL=..."
  exit 1
fi

echo "Writing secrets to SSM Parameter Store (region: $REGION, prefix: $PREFIX)..."

aws ssm put-parameter \
  --name "${PREFIX}/discord_token" \
  --value "${DISCORD_TOKEN}" \
  --type SecureString \
  --overwrite \
  --region "${REGION}"
echo "  ✓ discord_token"

aws ssm put-parameter \
  --name "${PREFIX}/anthropic_api_key" \
  --value "${ANTHROPIC_API_KEY}" \
  --type SecureString \
  --overwrite \
  --region "${REGION}"
echo "  ✓ anthropic_api_key"

aws ssm put-parameter \
  --name "${PREFIX}/discord_webhook_url" \
  --value "${DISCORD_WEBHOOK_URL}" \
  --type SecureString \
  --overwrite \
  --region "${REGION}"
echo "  ✓ discord_webhook_url"

echo ""
echo "All secrets stored. You can now run: bash scripts/create_stacks.sh"
