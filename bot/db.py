"""
All DynamoDB operations for Byte Bot.
Single-table design — every entity type flows through this module.

Table key patterns:
  USER#<user_id>  PROFILE                        → UserProfile
  USER#<user_id>  RECIPE#<uuid>                  → Saved recipe
  USER#<user_id>  WORKOUT#<ISO-ts>               → Workout log entry
  USER#<user_id>  HISTORY#<channel_id>#<ISO-ts>  → Conversation turn (TTL: 7 days)
  USER#<user_id>  REMINDER#<uuid>                → Reminder
  USER#<user_id>  FOOD#<ISO-ts>                  → Food log entry
  GUILD#<guild_id> CONFIG                         → Guild config (bot-chat channel)
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key

from bot.config import config

logger = logging.getLogger(__name__)

_TABLE_NAME = config.dynamodb_table_name
_HISTORY_TTL_DAYS = 7
_HISTORY_LIMIT = 20  # max turns loaded as Claude context


def _get_client():
    kwargs = {"region_name": config.aws_region}
    if config.dynamodb_endpoint:
        kwargs["endpoint_url"] = config.dynamodb_endpoint
    return boto3.client("dynamodb", **kwargs)


def _get_table():
    kwargs = {"region_name": config.aws_region}
    if config.dynamodb_endpoint:
        kwargs["endpoint_url"] = config.dynamodb_endpoint
    dynamodb = boto3.resource("dynamodb", **kwargs)
    return dynamodb.Table(_TABLE_NAME)


def ensure_table() -> None:
    """
    Create the DynamoDB table if it doesn't exist.
    Only runs in local dev (when DYNAMODB_ENDPOINT is set).
    In production the table is managed by CloudFormation (02-dynamodb.yaml).
    """
    if not config.dynamodb_endpoint:
        return  # production — table already exists via CloudFormation

    client = _get_client()
    try:
        client.describe_table(TableName=_TABLE_NAME)
        logger.info(f"DynamoDB table '{_TABLE_NAME}' already exists")
    except client.exceptions.ResourceNotFoundException:
        logger.info(f"Creating local DynamoDB table '{_TABLE_NAME}'...")
        client.create_table(
            TableName=_TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK",     "AttributeType": "S"},
                {"AttributeName": "SK",     "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "gsi1sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        client.get_waiter("table_exists").wait(TableName=_TABLE_NAME)
        logger.info(f"Table '{_TABLE_NAME}' created successfully")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl_from_now(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


# ── User Profile ─────────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> dict | None:
    table = _get_table()
    resp = table.get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE"})
    return resp.get("Item")


def put_user_profile(user_id: str, **fields) -> None:
    """Upsert profile fields. Merges with existing data."""
    table = _get_table()
    existing = get_user_profile(user_id) or {}
    existing.update(fields)
    existing["PK"] = f"USER#{user_id}"
    existing["SK"] = "PROFILE"
    existing["updated_at"] = _now_iso()
    if "created_at" not in existing:
        existing["created_at"] = _now_iso()
    table.put_item(Item=existing)


def get_or_create_profile(user_id: str, discord_username: str = "") -> dict:
    profile = get_user_profile(user_id)
    if profile is None:
        profile = {
            "PK": f"USER#{user_id}",
            "SK": "PROFILE",
            "discord_username": discord_username,
            "dietary_restrictions": [],
            "allergies": [],
            "fitness_goals": "",
            "preferred_diet": "standard",
            "activity_level": "moderately_active",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _get_table().put_item(Item=profile)
    return profile


# ── Conversation History ──────────────────────────────────────────────────────

def get_conversation_history(user_id: str, channel_id: str) -> list[dict]:
    """
    Returns the last HISTORY_LIMIT conversation turns as a list of
    {"role": "user"|"assistant", "content": "..."} dicts — ready to pass to Claude.
    """
    table = _get_table()
    prefix = f"HISTORY#{channel_id}#"
    resp = table.query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with(prefix),
        ScanIndexForward=True,  # ascending timestamp order
        Limit=_HISTORY_LIMIT,
    )
    items = resp.get("Items", [])
    # If more than HISTORY_LIMIT, take the last N
    if len(items) > _HISTORY_LIMIT:
        items = items[-_HISTORY_LIMIT:]
    return [{"role": item["role"], "content": item["content"]} for item in items]


def save_conversation_turn(
    user_id: str,
    channel_id: str,
    user_message: str,
    bot_response: str,
) -> None:
    table = _get_table()
    ts = _now_iso()
    ttl = _ttl_from_now(_HISTORY_TTL_DAYS)
    pk = f"USER#{user_id}"
    prefix = f"HISTORY#{channel_id}#{ts}"

    table.batch_writer()
    with table.batch_writer() as batch:
        batch.put_item(Item={
            "PK": pk,
            "SK": f"{prefix}#user",
            "role": "user",
            "content": user_message,
            "ttl": ttl,
        })
        batch.put_item(Item={
            "PK": pk,
            "SK": f"{prefix}#assistant",
            "role": "assistant",
            "content": bot_response,
            "ttl": ttl,
        })


# ── Recipes ───────────────────────────────────────────────────────────────────

def save_recipe(
    user_id: str,
    name: str,
    ingredients: list[str],
    instructions: list[str],
    diet_tags: list[str],
    calories: int | None = None,
    servings: int | None = None,
) -> str:
    recipe_id = str(uuid.uuid4())[:8]
    table = _get_table()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"RECIPE#{recipe_id}",
        "recipe_id": recipe_id,
        "name": name,
        "ingredients": ingredients,
        "instructions": instructions,
        "diet_tags": diet_tags,
        "saved_at": _now_iso(),
    }
    if calories is not None:
        item["calories"] = calories
    if servings is not None:
        item["servings"] = servings

    # GSI for diet-filtered queries
    if diet_tags:
        item["gsi1pk"] = f"USER#{user_id}"
        item["gsi1sk"] = f"DIET#{diet_tags[0]}#RECIPE#{recipe_id}"

    table.put_item(Item=item)
    return recipe_id


def get_recipes(user_id: str, diet_filter: str | None = None) -> list[dict]:
    table = _get_table()
    if diet_filter:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=(
                Key("gsi1pk").eq(f"USER#{user_id}") &
                Key("gsi1sk").begins_with(f"DIET#{diet_filter}#")
            ),
        )
    else:
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}") &
                Key("SK").begins_with("RECIPE#")
            ),
        )
    return resp.get("Items", [])


def delete_recipe(user_id: str, recipe_id: str) -> None:
    _get_table().delete_item(
        Key={"PK": f"USER#{user_id}", "SK": f"RECIPE#{recipe_id}"}
    )


# ── Workouts ──────────────────────────────────────────────────────────────────

def log_workout(
    user_id: str,
    workout_type: str,
    duration_min: int,
    exercises: list[str] | None = None,
    notes: str = "",
    calories_burned: int | None = None,
) -> str:
    ts = _now_iso()
    table = _get_table()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"WORKOUT#{ts}",
        "workout_type": workout_type,
        "duration_min": duration_min,
        "exercises": exercises or [],
        "notes": notes,
        "logged_at": ts,
        "gsi1pk": f"USER#{user_id}",
        "gsi1sk": f"TYPE#{workout_type}#WORKOUT#{ts}",
    }
    if calories_burned is not None:
        item["calories_burned"] = calories_burned
    table.put_item(Item=item)
    return ts


def get_workouts(user_id: str, limit: int = 10, workout_type: str | None = None) -> list[dict]:
    table = _get_table()
    if workout_type:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=(
                Key("gsi1pk").eq(f"USER#{user_id}") &
                Key("gsi1sk").begins_with(f"TYPE#{workout_type}#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
    else:
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}") &
                Key("SK").begins_with("WORKOUT#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
    return resp.get("Items", [])


# ── Reminders ─────────────────────────────────────────────────────────────────

def save_reminder(
    user_id: str,
    message: str,
    channel_id: str,
    schedule: str,
) -> str:
    reminder_id = str(uuid.uuid4())[:8]
    _get_table().put_item(Item={
        "PK": f"USER#{user_id}",
        "SK": f"REMINDER#{reminder_id}",
        "reminder_id": reminder_id,
        "message": message,
        "channel_id": channel_id,
        "schedule": schedule,
        "enabled": True,
        "created_at": _now_iso(),
    })
    return reminder_id


def get_reminders(user_id: str) -> list[dict]:
    resp = _get_table().query(
        KeyConditionExpression=(
            Key("PK").eq(f"USER#{user_id}") &
            Key("SK").begins_with("REMINDER#")
        )
    )
    return resp.get("Items", [])


def get_all_active_reminders() -> list[dict]:
    """Scan for all enabled reminders across all users (used by Lambda dispatcher)."""
    table = _get_table()
    resp = table.scan(
        FilterExpression=Key("SK").begins_with("REMINDER#"),
    )
    return [item for item in resp.get("Items", []) if item.get("enabled")]


def delete_reminder(user_id: str, reminder_id: str) -> None:
    _get_table().delete_item(
        Key={"PK": f"USER#{user_id}", "SK": f"REMINDER#{reminder_id}"}
    )


# ── Food Log ──────────────────────────────────────────────────────────────────

def log_food_entry(
    user_id: str,
    meal_type: str,
    foods: list[str],
    calories: int | None = None,
    protein_g: int | None = None,
    carbs_g: int | None = None,
    fat_g: int | None = None,
    notes: str = "",
) -> str:
    """
    Log a food/meal entry. Returns the ISO timestamp used as the food_id.
    PK is always USER#{user_id} — cross-user writes are structurally impossible.
    """
    ts = _now_iso()
    table = _get_table()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"FOOD#{ts}",
        "food_id": ts,
        "logged_at": ts,
        "meal_type": meal_type,
        "foods": foods,
        "notes": notes,
        # GSI always set — enables meal-type filtering via GSI1
        "gsi1pk": f"USER#{user_id}",
        "gsi1sk": f"MEAL#{meal_type}#FOOD#{ts}",
    }
    if calories is not None:
        item["calories"] = calories
    if protein_g is not None:
        item["protein_g"] = protein_g
    if carbs_g is not None:
        item["carbs_g"] = carbs_g
    if fat_g is not None:
        item["fat_g"] = fat_g
    table.put_item(Item=item)
    return ts


def get_food_log(
    user_id: str,
    limit: int = 10,
    meal_type: str | None = None,
    date: str | None = None,
) -> list[dict]:
    """
    Retrieve food log entries for a user.
    - meal_type: queries GSI1 to filter by meal type.
    - date: YYYY-MM-DD string; uses begins_with on SK to return only that day.
    - If both provided, meal_type takes precedence (GSI path).
    All paths filter strictly by user_id — no cross-user data is accessible.
    """
    table = _get_table()
    if meal_type:
        resp = table.query(
            IndexName="GSI1",
            KeyConditionExpression=(
                Key("gsi1pk").eq(f"USER#{user_id}") &
                Key("gsi1sk").begins_with(f"MEAL#{meal_type}#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
    elif date:
        # ISO timestamps start with the date, e.g. "2026-03-17T..."
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}") &
                Key("SK").begins_with(f"FOOD#{date}")
            ),
            ScanIndexForward=False,
        )
    else:
        resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(f"USER#{user_id}") &
                Key("SK").begins_with("FOOD#")
            ),
            ScanIndexForward=False,
            Limit=limit,
        )
    return resp.get("Items", [])


def delete_food_entry(user_id: str, food_id: str) -> None:
    """
    Delete a food log entry. Silent no-op if the item does not exist.
    Security: PK is always USER#{user_id}. Even if food_id belongs to another
    user, the delete targets only this user's partition — cross-user deletion
    is structurally impossible.
    """
    _get_table().delete_item(
        Key={"PK": f"USER#{user_id}", "SK": f"FOOD#{food_id}"}
    )


# ── Guild Config ──────────────────────────────────────────────────────────────

def get_guild_config(guild_id: str) -> dict | None:
    resp = _get_table().get_item(Key={"PK": f"GUILD#{guild_id}", "SK": "CONFIG"})
    return resp.get("Item")


def set_guild_chat_channel(guild_id: str, channel_id: str, channel_name: str) -> None:
    _get_table().put_item(Item={
        "PK": f"GUILD#{guild_id}",
        "SK": "CONFIG",
        "bot_chat_channel_id": channel_id,
        "bot_chat_channel_name": channel_name,
        "updated_at": _now_iso(),
    })
