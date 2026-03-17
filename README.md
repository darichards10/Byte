# Byte

A health and fitness Discord bot powered by Claude (Anthropic), running on AWS ECS Fargate with DynamoDB for persistence and a Lambda reminder dispatcher.

## Architecture

```
Discord ──► ECS Fargate (bot) ──► DynamoDB
                │
                └──► SSM Parameter Store (secrets)

EventBridge (cron) ──► Lambda (reminder dispatcher) ──► DynamoDB
```

## Setup

There are four areas to configure before deploying: **Discord**, **Anthropic**, **AWS**, and **GitHub Actions**.

---

## 1. Discord

### Create the bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Give it a name (e.g. `Byte`) and click **Create**.
3. In the left sidebar go to **Bot**.
4. Click **Reset Token**, confirm, and copy the token — this becomes `DISCORD_TOKEN`.
5. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
6. Click **Save Changes**.

### Invite the bot to your server

1. In the left sidebar go to **OAuth2 → URL Generator**.
2. Under **Scopes** select `bot` and `applications.commands`.
3. Under **Bot Permissions** select at minimum:
   - Send Messages
   - Read Message History
   - Use Slash Commands
4. Copy the generated URL, open it in a browser, and add the bot to your server.

### Create the bot channel

Create a text channel named **`byte-chat`** in your server. This is the channel the bot posts in by default (set via `BOT_CHAT_CHANNEL` in the ECS task).

---

## 2. Anthropic

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in.
2. Navigate to **API Keys** and click **Create Key**.
3. Copy the key — this becomes `ANTHROPIC_API_KEY`.

---

## 3. AWS

### Prerequisites

- AWS account with admin access (or a role with permissions for ECR, ECS, DynamoDB, Lambda, IAM, SSM, CloudFormation, S3, CloudWatch, SNS, EventBridge, VPC).
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and configured (`aws configure`).

### Step 1 — Store secrets in SSM Parameter Store

Run this once before deploying any CloudFormation stacks:

```bash
export DISCORD_TOKEN="your-discord-bot-token"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export DISCORD_WEBHOOK_URL="your-discord-webhook-url"   # optional: for outbound webhook notifications

bash scripts/ssm_put_secrets.sh
```

This writes the following **SecureString** parameters to SSM (all under `/byte/prod/`):

| SSM Path | Description |
|----------|-------------|
| `/byte/prod/discord_token` | Discord bot token |
| `/byte/prod/anthropic_api_key` | Anthropic API key |
| `/byte/prod/discord_webhook_url` | Discord webhook URL (optional) |

### Step 2 — Create an S3 bucket for CloudFormation templates

```bash
aws s3 mb s3://your-cfn-templates-bucket --region us-east-1
```

Note the bucket name — you'll need it as the `CFN_TEMPLATE_BUCKET` GitHub secret.

### Step 3 — Configure GitHub OIDC in IAM

This lets GitHub Actions authenticate to AWS without storing long-lived access keys.

**Add the identity provider:**

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

**Create the deployment IAM role.** Save the following as `github-actions-trust.json`, replacing `YOUR_GITHUB_ORG` and `YOUR_REPO_NAME`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_ORG/YOUR_REPO_NAME:*"
        },
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

```bash
aws iam create-role \
  --role-name github-actions-byte-bot \
  --assume-role-policy-document file://github-actions-trust.json

# Attach the permissions the deploy workflows need
aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/AmazonECS_FullAccess

aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/AWSCloudFormationFullAccess

aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess

aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess

aws iam attach-role-policy \
  --role-name github-actions-byte-bot \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

Copy the role ARN (`arn:aws:iam::YOUR_ACCOUNT_ID:role/github-actions-byte-bot`) — this becomes `AWS_DEPLOY_ROLE_ARN`.

### Step 4 — Deploy infrastructure (first time only)

```bash
export TEMPLATES_BUCKET=your-cfn-templates-bucket
bash scripts/create_stacks.sh
```

This deploys all CloudFormation stacks in order: VPC → ECR → DynamoDB → IAM → ECS → CloudWatch → Lambda, and builds/pushes the initial Docker image to ECR.

---

## 4. GitHub Actions

All configuration lives in **Settings → Secrets and variables → Actions** on your repository.

### Secrets

Secrets are encrypted and never shown in logs. Add these under the **Secrets** tab:

| Secret | Description | Example |
|--------|-------------|---------|
| `AWS_DEPLOY_ROLE_ARN` | ARN of the GitHub Actions IAM role created in Step 3 | `arn:aws:iam::123456789012:role/github-actions-byte-bot` |
| `CFN_TEMPLATE_BUCKET` | S3 bucket name for CloudFormation templates (Step 2) | `my-cfn-templates-bucket` |

### Variables

Variables are non-sensitive configuration visible in workflow logs. Add these under the **Variables** tab:

| Variable | Description | Value |
|----------|-------------|-------|
| `AWS_REGION` | AWS region for all resources | `us-east-1` |
| `ECR_REPOSITORY` | ECR repository name (must match `01-ecr.yaml`) | `byte-bot` |
| `ECS_CLUSTER` | ECS cluster name (must match `04-ecs.yaml`) | `byte-cluster` |
| `ECS_SERVICE` | ECS service name (must match `04-ecs.yaml`) | `byte-bot-service` |
| `CONTAINER_NAME` | Container name in the task definition | `byte-bot` |
| `STACK_PREFIX` | Prefix for all CloudFormation stack names | `byte-bot` |
| `LAMBDA_FUNCTION_NAME` | Lambda function name (must match `06-lambda.yaml`) | `byte-bot-reminder-dispatcher` |
| `ALERT_EMAIL` | Email for CloudWatch crash/error alerts (optional — leave blank to disable) | `you@example.com` |

---

## Deploying

### Infrastructure changes (`infra/`)

Merging a PR that touches `infra/` triggers `deploy-infra.yml`, which lints, validates, and deploys the changed CloudFormation stacks. You can also trigger it manually from the **Actions** tab with an optional specific stack target.

### Bot code changes (`bot/`, `Dockerfile`, `requirements.txt`)

Merging a PR that touches these paths triggers `deploy-bot.yml`, which runs tests, builds and pushes a new Docker image to ECR (tagged with the short commit SHA), then forces a new ECS deployment.

### Lambda changes (`lambda/`)

Merging a PR that touches `lambda/` triggers `deploy-lambda.yml`, which packages the code into a ZIP and deploys it to the Lambda function.

### Manual deploys

All three deploy workflows support `workflow_dispatch` from the **Actions** tab if you need to deploy without a PR merge.

---

## Local development

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ --tb=short --cov=bot --cov-report=term-missing -v
```

Environment variables needed for local testing are provided as dummy values by the test suite via `moto` (AWS mock) — no real AWS credentials needed for tests.
