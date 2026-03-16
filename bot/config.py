import os
import logging
import boto3
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Config:
    discord_token: str
    anthropic_api_key: str
    dynamodb_table_name: str
    aws_region: str
    bot_chat_channel: str
    environment: str
    dynamodb_endpoint: str | None  # only set in local dev


def _get_ssm(client, name: str) -> str:
    resp = client.get_parameter(Name=name, WithDecryption=True)
    return resp["Parameter"]["Value"]


def load_config() -> Config:
    env = os.getenv("ENVIRONMENT", "local")
    region = os.getenv("AWS_REGION", "us-east-1")

    if env == "local":
        token = os.environ.get("DISCORD_TOKEN", "")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not token or not api_key:
            logger.warning(
                "DISCORD_TOKEN or ANTHROPIC_API_KEY not set — "
                "copy .env.example to .env and fill in values"
            )
        return Config(
            discord_token=token,
            anthropic_api_key=api_key,
            dynamodb_table_name=os.getenv("DYNAMODB_TABLE", "ByteBot"),
            aws_region=region,
            bot_chat_channel=os.getenv("BOT_CHAT_CHANNEL", "byte-chat"),
            environment="local",
            dynamodb_endpoint=os.getenv("DYNAMODB_ENDPOINT"),
        )

    # Production: pull secrets from SSM Parameter Store
    ssm_prefix = os.getenv("SSM_PREFIX", "/byte/prod")
    ssm = boto3.client("ssm", region_name=region)
    return Config(
        discord_token=_get_ssm(ssm, f"{ssm_prefix}/discord_token"),
        anthropic_api_key=_get_ssm(ssm, f"{ssm_prefix}/anthropic_api_key"),
        dynamodb_table_name=os.getenv("DYNAMODB_TABLE", "ByteBot"),
        aws_region=region,
        bot_chat_channel=os.getenv("BOT_CHAT_CHANNEL", "byte-chat"),
        environment="production",
        dynamodb_endpoint=None,
    )


# Module-level singleton loaded once at import time
config = load_config()
