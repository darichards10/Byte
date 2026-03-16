"""
Determines whether Byte should respond to a message in a given channel.
"""

import discord
from discord.ext import commands

from bot.config import config
from bot import db


def is_bot_chat_channel(channel: discord.abc.Messageable) -> bool:
    """
    Returns True if the channel is:
    - A DM (no guild)
    - Named exactly as BOT_CHAT_CHANNEL env var (default: 'byte-chat')
    """
    # Always respond in DMs
    if not hasattr(channel, "guild") or channel.guild is None:
        return True

    return getattr(channel, "name", "") == config.bot_chat_channel


def is_bot_chat_channel_by_guild_config(channel: discord.TextChannel) -> bool:
    """
    Check guild config in DynamoDB for the configured channel ID.
    Falls back to name-based check if no guild config is set.
    """
    if not hasattr(channel, "guild") or channel.guild is None:
        return True

    guild_config = db.get_guild_config(str(channel.guild.id))
    if guild_config and guild_config.get("bot_chat_channel_id"):
        return str(channel.id) == guild_config["bot_chat_channel_id"]

    # Fallback to name-based check
    return channel.name == config.bot_chat_channel
