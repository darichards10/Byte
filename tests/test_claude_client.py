"""Tests for bot/claude_client.py — mocks the Anthropic SDK."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_anthropic():
    with patch("bot.claude_client.AsyncAnthropic") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        # Set up mock response
        mock_content = MagicMock()
        mock_content.text = "Here is a keto avocado egg bowl recipe..."

        mock_response = MagicMock()
        mock_response.content = [mock_content]

        mock_instance.messages.create = AsyncMock(return_value=mock_response)
        yield mock_instance


@pytest.mark.asyncio
async def test_chat_calls_claude(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.chat(
        user_message="What's a good keto breakfast?",
        history=[],
        profile={"preferred_diet": "keto", "allergies": ["peanuts"]},
    )
    assert "keto" in result.lower() or len(result) > 0
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_chat_includes_allergy_in_system_prompt(mock_anthropic):
    from bot.claude_client import ClaudeClient, _build_system_prompt
    profile = {"allergies": ["shellfish", "tree nuts"], "preferred_diet": "standard"}
    prompt = _build_system_prompt(profile)
    assert "shellfish" in prompt
    assert "tree nuts" in prompt
    assert "CRITICAL" in prompt  # allergy warning


@pytest.mark.asyncio
async def test_generate_recipe(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.generate_recipe(diet="vegan", cuisine="Mexican")
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()
    call_kwargs = mock_anthropic.messages.create.call_args.kwargs
    assert "vegan" in str(call_kwargs.get("messages", "")).lower() or \
           "vegan" in str(call_kwargs).lower()


@pytest.mark.asyncio
async def test_history_sliding_window(mock_anthropic):
    from bot.claude_client import ClaudeClient, MAX_HISTORY_MESSAGES
    client = ClaudeClient()

    # Build history larger than window
    large_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(MAX_HISTORY_MESSAGES + 10)
    ]

    await client.chat(user_message="new message", history=large_history)

    call_kwargs = mock_anthropic.messages.create.call_args.kwargs
    messages_sent = call_kwargs["messages"]
    # Should be truncated to MAX_HISTORY_MESSAGES + 1 (the new message)
    assert len(messages_sent) <= MAX_HISTORY_MESSAGES + 1


@pytest.mark.asyncio
async def test_analyze_workout_history_empty(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.analyze_workout_history([])
    # Should return a no-data message without calling Claude
    assert "No workout history" in result
    mock_anthropic.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _build_system_prompt variations
# ---------------------------------------------------------------------------

def test_build_system_prompt_no_profile():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt(None)
    assert "Byte" in prompt
    assert "fitness" in prompt.lower()


def test_build_system_prompt_standard_diet_not_appended():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"preferred_diet": "standard"})
    # 'standard' diet should NOT add a diet line to the user profile section
    assert "Preferred diet: standard" not in prompt


def test_build_system_prompt_non_standard_diet_appended():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"preferred_diet": "keto"})
    assert "keto" in prompt


def test_build_system_prompt_includes_dietary_restrictions():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"dietary_restrictions": ["gluten-free", "dairy-free"]})
    assert "gluten-free" in prompt
    assert "dairy-free" in prompt


def test_build_system_prompt_includes_fitness_goals():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"fitness_goals": "run a 5k"})
    assert "run a 5k" in prompt


def test_build_system_prompt_includes_activity_level():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"activity_level": "very_active"})
    assert "very_active" in prompt


def test_build_system_prompt_empty_profile_returns_base():
    from bot.claude_client import _build_system_prompt, _BASE_SYSTEM_PROMPT
    prompt = _build_system_prompt({})
    assert prompt == _BASE_SYSTEM_PROMPT


def test_build_system_prompt_empty_allergies_list_not_appended():
    from bot.claude_client import _build_system_prompt
    prompt = _build_system_prompt({"allergies": []})
    assert "CRITICAL" not in prompt


def test_build_system_prompt_multiple_allergies_all_present():
    from bot.claude_client import _build_system_prompt
    profile = {"allergies": ["peanuts", "shellfish", "soy"]}
    prompt = _build_system_prompt(profile)
    assert "peanuts" in prompt
    assert "shellfish" in prompt
    assert "soy" in prompt


# ---------------------------------------------------------------------------
# Tests: generate_meal_plan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_meal_plan_calls_claude(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.generate_meal_plan(diet="vegan", days=3)
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_meal_plan_includes_diet_and_days(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_meal_plan(diet="paleo", days=5)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "paleo" in call_str.lower()
    assert "5" in call_str


@pytest.mark.asyncio
async def test_generate_meal_plan_with_calories(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_meal_plan(diet="keto", days=7, calories=1800)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "1800" in call_str


@pytest.mark.asyncio
async def test_generate_meal_plan_no_calories_omits_clause(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_meal_plan(diet="standard", days=3, calories=None)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "calories/day" not in call_str


# ---------------------------------------------------------------------------
# Tests: generate_grocery_list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_grocery_list_calls_claude(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.generate_grocery_list("Day 1: eggs, avocado")
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_grocery_list_includes_meal_plan_text(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_grocery_list("spinach salad, grilled chicken")
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "spinach salad" in call_str


@pytest.mark.asyncio
async def test_generate_grocery_list_multiple_servings_in_prompt(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_grocery_list("Day 1: oats", servings=4)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "4" in call_str


@pytest.mark.asyncio
async def test_generate_grocery_list_single_serving_omits_clause(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_grocery_list("Day 1: oats", servings=1)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "for 1 people" not in call_str


# ---------------------------------------------------------------------------
# Tests: generate_workout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_workout_calls_claude(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.generate_workout(workout_type="strength", duration_min=45)
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_generate_workout_includes_type_and_duration(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_workout(workout_type="HIIT", duration_min=20)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "HIIT" in call_str
    assert "20" in call_str


@pytest.mark.asyncio
async def test_generate_workout_with_equipment(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_workout(workout_type="strength", duration_min=45, equipment="dumbbells")
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "dumbbells" in call_str


@pytest.mark.asyncio
async def test_generate_workout_no_equipment_clause(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    await client.generate_workout(workout_type="yoga", duration_min=30, equipment=None)
    call_str = str(mock_anthropic.messages.create.call_args)
    assert "no equipment" in call_str


# ---------------------------------------------------------------------------
# Tests: analyze_workout_history with data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_workout_history_with_workouts_calls_claude(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    workouts = [
        {"workout_type": "strength", "duration_min": 45, "exercises": ["squat"], "logged_at": "2026-03-01T10:00:00"},
        {"workout_type": "cardio", "duration_min": 30, "exercises": ["running"], "logged_at": "2026-03-02T10:00:00"},
    ]
    result = await client.analyze_workout_history(workouts)
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_workout_history_caps_at_10_workouts(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    # Provide 15 workouts; only the first 10 should appear in the prompt
    workouts = [
        {"workout_type": "cardio", "duration_min": i, "exercises": [], "logged_at": f"2026-03-{i:02d}T10:00:00"}
        for i in range(1, 16)
    ]
    await client.analyze_workout_history(workouts)
    call_str = str(mock_anthropic.messages.create.call_args)
    # workout 15 (the 15th) should NOT be included
    assert "2026-03-15" not in call_str


# ---------------------------------------------------------------------------
# Tests: chat with no profile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_with_no_profile_uses_base_prompt(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.chat(user_message="Hello", history=[], profile=None)
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()
    call_kwargs = mock_anthropic.messages.create.call_args.kwargs
    assert "Byte" in call_kwargs.get("system", "")


@pytest.mark.asyncio
async def test_generate_recipe_without_optional_params(mock_anthropic):
    from bot.claude_client import ClaudeClient
    client = ClaudeClient()
    result = await client.generate_recipe(diet="vegan")
    assert result is not None
    mock_anthropic.messages.create.assert_called_once()
