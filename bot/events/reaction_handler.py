"""
on_raw_reaction_add event handler.

⭐ reaction on any Byte message → auto-save the recipe from that message to favorites.
"""

import logging
import re
import discord
from discord.ext import commands

from bot import db

logger = logging.getLogger(__name__)

SAVE_EMOJI = "⭐"


def _parse_recipe_from_message(content: str) -> dict | None:
    """
    Attempt to extract a recipe name from a Claude-generated recipe message.
    Returns a dict with basic fields if found, None otherwise.
    """
    lines = content.strip().splitlines()
    name = None

    # Try to find the recipe name — typically the first non-empty bold line
    for line in lines[:5]:
        line = line.strip()
        # Match **Recipe Name** or just the first meaningful line
        bold_match = re.match(r"\*\*(.+?)\*\*", line)
        if bold_match:
            name = bold_match.group(1).strip()
            break
        if line and not line.startswith("-") and len(line) < 80:
            name = line
            break

    if not name:
        return None

    # Extract ingredients block (lines starting with - after "Ingredients" section)
    ingredients = []
    in_ingredients = False
    for line in lines:
        stripped = line.strip()
        if re.search(r"ingredient", stripped, re.IGNORECASE):
            in_ingredients = True
            continue
        if in_ingredients:
            if stripped.startswith("-"):
                ingredients.append(stripped.lstrip("- ").strip())
            elif stripped and not stripped.startswith("-"):
                in_ingredients = False

    return {
        "name": name,
        "ingredients": ingredients,
        "instructions": [],  # full text saved as-is
        "diet_tags": [],
    }


class ReactionHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Only handle ⭐
        if str(payload.emoji) != SAVE_EMOJI:
            return

        # Don't react to the bot's own reactions
        if payload.user_id == self.bot.user.id:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        except discord.Forbidden:
            return

        # Only save messages sent by Byte itself
        if message.author != self.bot.user:
            return

        # Try to parse the recipe from the message content
        recipe_data = _parse_recipe_from_message(message.content)
        if not recipe_data:
            try:
                user = await self.bot.fetch_user(payload.user_id)
                await user.send(
                    "I couldn't automatically parse a recipe from that message. "
                    "Try using `/save_recipe` to manually save it!"
                )
            except discord.Forbidden:
                pass
            return

        user_id = str(payload.user_id)
        recipe_id = db.save_recipe(
            user_id=user_id,
            name=recipe_data["name"],
            ingredients=recipe_data["ingredients"],
            instructions=[message.content],  # save full message as instructions
            diet_tags=recipe_data["diet_tags"],
        )

        # Confirm save via DM (to avoid cluttering the channel)
        try:
            user = await self.bot.fetch_user(payload.user_id)
            await user.send(
                f"Saved **{recipe_data['name']}** to your recipes! "
                f"(ID: `{recipe_id}`)\n"
                f"View all saved recipes with `/my_recipes`."
            )
        except discord.Forbidden:
            # User has DMs disabled — add a ✅ reaction as confirmation instead
            await message.add_reaction("✅")

        logger.info(f"Recipe saved via ⭐ reaction: user={user_id} recipe_id={recipe_id}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionHandler(bot))
