"""
Tests for bot/events/reaction_handler.py

Covers:
  1. _parse_recipe_from_message — name extraction and ingredient parsing
  2. ReactionHandler.on_raw_reaction_add — guard conditions and save flow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord


# ---------------------------------------------------------------------------
# Tests: _parse_recipe_from_message
# ---------------------------------------------------------------------------

class TestParseRecipeFromMessage:

    def _parse(self, content: str):
        from bot.events.reaction_handler import _parse_recipe_from_message
        return _parse_recipe_from_message(content)

    def test_extracts_bold_recipe_name(self):
        content = "**Keto Avocado Egg Bowl**\nA delicious recipe."
        result = self._parse(content)
        assert result is not None
        assert result["name"] == "Keto Avocado Egg Bowl"

    def test_extracts_plain_first_line_as_name(self):
        content = "Vegan Lentil Soup\nA hearty soup recipe."
        result = self._parse(content)
        assert result is not None
        assert result["name"] == "Vegan Lentil Soup"

    def test_returns_none_when_no_name_found(self):
        # First lines start with dashes — should fail to extract name
        content = "- item one\n- item two\n- item three"
        result = self._parse(content)
        assert result is None

    def test_returns_none_for_empty_content(self):
        result = self._parse("")
        assert result is None

    def test_returns_none_for_whitespace_only(self):
        result = self._parse("   \n\n  ")
        assert result is None

    def test_extracts_ingredients_after_section_header(self):
        content = (
            "**Chicken Stir Fry**\n"
            "A quick stir fry.\n\n"
            "**Ingredients**\n"
            "- 2 chicken breasts\n"
            "- 1 cup broccoli\n"
            "- 2 tbsp soy sauce\n\n"
            "**Instructions**\n"
            "1. Cook chicken."
        )
        result = self._parse(content)
        assert result is not None
        assert "2 chicken breasts" in result["ingredients"]
        assert "1 cup broccoli" in result["ingredients"]
        assert "2 tbsp soy sauce" in result["ingredients"]

    def test_ingredients_stop_at_non_list_line(self):
        content = (
            "**Salad**\n\n"
            "Ingredients:\n"
            "- lettuce\n"
            "- tomato\n"
            "Instructions:\n"
            "- do stuff\n"
        )
        result = self._parse(content)
        assert result is not None
        # "do stuff" should NOT be in ingredients — it's after the non-list break
        assert "do stuff" not in result["ingredients"]
        assert "lettuce" in result["ingredients"]

    def test_no_ingredients_section_returns_empty_list(self):
        content = "**Quick Recipe**\nJust some text without an ingredients heading."
        result = self._parse(content)
        assert result is not None
        assert result["ingredients"] == []

    def test_result_has_required_keys(self):
        content = "**Test Recipe**\n\nIngredients\n- salt"
        result = self._parse(content)
        assert result is not None
        for key in ("name", "ingredients", "instructions", "diet_tags"):
            assert key in result

    def test_instructions_always_empty_list(self):
        # instructions are not parsed — caller saves full message text instead
        content = "**My Recipe**\nIngredients\n- egg"
        result = self._parse(content)
        assert result["instructions"] == []

    def test_diet_tags_always_empty_list(self):
        content = "**My Recipe**"
        result = self._parse(content)
        assert result["diet_tags"] == []

    def test_ignores_long_first_lines(self):
        # Lines >= 80 chars are skipped as recipe names
        long_line = "x" * 80
        content = f"{long_line}\n**Actual Recipe**"
        result = self._parse(content)
        assert result is not None
        assert result["name"] == "Actual Recipe"

    def test_bold_name_strips_surrounding_whitespace(self):
        content = "**  Spaced Name  **\nSome text"
        result = self._parse(content)
        assert result is not None
        assert result["name"] == "Spaced Name"

    def test_case_insensitive_ingredients_header(self):
        content = "**Recipe**\nINGREDIENTS\n- egg\n- milk"
        result = self._parse(content)
        assert result is not None
        assert "egg" in result["ingredients"]
        assert "milk" in result["ingredients"]


# ---------------------------------------------------------------------------
# Helpers for ReactionHandler tests
# ---------------------------------------------------------------------------

def _make_payload(
    emoji: str = "⭐",
    user_id: int = 42,
    channel_id: int = 100,
    message_id: int = 200,
    bot_id: int = 999,
) -> MagicMock:
    payload = MagicMock(spec=discord.RawReactionActionEvent)
    payload.emoji = MagicMock()
    payload.emoji.__str__ = MagicMock(return_value=emoji)
    payload.user_id = user_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    return payload


def _make_bot(bot_id: int = 999) -> MagicMock:
    from discord.ext import commands
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = bot_id
    return bot


# ---------------------------------------------------------------------------
# Tests: ReactionHandler guard conditions
# ---------------------------------------------------------------------------

class TestReactionHandlerGuards:

    def setup_method(self):
        from bot.events.reaction_handler import ReactionHandler
        self.bot = _make_bot()
        self.handler = ReactionHandler(self.bot)

    @pytest.mark.asyncio
    async def test_ignores_non_star_emoji(self):
        payload = _make_payload(emoji="👍")
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_bots_own_reaction(self):
        payload = _make_payload(user_id=self.bot.user.id)  # bot reacted
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_when_channel_not_found(self):
        payload = _make_payload()
        self.bot.get_channel = MagicMock(return_value=None)
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_when_message_not_found(self):
        payload = _make_payload()
        channel = AsyncMock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))
        self.bot.get_channel = MagicMock(return_value=channel)
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_forbidden_message_fetch(self):
        payload = _make_payload()
        channel = AsyncMock()
        channel.fetch_message = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "forbidden"))
        self.bot.get_channel = MagicMock(return_value=channel)
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_reactions_on_non_bot_messages(self):
        payload = _make_payload()
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock()  # not the bot
        message.content = "**Some Recipe**"
        channel = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=message)
        self.bot.get_channel = MagicMock(return_value=channel)
        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: ReactionHandler happy path and DM fallback
# ---------------------------------------------------------------------------

class TestReactionHandlerSaveFlow:

    def setup_method(self):
        from bot.events.reaction_handler import ReactionHandler
        self.bot = _make_bot()
        self.handler = ReactionHandler(self.bot)

    def _setup_channel_with_message(self, content: str) -> tuple:
        message = MagicMock(spec=discord.Message)
        message.author = self.bot.user
        message.content = content
        message.add_reaction = AsyncMock()
        channel = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=message)
        self.bot.get_channel = MagicMock(return_value=channel)
        return channel, message

    @pytest.mark.asyncio
    async def test_saves_recipe_and_dms_user(self):
        payload = _make_payload()
        _, message = self._setup_channel_with_message(
            "**Avocado Toast**\n\nIngredients\n- avocado\n- bread"
        )
        user = AsyncMock()
        user.send = AsyncMock()
        self.bot.fetch_user = AsyncMock(return_value=user)

        with patch("bot.events.reaction_handler.db") as mock_db:
            mock_db.save_recipe.return_value = "abc12345"
            await self.handler.on_raw_reaction_add(payload)

        mock_db.save_recipe.assert_called_once()
        call_kwargs = mock_db.save_recipe.call_args.kwargs
        assert call_kwargs["name"] == "Avocado Toast"
        assert "avocado" in call_kwargs["ingredients"]
        user.send.assert_awaited_once()
        dm_text = user.send.call_args[0][0]
        assert "Avocado Toast" in dm_text
        assert "abc12345" in dm_text

    @pytest.mark.asyncio
    async def test_unparseable_message_sends_fallback_dm(self):
        payload = _make_payload()
        # Message content starts with dashes — cannot extract name
        _, _ = self._setup_channel_with_message("- item\n- item2")
        user = AsyncMock()
        user.send = AsyncMock()
        self.bot.fetch_user = AsyncMock(return_value=user)

        with patch("bot.events.reaction_handler.db") as mock_db:
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()
            user.send.assert_awaited_once()
            assert "save_recipe" in user.send.call_args[0][0]

    @pytest.mark.asyncio
    async def test_dm_disabled_falls_back_to_checkmark_reaction(self):
        payload = _make_payload()
        _, message = self._setup_channel_with_message("**Quick Salad**")
        user = AsyncMock()
        user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs disabled"))
        self.bot.fetch_user = AsyncMock(return_value=user)

        with patch("bot.events.reaction_handler.db") as mock_db:
            mock_db.save_recipe.return_value = "xyz99"
            await self.handler.on_raw_reaction_add(payload)

        message.add_reaction.assert_awaited_once_with("✅")

    @pytest.mark.asyncio
    async def test_unparseable_dm_forbidden_is_silently_ignored(self):
        payload = _make_payload()
        _, _ = self._setup_channel_with_message("- only list items\n- no title")
        user = AsyncMock()
        user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs disabled"))
        self.bot.fetch_user = AsyncMock(return_value=user)

        with patch("bot.events.reaction_handler.db") as mock_db:
            # Should not raise
            await self.handler.on_raw_reaction_add(payload)
            mock_db.save_recipe.assert_not_called()
