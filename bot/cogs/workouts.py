import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.claude_client import claude
from bot.utils.formatters import send_chunked, workout_list_embed

WORKOUT_CHOICES = [
    app_commands.Choice(name="Strength", value="strength"),
    app_commands.Choice(name="Cardio", value="cardio"),
    app_commands.Choice(name="HIIT", value="hiit"),
    app_commands.Choice(name="Yoga", value="yoga"),
    app_commands.Choice(name="Stretching / Mobility", value="stretching"),
    app_commands.Choice(name="Full Body", value="full_body"),
    app_commands.Choice(name="Upper Body", value="upper_body"),
    app_commands.Choice(name="Lower Body", value="lower_body"),
]


class Workouts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="workout_plan", description="Generate a personalized workout")
    @app_commands.choices(type=WORKOUT_CHOICES)
    async def workout_plan(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        duration: int = 45,
        equipment: str | None = None,
    ):
        if duration < 10 or duration > 120:
            await interaction.response.send_message(
                "Duration must be between 10 and 120 minutes.", ephemeral=True
            )
            return

        await interaction.response.defer()
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)

        workout_text = await claude.generate_workout(
            workout_type=type.value,
            duration_min=duration,
            equipment=equipment,
            profile=profile,
        )

        await send_chunked(
            interaction.channel,
            f"**{duration}-Minute {type.name} Workout**\n\n{workout_text}",
        )
        await interaction.followup.send(
            "Workout posted above! Log it when you're done with `/log_workout`.",
            ephemeral=True,
        )

    @app_commands.command(name="log_workout", description="Log a completed workout")
    @app_commands.choices(type=WORKOUT_CHOICES)
    async def log_workout(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        duration: int,
        exercises: str | None = None,
        notes: str | None = None,
        calories_burned: int | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        exercise_list = []
        if exercises:
            exercise_list = [e.strip() for e in exercises.split(",") if e.strip()]

        db.log_workout(
            user_id=user_id,
            workout_type=type.value,
            duration_min=duration,
            exercises=exercise_list,
            notes=notes or "",
            calories_burned=calories_burned,
        )

        parts = [f"Logged **{type.name}** — {duration} minutes"]
        if exercise_list:
            parts.append(f"Exercises: {', '.join(exercise_list)}")
        if calories_burned:
            parts.append(f"Calories burned: {calories_burned}")
        if notes:
            parts.append(f"Notes: {notes}")
        parts.append("Great work! View your history with `/my_workouts`.")

        await interaction.followup.send("\n".join(parts), ephemeral=True)

    @app_commands.command(name="my_workouts", description="View your workout history")
    @app_commands.choices(type_filter=WORKOUT_CHOICES)
    async def my_workouts(
        self,
        interaction: discord.Interaction,
        limit: int = 10,
        type_filter: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        limit = min(max(limit, 1), 25)
        user_id = str(interaction.user.id)
        filter_value = type_filter.value if type_filter else None
        workouts = db.get_workouts(user_id, limit=limit, workout_type=filter_value)
        embed = workout_list_embed(workouts)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="workout_analysis", description="Get AI analysis of your recent workout history")
    async def workout_analysis(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)
        workouts = db.get_workouts(user_id, limit=10)
        analysis = await claude.analyze_workout_history(workouts, profile=profile)
        await send_chunked(
            interaction.channel,
            f"**Your Workout Analysis**\n\n{analysis}",
        )
        await interaction.followup.send("Analysis posted above!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Workouts(bot))
