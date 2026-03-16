"""
Byte Bot — Lambda reminder dispatcher.

Triggered by AWS EventBridge on a schedule (e.g. every Sunday 6 PM UTC).
Reads all active reminders from DynamoDB and POSTs messages to Discord
via a bot webhook URL.

Environment variables:
  DYNAMODB_TABLE   — DynamoDB table name
  SSM_PREFIX       — SSM prefix for secrets (e.g. /byte/prod)
  AWS_REGION_NAME  — AWS region
"""

import json
import logging
import os

import boto3
import urllib.request
import urllib.error

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
SSM_PREFIX = os.environ.get("SSM_PREFIX", "/byte/prod")
AWS_REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")

_webhook_url = None  # cached after first SSM fetch


def _get_webhook_url() -> str:
    global _webhook_url
    if _webhook_url:
        return _webhook_url
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    resp = ssm.get_parameter(Name=f"{SSM_PREFIX}/discord_webhook_url", WithDecryption=True)
    _webhook_url = resp["Parameter"]["Value"]
    return _webhook_url


def _get_table():
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return dynamodb.Table(TABLE_NAME)


def _get_active_reminders() -> list[dict]:
    """Scan for all enabled reminders across all users."""
    table = _get_table()
    resp = table.scan(
        FilterExpression="begins_with(SK, :prefix) AND #en = :true",
        ExpressionAttributeNames={"#en": "enabled"},
        ExpressionAttributeValues={":prefix": "REMINDER#", ":true": True},
    )
    return resp.get("Items", [])


def _post_to_discord(channel_id: str, message: str, webhook_url: str) -> bool:
    """Send a message to a specific Discord channel via webhook."""
    # Use the webhook to send a message with the channel ID embedded
    payload = json.dumps({
        "content": message,
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 204)
    except urllib.error.HTTPError as e:
        logger.error(f"Discord webhook error {e.code}: {e.read()}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error posting to Discord: {e}")
        return False


def _handle_weekly_meal_plan(reminder: dict, webhook_url: str) -> None:
    """Send a weekly meal plan nudge."""
    message = (
        f"Hey! It's time to plan your week. "
        f"Use `/meal_plan` to generate this week's meal plan, "
        f"then `/grocery_list` to get your shopping list ready!"
    )
    channel_id = reminder.get("channel_id", "")
    _post_to_discord(channel_id, message, webhook_url)


def lambda_handler(event: dict, context) -> dict:
    logger.info(f"Reminder dispatcher triggered: {json.dumps(event)}")

    reminder_type = event.get("reminder_type", "custom")
    webhook_url = _get_webhook_url()

    if reminder_type == "weekly_meal_plan":
        # Find all users with weekly_meal_plan schedule reminders
        reminders = _get_active_reminders()
        weekly = [r for r in reminders if "weekly" in r.get("schedule", "").lower()
                  or r.get("schedule") == "weekly_meal_plan"]

        if not weekly:
            logger.info("No active weekly meal plan reminders found")
        else:
            for reminder in weekly:
                _handle_weekly_meal_plan(reminder, webhook_url)
                logger.info(f"Sent weekly reminder to user={reminder.get('PK')} channel={reminder.get('channel_id')}")
    else:
        # Generic: send all active reminders that match this trigger
        reminders = _get_active_reminders()
        sent = 0
        for reminder in reminders:
            if reminder.get("schedule", "").lower() == reminder_type.lower():
                channel_id = reminder.get("channel_id", "")
                message = reminder.get("message", "")
                if channel_id and message:
                    success = _post_to_discord(channel_id, message, webhook_url)
                    if success:
                        sent += 1
        logger.info(f"Sent {sent} custom reminders for type={reminder_type}")

    return {"statusCode": 200, "body": "Reminders dispatched"}
