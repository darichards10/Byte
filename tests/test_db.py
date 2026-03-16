"""Tests for bot/db.py using moto-mocked DynamoDB."""

import os
import pytest
from moto import mock_aws
import boto3

# Patch config before importing db
os.environ["DYNAMODB_TABLE"] = "ByteBot-Test"
os.environ["ENVIRONMENT"] = "local"
os.environ["AWS_REGION"] = "us-east-1"

from tests.conftest import TABLE_NAME, create_test_table


@pytest.fixture(autouse=True)
def mock_dynamo(aws_credentials):
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        create_test_table(resource)
        # Patch the db module to use the mocked table
        import bot.db as db_module
        db_module._TABLE_NAME = TABLE_NAME
        yield


class TestUserProfile:
    def test_get_or_create_creates_new_profile(self):
        from bot import db
        profile = db.get_or_create_profile("user1", "TestUser")
        assert profile["PK"] == "USER#user1"
        assert profile["discord_username"] == "TestUser"
        assert profile["preferred_diet"] == "standard"
        assert profile["allergies"] == []

    def test_get_or_create_returns_existing(self):
        from bot import db
        db.get_or_create_profile("user1", "TestUser")
        db.put_user_profile("user1", preferred_diet="keto")
        profile = db.get_or_create_profile("user1", "TestUser")
        assert profile["preferred_diet"] == "keto"

    def test_put_user_profile_merges(self):
        from bot import db
        db.get_or_create_profile("user2", "User2")
        db.put_user_profile("user2", allergies=["peanuts", "shellfish"])
        db.put_user_profile("user2", preferred_diet="vegan")
        profile = db.get_user_profile("user2")
        assert profile["allergies"] == ["peanuts", "shellfish"]
        assert profile["preferred_diet"] == "vegan"


class TestConversationHistory:
    def test_save_and_retrieve_conversation(self):
        from bot import db
        db.save_conversation_turn(
            user_id="user1",
            channel_id="chan1",
            user_message="What's a good keto breakfast?",
            bot_response="Here's a keto avocado egg bowl...",
        )
        history = db.get_conversation_history("user1", "chan1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "What's a good keto breakfast?"
        assert history[1]["role"] == "assistant"

    def test_history_isolated_by_channel(self):
        from bot import db
        db.save_conversation_turn("user1", "chan1", "msg1", "resp1")
        db.save_conversation_turn("user1", "chan2", "msg2", "resp2")
        history_chan1 = db.get_conversation_history("user1", "chan1")
        history_chan2 = db.get_conversation_history("user1", "chan2")
        assert len(history_chan1) == 2
        assert len(history_chan2) == 2
        assert history_chan1[0]["content"] == "msg1"
        assert history_chan2[0]["content"] == "msg2"


class TestRecipes:
    def test_save_and_retrieve_recipe(self):
        from bot import db
        recipe_id = db.save_recipe(
            user_id="user1",
            name="Keto Egg Bowl",
            ingredients=["eggs", "avocado", "spinach"],
            instructions=["Fry eggs", "Slice avocado", "Combine"],
            diet_tags=["keto"],
            calories=350,
        )
        assert recipe_id is not None
        recipes = db.get_recipes("user1")
        assert len(recipes) == 1
        assert recipes[0]["name"] == "Keto Egg Bowl"

    def test_delete_recipe(self):
        from bot import db
        recipe_id = db.save_recipe(
            user_id="user1",
            name="Test Recipe",
            ingredients=[],
            instructions=[],
            diet_tags=["standard"],
        )
        db.delete_recipe("user1", recipe_id)
        recipes = db.get_recipes("user1")
        assert len(recipes) == 0


class TestWorkouts:
    def test_log_and_retrieve_workout(self):
        from bot import db
        db.log_workout(
            user_id="user1",
            workout_type="strength",
            duration_min=45,
            exercises=["squat", "bench press", "deadlift"],
            notes="Felt strong",
            calories_burned=300,
        )
        workouts = db.get_workouts("user1")
        assert len(workouts) == 1
        assert workouts[0]["workout_type"] == "strength"
        assert workouts[0]["duration_min"] == 45
        assert "squat" in workouts[0]["exercises"]

    def test_workout_filter_by_type(self):
        from bot import db
        db.log_workout("user1", "strength", 45)
        db.log_workout("user1", "cardio", 30)
        strength_workouts = db.get_workouts("user1", workout_type="strength")
        assert all(w["workout_type"] == "strength" for w in strength_workouts)

    def test_get_workouts_respects_limit(self):
        from bot import db
        for i in range(5):
            db.log_workout("user1", "cardio", 30 + i)
        limited = db.get_workouts("user1", limit=3)
        assert len(limited) <= 3

    def test_log_workout_without_optional_fields(self):
        from bot import db
        ts = db.log_workout("user1", "yoga", 60)
        assert ts is not None
        workouts = db.get_workouts("user1")
        assert workouts[0]["exercises"] == []
        assert workouts[0]["notes"] == ""
        assert "calories_burned" not in workouts[0]

    def test_log_workout_with_calories_burned(self):
        from bot import db
        db.log_workout("user1", "HIIT", 20, calories_burned=400)
        workouts = db.get_workouts("user1")
        assert workouts[0]["calories_burned"] == 400

    def test_workouts_isolated_per_user(self):
        from bot import db
        db.log_workout("user1", "strength", 45)
        db.log_workout("user2", "cardio", 30)
        user1_workouts = db.get_workouts("user1")
        assert all(w["workout_type"] == "strength" for w in user1_workouts)
        user2_workouts = db.get_workouts("user2")
        assert all(w["workout_type"] == "cardio" for w in user2_workouts)


class TestRecipesExtended:

    def test_get_recipes_with_diet_filter(self):
        from bot import db
        db.save_recipe("user1", "Keto Eggs", [], [], diet_tags=["keto"])
        db.save_recipe("user1", "Vegan Bowl", [], [], diet_tags=["vegan"])
        keto_recipes = db.get_recipes("user1", diet_filter="keto")
        assert len(keto_recipes) == 1
        assert keto_recipes[0]["name"] == "Keto Eggs"

    def test_save_recipe_without_diet_tags(self):
        from bot import db
        recipe_id = db.save_recipe("user1", "Plain Oats", ["oats", "water"], ["boil"], diet_tags=[])
        recipes = db.get_recipes("user1")
        assert len(recipes) == 1
        assert recipes[0]["recipe_id"] == recipe_id

    def test_save_recipe_stores_calories_and_servings(self):
        from bot import db
        db.save_recipe("user1", "Protein Shake", ["whey", "milk"], [], diet_tags=[], calories=300, servings=1)
        recipes = db.get_recipes("user1")
        assert recipes[0]["calories"] == 300
        assert recipes[0]["servings"] == 1

    def test_save_recipe_without_calories_has_no_calories_key(self):
        from bot import db
        db.save_recipe("user1", "Mystery Meal", [], [], diet_tags=[])
        recipes = db.get_recipes("user1")
        assert "calories" not in recipes[0]

    def test_delete_nonexistent_recipe_does_not_raise(self):
        from bot import db
        # Deleting an item that does not exist should be a no-op, not an exception
        db.delete_recipe("user1", "nonexistent-id")

    def test_multiple_users_recipes_isolated(self):
        from bot import db
        db.save_recipe("user1", "User1 Recipe", [], [], diet_tags=[])
        db.save_recipe("user2", "User2 Recipe", [], [], diet_tags=[])
        assert len(db.get_recipes("user1")) == 1
        assert len(db.get_recipes("user2")) == 1


class TestReminders:

    def test_save_and_retrieve_reminder(self):
        from bot import db
        reminder_id = db.save_reminder(
            user_id="user1",
            message="Time to drink water!",
            channel_id="chan1",
            schedule="daily",
        )
        assert reminder_id is not None
        reminders = db.get_reminders("user1")
        assert len(reminders) == 1
        assert reminders[0]["message"] == "Time to drink water!"
        assert reminders[0]["schedule"] == "daily"
        assert reminders[0]["enabled"] is True

    def test_delete_reminder(self):
        from bot import db
        reminder_id = db.save_reminder("user1", "Workout time!", "chan1", "daily")
        db.delete_reminder("user1", reminder_id)
        reminders = db.get_reminders("user1")
        assert len(reminders) == 0

    def test_delete_nonexistent_reminder_does_not_raise(self):
        from bot import db
        db.delete_reminder("user1", "ghost-id")  # should not raise

    def test_multiple_reminders_per_user(self):
        from bot import db
        db.save_reminder("user1", "Morning run", "chan1", "daily")
        db.save_reminder("user1", "Evening stretch", "chan1", "daily")
        reminders = db.get_reminders("user1")
        assert len(reminders) == 2

    def test_reminders_isolated_per_user(self):
        from bot import db
        db.save_reminder("user1", "User1 reminder", "chan1", "daily")
        db.save_reminder("user2", "User2 reminder", "chan2", "weekly")
        assert len(db.get_reminders("user1")) == 1
        assert len(db.get_reminders("user2")) == 1

    def test_get_all_active_reminders_returns_enabled(self):
        from bot import db
        db.save_reminder("user1", "Active reminder", "chan1", "daily")
        all_reminders = db.get_all_active_reminders()
        assert any(r["message"] == "Active reminder" for r in all_reminders)

    def test_get_all_active_reminders_excludes_disabled(self):
        from bot import db
        import boto3
        # Save a reminder then manually disable it
        reminder_id = db.save_reminder("user1", "Disabled reminder", "chan1", "daily")
        # Directly update the item to set enabled=False
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.Table("ByteBot-Test")
        table.update_item(
            Key={"PK": "USER#user1", "SK": f"REMINDER#{reminder_id}"},
            UpdateExpression="SET enabled = :val",
            ExpressionAttributeValues={":val": False},
        )
        all_reminders = db.get_all_active_reminders()
        assert not any(r["message"] == "Disabled reminder" for r in all_reminders)


class TestGuildConfig:

    def test_get_guild_config_returns_none_when_not_set(self):
        from bot import db
        result = db.get_guild_config("guild999")
        assert result is None

    def test_set_and_get_guild_chat_channel(self):
        from bot import db
        db.set_guild_chat_channel("guild1", "channel123", "bot-chat")
        config = db.get_guild_config("guild1")
        assert config is not None
        assert config["bot_chat_channel_id"] == "channel123"
        assert config["bot_chat_channel_name"] == "bot-chat"

    def test_set_guild_chat_channel_overwrites_previous(self):
        from bot import db
        db.set_guild_chat_channel("guild1", "old-chan", "old-chat")
        db.set_guild_chat_channel("guild1", "new-chan", "new-chat")
        config = db.get_guild_config("guild1")
        assert config["bot_chat_channel_id"] == "new-chan"
        assert config["bot_chat_channel_name"] == "new-chat"

    def test_guild_configs_isolated_per_guild(self):
        from bot import db
        db.set_guild_chat_channel("guild1", "chan1", "chat1")
        db.set_guild_chat_channel("guild2", "chan2", "chat2")
        config1 = db.get_guild_config("guild1")
        config2 = db.get_guild_config("guild2")
        assert config1["bot_chat_channel_id"] == "chan1"
        assert config2["bot_chat_channel_id"] == "chan2"
