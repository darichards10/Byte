"""
Tests for on_message mention handling logic.

Covers the three trigger conditions:
  1. @mention in any channel
  2. Direct message (DM)
  3. Designated bot-chat channel
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot(bot_id: int = 999) -> MagicMock:
    bot = MagicMock(spec=discord.ext.commands.Bot)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = bot_id
    return bot


def _make_message(
    *,
    bot_user,
    content: str = "hello",
    is_dm: bool = False,
    mentions_bot: bool = False,
    author_is_bot: bool = False,
    channel_name: str = "general",
) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.content = content

    # Author
    author = MagicMock(spec=discord.Member)
    author.bot = author_is_bot
    author.id = 42
    author.display_name = "testuser"
    message.author = author

    # Channel
    if is_dm:
        channel = MagicMock(spec=discord.DMChannel)
        channel.id = 1001
        del channel.guild  # DMs have no guild attribute
    else:
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 2001
        channel.name = channel_name
        channel.guild = MagicMock()
        channel.guild.id = 5000

    message.channel = channel

    # Mentions
    message.mentions = [bot_user] if mentions_bot else []

    return message


# ---------------------------------------------------------------------------
# Tests: guard conditions
# ---------------------------------------------------------------------------

class TestMessageHandlerGuards:

    def setup_method(self):
        from bot.events.message_handler import MessageHandler
        self.bot = _make_bot()
        self.handler = MessageHandler(self.bot)

    @pytest.mark.asyncio
    async def test_ignores_own_messages(self):
        msg = _make_message(bot_user=self.bot.user)
        msg.author = self.bot.user  # message from the bot itself
        # Should return early — claude should never be called
        with patch("bot.events.message_handler.claude") as mock_claude:
            await self.handler.on_message(msg)
            mock_claude.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_other_bots(self):
        msg = _make_message(bot_user=self.bot.user, author_is_bot=True)
        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config", return_value=False):
            with patch("bot.events.message_handler.claude") as mock_claude:
                await self.handler.on_message(msg)
                mock_claude.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_mention_non_designated(self):
        msg = _make_message(bot_user=self.bot.user, mentions_bot=False)
        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config", return_value=False) as mock_guard:
            with patch("bot.events.message_handler.claude") as mock_claude:
                await self.handler.on_message(msg)
                mock_guard.assert_called_once()
                mock_claude.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_mention_skips_db_channel_check(self):
        """When bot is @mentioned, DynamoDB channel check must NOT be called."""
        msg = _make_message(bot_user=self.bot.user, mentions_bot=True, content="hi")
        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config") as mock_guard:
            with patch("bot.events.message_handler.db") as mock_db:
                with patch("bot.events.message_handler.claude") as mock_claude:
                    mock_db.get_or_create_profile.return_value = {}
                    mock_db.get_conversation_history.return_value = []
                    mock_claude.chat = AsyncMock(return_value="response")
                    mock_db.save_conversation_turn.return_value = None
                    msg.channel.typing = MagicMock(
                        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
                    )
                    msg.reply = AsyncMock()
                    with patch("bot.events.message_handler.send_chunked", new_callable=AsyncMock):
                        await self.handler.on_message(msg)
                    mock_guard.assert_not_called()

    @pytest.mark.asyncio
    async def test_dm_skips_db_channel_check(self):
        """In a DM, DynamoDB channel check must NOT be called."""
        msg = _make_message(bot_user=self.bot.user, is_dm=True, content="hi")
        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config") as mock_guard:
            with patch("bot.events.message_handler.db") as mock_db:
                with patch("bot.events.message_handler.claude") as mock_claude:
                    mock_db.get_or_create_profile.return_value = {}
                    mock_db.get_conversation_history.return_value = []
                    mock_claude.chat = AsyncMock(return_value="response")
                    mock_db.save_conversation_turn.return_value = None
                    msg.channel.typing = MagicMock(
                        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
                    )
                    msg.reply = AsyncMock()
                    with patch("bot.events.message_handler.send_chunked", new_callable=AsyncMock):
                        await self.handler.on_message(msg)
                    mock_guard.assert_not_called()

    @pytest.mark.asyncio
    async def test_designated_channel_hits_db(self):
        """Non-mention messages in a designated channel do reach the DB check."""
        msg = _make_message(bot_user=self.bot.user, mentions_bot=False, channel_name="byte-chat")
        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config", return_value=True) as mock_guard:
            with patch("bot.events.message_handler.db") as mock_db:
                with patch("bot.events.message_handler.claude") as mock_claude:
                    mock_db.get_or_create_profile.return_value = {}
                    mock_db.get_conversation_history.return_value = []
                    mock_claude.chat = AsyncMock(return_value="response")
                    mock_db.save_conversation_turn.return_value = None
                    msg.channel.typing = MagicMock(
                        return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
                    )
                    msg.reply = AsyncMock()
                    with patch("bot.events.message_handler.send_chunked", new_callable=AsyncMock):
                        await self.handler.on_message(msg)
                    mock_guard.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: mention content stripping
# ---------------------------------------------------------------------------

class TestMentionContentStripping:

    def setup_method(self):
        from bot.events.message_handler import MessageHandler
        self.bot = _make_bot(bot_id=999)
        self.handler = MessageHandler(self.bot)

    @pytest.mark.asyncio
    async def test_strips_mention_prefix(self):
        msg = _make_message(
            bot_user=self.bot.user,
            mentions_bot=True,
            content=f"<@999> what should I eat today?",
        )
        captured = {}

        async def fake_chat(user_message, history, profile):
            captured["user_message"] = user_message
            return "eat veggies"

        with patch("bot.events.message_handler.db") as mock_db:
            with patch("bot.events.message_handler.claude") as mock_claude:
                mock_db.get_or_create_profile.return_value = {}
                mock_db.get_conversation_history.return_value = []
                mock_claude.chat = fake_chat
                mock_db.save_conversation_turn.return_value = None
                msg.channel.typing = MagicMock(
                    return_value=MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
                )
                msg.reply = AsyncMock()
                with patch("bot.events.message_handler.send_chunked", new_callable=AsyncMock):
                    await self.handler.on_message(msg)

        assert captured.get("user_message") == "what should I eat today?"

    @pytest.mark.asyncio
    async def test_empty_mention_shows_help(self):
        msg = _make_message(
            bot_user=self.bot.user,
            mentions_bot=True,
            content="<@999>",
        )
        msg.reply = AsyncMock()

        with patch("bot.events.message_handler.is_bot_chat_channel_by_guild_config", return_value=False):
            await self.handler.on_message(msg)

        msg.reply.assert_awaited_once()
        assert "Ask me anything" in msg.reply.call_args[0][0]
