"""
Tests for bot/utils/channel_guard.py

Covers:
  1. is_bot_chat_channel — DM / name-based checks
  2. is_bot_chat_channel_by_guild_config — DB-backed checks with name fallback
"""

import pytest
from unittest.mock import MagicMock, patch
import discord


# ---------------------------------------------------------------------------
# Tests: is_bot_chat_channel
# ---------------------------------------------------------------------------

class TestIsBotChatChannel:

    def _call(self, channel):
        from bot.utils.channel_guard import is_bot_chat_channel
        return is_bot_chat_channel(channel)

    def test_returns_true_for_dm_channel(self):
        channel = MagicMock(spec=discord.DMChannel)
        # DMChannel has no 'guild' attribute
        del channel.guild
        assert self._call(channel) is True

    def test_returns_true_when_guild_is_none(self):
        channel = MagicMock()
        channel.guild = None
        channel.name = "general"
        assert self._call(channel) is True

    def test_returns_true_for_matching_channel_name(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.name = "byte-chat"
        with patch("bot.utils.channel_guard.config") as mock_config:
            mock_config.bot_chat_channel = "byte-chat"
            assert self._call(channel) is True

    def test_returns_false_for_non_matching_channel_name(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.name = "general"
        with patch("bot.utils.channel_guard.config") as mock_config:
            mock_config.bot_chat_channel = "byte-chat"
            assert self._call(channel) is False

    def test_returns_false_for_empty_channel_name(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = MagicMock()
        channel.name = ""
        with patch("bot.utils.channel_guard.config") as mock_config:
            mock_config.bot_chat_channel = "byte-chat"
            assert self._call(channel) is False


# ---------------------------------------------------------------------------
# Tests: is_bot_chat_channel_by_guild_config
# ---------------------------------------------------------------------------

class TestIsBotChatChannelByGuildConfig:

    def _call(self, channel):
        from bot.utils.channel_guard import is_bot_chat_channel_by_guild_config
        return is_bot_chat_channel_by_guild_config(channel)

    def _make_text_channel(self, channel_id: int, channel_name: str, guild_id: int = 5000):
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = channel_name
        channel.guild = MagicMock()
        channel.guild.id = guild_id
        return channel

    def test_returns_true_for_dm_channel(self):
        channel = MagicMock(spec=discord.DMChannel)
        del channel.guild
        assert self._call(channel) is True

    def test_returns_true_when_guild_is_none(self):
        channel = MagicMock()
        channel.guild = None
        assert self._call(channel) is True

    def test_uses_db_config_when_channel_id_matches(self):
        channel = self._make_text_channel(channel_id=1234, channel_name="general")
        guild_config = {"bot_chat_channel_id": "1234", "bot_chat_channel_name": "general"}
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = guild_config
            assert self._call(channel) is True

    def test_uses_db_config_when_channel_id_does_not_match(self):
        channel = self._make_text_channel(channel_id=9999, channel_name="general")
        guild_config = {"bot_chat_channel_id": "1234", "bot_chat_channel_name": "bot-chat"}
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = guild_config
            assert self._call(channel) is False

    def test_falls_back_to_name_when_no_db_config(self):
        channel = self._make_text_channel(channel_id=555, channel_name="byte-chat")
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = None
            with patch("bot.utils.channel_guard.config") as mock_config:
                mock_config.bot_chat_channel = "byte-chat"
                assert self._call(channel) is True

    def test_falls_back_to_name_when_db_config_has_no_channel_id(self):
        channel = self._make_text_channel(channel_id=555, channel_name="byte-chat")
        # Config exists but no channel_id field
        guild_config = {"some_other_field": "value"}
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = guild_config
            with patch("bot.utils.channel_guard.config") as mock_config:
                mock_config.bot_chat_channel = "byte-chat"
                assert self._call(channel) is True

    def test_name_fallback_returns_false_for_wrong_name(self):
        channel = self._make_text_channel(channel_id=555, channel_name="random")
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = None
            with patch("bot.utils.channel_guard.config") as mock_config:
                mock_config.bot_chat_channel = "byte-chat"
                assert self._call(channel) is False

    def test_queries_db_with_correct_guild_id(self):
        channel = self._make_text_channel(channel_id=1, channel_name="test", guild_id=8888)
        with patch("bot.utils.channel_guard.db") as mock_db:
            mock_db.get_guild_config.return_value = None
            with patch("bot.utils.channel_guard.config") as mock_config:
                mock_config.bot_chat_channel = "test"
                self._call(channel)
                mock_db.get_guild_config.assert_called_once_with("8888")
