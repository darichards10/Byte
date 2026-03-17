"""
Food/meal logging commands for Byte Bot.

Security model:
  - user_id is ALWAYS derived from interaction.user.id — never from user input.
  - All responses use ephemeral=True — food data is invisible to other server members.
  - DynamoDB PK = USER#{user_id}: cross-user access or deletion is structurally
    impossible regardless of the food_id value supplied by the caller.
  - Data is keyed by Discord user ID (global), so the same user's logs are
    accessible from any server they're in — personal data, not guild-scoped.
"""

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.claude_client import claude
from bot.utils.formatters import food_log_embed

_MEAL_CHOICES = [
    app_commands.Choice(name="Breakfast",    value="breakfast"),
    app_commands.Choice(name="Lunch",        value="lunch"),
    app_commands.Choice(name="Dinner",       value="dinner"),
    app_commands.Choice(name="Snack",        value="snack"),
    app_commands.Choice(name="Pre-Workout",  value="pre_workout"),
    app_commands.Choice(name="Post-Workout", value="post_workout"),
]

_MAX_NOTES_LEN = 200
_MAX_FOOD_ITEMS = 20
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FoodLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /log_food ─────────────────────────────────────────────────────────────

    @app_commands.command(name="log_food", description="Log a meal or food entry")
    @app_commands.choices(meal_type=_MEAL_CHOICES)
    async def log_food(
        self,
        interaction: discord.Interaction,
        meal_type: app_commands.Choice[str],
        foods: str,
        calories: int | None = None,
        protein: int | None = None,
        carbs: int | None = None,
        fat: int | None = None,
        notes: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)  # always from Discord — never user-supplied

        if notes and len(notes) > _MAX_NOTES_LEN:
            await interaction.followup.send(
                f"Notes must be {_MAX_NOTES_LEN} characters or fewer.", ephemeral=True
            )
            return

        food_list = [f.strip() for f in foods.split(",") if f.strip()]
        if not food_list:
            await interaction.followup.send(
                "Please provide at least one food item.", ephemeral=True
            )
            return
        food_list = food_list[:_MAX_FOOD_ITEMS]

        food_id = db.log_food_entry(
            user_id=user_id,
            meal_type=meal_type.value,
            foods=food_list,
            calories=calories,
            protein_g=protein,
            carbs_g=carbs,
            fat_g=fat,
            notes=notes or "",
        )

        lines = [f"Logged **{meal_type.name}**: {', '.join(food_list[:5])}"]
        if len(food_list) > 5:
            lines[0] += f" (+{len(food_list) - 5} more)"

        macro_parts = []
        if calories is not None:
            macro_parts.append(f"{calories} cal")
        if protein is not None:
            macro_parts.append(f"P:{protein}g")
        if carbs is not None:
            macro_parts.append(f"C:{carbs}g")
        if fat is not None:
            macro_parts.append(f"F:{fat}g")
        if macro_parts:
            lines.append("Macros: " + " · ".join(macro_parts))
        if notes:
            lines.append(f"Notes: {notes}")
        lines.append(f"Entry ID: `{food_id}`")
        lines.append("View your log with `/my_food_log`.")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ── /my_food_log ──────────────────────────────────────────────────────────

    @app_commands.command(name="my_food_log", description="View your food log")
    @app_commands.choices(meal_filter=_MEAL_CHOICES)
    async def my_food_log(
        self,
        interaction: discord.Interaction,
        limit: int = 10,
        meal_filter: app_commands.Choice[str] | None = None,
        date: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)  # always from Discord — never user-supplied
        limit = min(max(limit, 1), 25)

        if date and not _DATE_RE.match(date):
            await interaction.followup.send(
                "Date must be in YYYY-MM-DD format, e.g. `2026-03-17`.", ephemeral=True
            )
            return

        filter_value = meal_filter.value if meal_filter else None
        entries = db.get_food_log(user_id, limit=limit, meal_type=filter_value, date=date)

        embed = food_log_embed(entries)
        if meal_filter:
            embed.title = f"Your Food Log — {meal_filter.name}"
        elif date:
            embed.title = f"Your Food Log — {date}"

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /delete_food_log ──────────────────────────────────────────────────────

    @app_commands.command(name="delete_food_log", description="Delete a food log entry by its ID")
    async def delete_food_log(
        self,
        interaction: discord.Interaction,
        food_id: str,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)  # always from Discord — never user-supplied

        # PK is built from user_id — cross-user deletion is structurally impossible.
        # DynamoDB silently no-ops if the item doesn't exist under this user's partition.
        db.delete_food_entry(user_id, food_id)

        await interaction.followup.send(
            f"Food log entry `{food_id}` removed.", ephemeral=True
        )

    # ── /nutrition_summary ────────────────────────────────────────────────────

    @app_commands.command(
        name="nutrition_summary",
        description="Get an AI analysis of your recent eating patterns",
    )
    async def nutrition_summary(
        self,
        interaction: discord.Interaction,
        days: int = 7,
    ):
        if days < 1 or days > 14:
            await interaction.response.send_message(
                "Days must be between 1 and 14.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)  # always from Discord — never user-supplied

        profile = db.get_or_create_profile(user_id, interaction.user.display_name)
        entries = db.get_food_log(user_id, limit=20 * days)

        analysis = await claude.analyze_food_log(entries=entries, days=days, profile=profile)

        await interaction.followup.send(
            f"**Nutrition Summary (last {days} day(s))**\n\n{analysis}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(FoodLog(bot))
