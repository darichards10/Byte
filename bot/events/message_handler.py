"""
on_message event handler — natural language chat with Claude.

Byte responds when:
  1. The message is in the designated #byte-chat channel (or channel set via /set_chat_channel)
  2. The bot is @mentioned in any channel
  3. The message is a DM

Byte ignores:
  - Its own messages (infinite loop prevention)
  - Other bots
  - Messages in any other channel (no @mention)
"""

import logging
import discord
from discord.ext import commands

from bot.claude_client import claude
from bot import db
from bot.utils.formatters import send_chunked
from bot.utils.channel_guard import is_bot_chat_channel_by_guild_config

logger = logging.getLogger(__name__)

# Per-channel processing lock — prevents overlapping Claude calls in the same channel
_processing: set[int] = set()


class MessageHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ── Guard 1: Never respond to self ───────────────────────────────────
        if message.author == self.bot.user:
            return

        # ── Guard 2: Ignore all bots ─────────────────────────────────────────
        if message.author.bot:
            return

        # ── Guard 3: Determine if Byte should respond ────────────────────────
        is_mention = self.bot.user in message.mentions
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_designated = is_bot_chat_channel_by_guild_config(message.channel)

        if not (is_mention or is_dm or is_designated):
            return

        # ── Guard 4: Prevent concurrent calls for the same channel ───────────
        if message.channel.id in _processing:
            return
        _processing.add(message.channel.id)

        try:
            # Strip @mention prefix from content
            content = message.content
            if is_mention:
                content = (
                    content
                    .replace(f"<@{self.bot.user.id}>", "")
                    .replace(f"<@!{self.bot.user.id}>", "")
                    .strip()
                )

            if not content:
                await message.reply(
                    "Hey! Ask me anything — recipes, meal plans, workouts, or nutrition advice. "
                    "You can also use `/help` to see all available commands."
                )
                return

            async with message.channel.typing():
                user_id = str(message.author.id)
                channel_id = str(message.channel.id)
                username = message.author.display_name

                profile = db.get_or_create_profile(user_id, username)
                history = db.get_conversation_history(user_id, channel_id)

                response_text = await claude.chat(
                    user_message=content,
                    history=history,
                    profile=profile,
                )

                db.save_conversation_turn(
                    user_id=user_id,
                    channel_id=channel_id,
                    user_message=content,
                    bot_response=response_text,
                )

            await send_chunked(message.channel, response_text, reply_to=message)

        except Exception as e:
            logger.error(
                f"on_message error — user={message.author.id} channel={message.channel.id}: {e}",
                exc_info=True,
            )
            await message.reply(
                "Sorry, I hit an error processing that. Please try again in a moment!"
            )
        finally:
            _processing.discard(message.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageHandler(bot))
