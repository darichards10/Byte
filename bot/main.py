"""
Byte Bot — entry point.
Run with: python -m bot.main
"""

import asyncio
import logging

import discord
from discord.ext import commands

from bot.config import config
from bot import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Privileged intents — both must be enabled in Discord Developer Portal:
# Bot → Privileged Gateway Intents → Message Content Intent + Server Members Intent
intents = discord.Intents.default()
intents.message_content = True  # required for on_message natural language chat
intents.reactions = True        # required for on_raw_reaction_add (🌟 recipe saver)

bot = commands.Bot(
    command_prefix="!",       # fallback prefix — slash commands are primary
    intents=intents,
    help_command=None,        # disabled — /help slash command replaces it
    description="Byte — your personal health & fitness AI coach",
)

COGS = [
    "bot.cogs.recipes",
    "bot.cogs.workouts",
    "bot.cogs.meal_plan",
    "bot.cogs.profile",
    "bot.cogs.reminders",
    "bot.cogs.admin",
    "bot.cogs.food_log",
    "bot.events.message_handler",
    "bot.events.reaction_handler",
]


@bot.event
async def on_ready():
    logger.info(f"Byte is online: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"DynamoDB table: {config.dynamodb_table_name}")
    logger.info(f"Bot chat channel: #{config.bot_chat_channel}")

    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s) globally")
    except Exception as e:
        logger.error(f"Slash command sync failed: {e}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="your health goals | /help",
        )
    )


@bot.event
async def on_disconnect():
    logger.warning("Byte disconnected from Discord gateway")


@bot.event
async def on_resumed():
    logger.info("Byte reconnected and resumed gateway session")


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"Command error in {ctx.command}: {error}")


async def main():
    if not config.discord_token:
        logger.error(
            "DISCORD_TOKEN is not set. "
            "Copy .env.example to .env and add your bot token."
        )
        return

    async with bot:
        # Create DynamoDB table in local dev (no-op in production)
        db.ensure_table()

        for cog_path in COGS:
            try:
                await bot.load_extension(cog_path)
                logger.info(f"Loaded cog: {cog_path}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog_path}: {e}")

        await bot.start(config.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
