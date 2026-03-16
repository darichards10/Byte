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
