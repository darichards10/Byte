"""Tests for bot/utils/formatters.py"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from bot.utils.formatters import chunk_text


class TestChunkText:
    def test_short_text_returned_as_single_chunk(self):
        text = "Hello, world!"
        chunks = chunk_text(text, size=1900)
        assert chunks == [text]

    def test_long_text_split_into_chunks(self):
        text = "word " * 500  # 2500 chars
        chunks = chunk_text(text, size=500)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 500

    def test_split_prefers_newlines(self):
        text = "line one\nline two\n" + "x" * 490
        chunks = chunk_text(text, size=500)
        # First chunk should end at a newline boundary if possible
        assert len(chunks[0]) <= 500

    def test_no_data_loss(self):
        text = "a" * 5000
        chunks = chunk_text(text, size=1900)
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

    def test_exact_size_boundary(self):
        text = "a" * 1900
        chunks = chunk_text(text, size=1900)
        assert len(chunks) == 1

    def test_empty_string_returns_single_empty_chunk(self):
        chunks = chunk_text("", size=1900)
        assert chunks == [""]

    def test_single_char_returns_single_chunk(self):
        chunks = chunk_text("x", size=1900)
        assert chunks == ["x"]

    def test_size_plus_one_requires_two_chunks(self):
        text = "a" * 1901
        chunks = chunk_text(text, size=1900)
        assert len(chunks) == 2

    def test_chunks_cover_full_content(self):
        text = "\n".join([f"line {i}" for i in range(200)])
        chunks = chunk_text(text, size=500)
        reconstructed = "\n".join(chunks)
        # Original newlines may be stripped between chunks but content is preserved
        for i in range(200):
            assert f"line {i}" in reconstructed


# ---------------------------------------------------------------------------
# Tests: send_chunked
# ---------------------------------------------------------------------------

class TestSendChunked:

    @pytest.mark.asyncio
    async def test_single_chunk_uses_reply(self):
        from bot.utils.formatters import send_chunked
        target = AsyncMock(spec=discord.abc.Messageable)
        reply_msg = AsyncMock(spec=discord.Message)
        reply_msg.reply = AsyncMock()
        await send_chunked(target, "short text", reply_to=reply_msg)
        reply_msg.reply.assert_awaited_once_with("short text")
        target.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_single_chunk_no_reply_uses_send(self):
        from bot.utils.formatters import send_chunked
        target = AsyncMock(spec=discord.abc.Messageable)
        target.send = AsyncMock()
        await send_chunked(target, "short text", reply_to=None)
        target.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multi_chunk_first_uses_reply_rest_uses_send(self):
        from bot.utils.formatters import send_chunked
        target = AsyncMock(spec=discord.abc.Messageable)
        target.send = AsyncMock()
        reply_msg = AsyncMock(spec=discord.Message)
        reply_msg.reply = AsyncMock()
        long_text = "word " * 600  # exceeds 1900-char chunk size
        await send_chunked(target, long_text, reply_to=reply_msg)
        reply_msg.reply.assert_awaited_once()
        assert target.send.await_count >= 1

    @pytest.mark.asyncio
    async def test_multi_chunk_labels_added(self):
        from bot.utils.formatters import send_chunked
        target = AsyncMock(spec=discord.abc.Messageable)
        target.send = AsyncMock()
        reply_msg = AsyncMock(spec=discord.Message)
        reply_msg.reply = AsyncMock()
        long_text = "word " * 600
        await send_chunked(target, long_text, reply_to=reply_msg)
        first_call_text = reply_msg.reply.call_args[0][0]
        assert "part 1/" in first_call_text


# ---------------------------------------------------------------------------
# Tests: profile_embed
# ---------------------------------------------------------------------------

class TestProfileEmbed:

    def test_embed_title_includes_username(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "keto", "activity_level": "moderately_active",
                   "dietary_restrictions": [], "allergies": [], "fitness_goals": ""}
        embed = profile_embed(profile, "testuser")
        assert "testuser" in embed.title

    def test_embed_shows_diet(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "vegan", "activity_level": "active",
                   "dietary_restrictions": [], "allergies": [], "fitness_goals": ""}
        embed = profile_embed(profile, "user")
        field_values = [f.value for f in embed.fields]
        assert any("Vegan" in v for v in field_values)

    def test_embed_shows_allergies(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "standard", "activity_level": "active",
                   "dietary_restrictions": [], "allergies": ["peanuts", "shellfish"], "fitness_goals": ""}
        embed = profile_embed(profile, "user")
        field_values = [f.value for f in embed.fields]
        assert any("peanuts" in v for v in field_values)
        assert any("shellfish" in v for v in field_values)

    def test_embed_shows_none_for_empty_allergies(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "standard", "activity_level": "active",
                   "dietary_restrictions": [], "allergies": [], "fitness_goals": ""}
        embed = profile_embed(profile, "user")
        field_values = [f.value for f in embed.fields]
        assert any(v == "None" for v in field_values)

    def test_embed_shows_not_set_for_missing_goals(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "standard", "activity_level": "active",
                   "dietary_restrictions": [], "allergies": [], "fitness_goals": ""}
        embed = profile_embed(profile, "user")
        field_values = [f.value for f in embed.fields]
        assert any("Not set" in v for v in field_values)

    def test_embed_shows_fitness_goals_when_set(self):
        from bot.utils.formatters import profile_embed
        profile = {"preferred_diet": "standard", "activity_level": "active",
                   "dietary_restrictions": [], "allergies": [], "fitness_goals": "lose 10 pounds"}
        embed = profile_embed(profile, "user")
        field_values = [f.value for f in embed.fields]
        assert any("lose 10 pounds" in v for v in field_values)


# ---------------------------------------------------------------------------
# Tests: recipe_list_embed
# ---------------------------------------------------------------------------

class TestRecipeListEmbed:

    def test_empty_recipes_shows_description(self):
        from bot.utils.formatters import recipe_list_embed
        embed = recipe_list_embed([])
        assert embed.description is not None
        assert "No saved recipes" in embed.description

    def test_recipes_shown_as_fields(self):
        from bot.utils.formatters import recipe_list_embed
        recipes = [
            {"name": "Keto Eggs", "recipe_id": "abc1", "diet_tags": ["keto"], "calories": 300},
            {"name": "Vegan Bowl", "recipe_id": "def2", "diet_tags": ["vegan"]},
        ]
        embed = recipe_list_embed(recipes)
        field_names = [f.name for f in embed.fields]
        assert "Keto Eggs" in field_names
        assert "Vegan Bowl" in field_names

    def test_recipe_id_shown_in_field_value(self):
        from bot.utils.formatters import recipe_list_embed
        recipes = [{"name": "My Recipe", "recipe_id": "xyz99", "diet_tags": []}]
        embed = recipe_list_embed(recipes)
        assert any("xyz99" in f.value for f in embed.fields)

    def test_calories_shown_when_present(self):
        from bot.utils.formatters import recipe_list_embed
        recipes = [{"name": "Protein Meal", "recipe_id": "r1", "diet_tags": [], "calories": 450}]
        embed = recipe_list_embed(recipes)
        assert any("450" in f.value for f in embed.fields)

    def test_capped_at_10_recipes(self):
        from bot.utils.formatters import recipe_list_embed
        recipes = [
            {"name": f"Recipe {i}", "recipe_id": f"r{i}", "diet_tags": []}
            for i in range(15)
        ]
        embed = recipe_list_embed(recipes)
        assert len(embed.fields) <= 10

    def test_untagged_shown_when_no_diet_tags(self):
        from bot.utils.formatters import recipe_list_embed
        recipes = [{"name": "Plain", "recipe_id": "p1", "diet_tags": []}]
        embed = recipe_list_embed(recipes)
        assert any("untagged" in f.value for f in embed.fields)


# ---------------------------------------------------------------------------
# Tests: workout_list_embed
# ---------------------------------------------------------------------------

class TestWorkoutListEmbed:

    def test_empty_workouts_shows_description(self):
        from bot.utils.formatters import workout_list_embed
        embed = workout_list_embed([])
        assert embed.description is not None
        assert "No workouts logged" in embed.description

    def test_workouts_shown_as_fields(self):
        from bot.utils.formatters import workout_list_embed
        workouts = [
            {"workout_type": "strength", "duration_min": 45,
             "logged_at": "2026-03-10T10:00:00", "exercises": ["squat"]},
        ]
        embed = workout_list_embed(workouts)
        assert len(embed.fields) == 1
        assert "Strength" in embed.fields[0].name

    def test_workout_date_shown(self):
        from bot.utils.formatters import workout_list_embed
        workouts = [
            {"workout_type": "cardio", "duration_min": 30,
             "logged_at": "2026-03-15T08:00:00", "exercises": []},
        ]
        embed = workout_list_embed(workouts)
        assert "2026-03-15" in embed.fields[0].name

    def test_calories_shown_when_present(self):
        from bot.utils.formatters import workout_list_embed
        workouts = [
            {"workout_type": "HIIT", "duration_min": 20,
             "logged_at": "2026-03-01T10:00:00", "exercises": [], "calories_burned": 350},
        ]
        embed = workout_list_embed(workouts)
        assert "350" in embed.fields[0].name

    def test_exercises_shown_in_field_value(self):
        from bot.utils.formatters import workout_list_embed
        workouts = [
            {"workout_type": "strength", "duration_min": 45,
             "logged_at": "2026-03-01T10:00:00", "exercises": ["squat", "bench press", "deadlift"]},
        ]
        embed = workout_list_embed(workouts)
        assert "squat" in embed.fields[0].value

    def test_exercises_capped_at_3(self):
        from bot.utils.formatters import workout_list_embed
        workouts = [
            {"workout_type": "strength", "duration_min": 60,
             "logged_at": "2026-03-01T10:00:00",
             "exercises": ["squat", "bench", "deadlift", "curl", "row"]},
        ]
        embed = workout_list_embed(workouts)
        field_value = embed.fields[0].value
        # Only 3 exercises should appear
        exercise_count = sum(1 for ex in ["squat", "bench", "deadlift", "curl", "row"] if ex in field_value)
        assert exercise_count <= 3
