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
