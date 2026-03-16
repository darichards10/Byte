import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.utils.formatters import profile_embed


DIET_CHOICES = [
    app_commands.Choice(name="Standard", value="standard"),
    app_commands.Choice(name="Keto", value="keto"),
    app_commands.Choice(name="Paleo", value="paleo"),
    app_commands.Choice(name="Vegan", value="vegan"),
    app_commands.Choice(name="Vegetarian", value="vegetarian"),
    app_commands.Choice(name="Mediterranean", value="mediterranean"),
    app_commands.Choice(name="Carnivore", value="carnivore"),
    app_commands.Choice(name="Whole30", value="whole30"),
]

ACTIVITY_CHOICES = [
    app_commands.Choice(name="Sedentary (desk job, little exercise)", value="sedentary"),
    app_commands.Choice(name="Lightly active (1-3 days/week)", value="lightly_active"),
    app_commands.Choice(name="Moderately active (3-5 days/week)", value="moderately_active"),
    app_commands.Choice(name="Very active (6-7 days/week)", value="very_active"),
    app_commands.Choice(name="Extremely active (athlete/physical job)", value="extremely_active"),
]


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="my_profile", description="View your Byte health and fitness profile")
    async def my_profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)
        embed = profile_embed(profile, interaction.user.display_name)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="set_diet", description="Set your preferred diet type")
    @app_commands.choices(diet=DIET_CHOICES)
    async def set_diet(self, interaction: discord.Interaction, diet: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        db.put_user_profile(str(interaction.user.id), preferred_diet=diet.value)
        await interaction.followup.send(
            f"Updated your preferred diet to **{diet.name}**. "
            f"Byte will use this in all recipe and meal plan suggestions.",
            ephemeral=True,
        )

    @app_commands.command(name="set_activity", description="Set your activity level")
    @app_commands.choices(level=ACTIVITY_CHOICES)
    async def set_activity(self, interaction: discord.Interaction, level: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        db.put_user_profile(str(interaction.user.id), activity_level=level.value)
        await interaction.followup.send(
            f"Updated your activity level to **{level.name}**.",
            ephemeral=True,
        )

    @app_commands.command(name="set_allergies", description="Set your food allergies (comma-separated)")
    async def set_allergies(
        self,
        interaction: discord.Interaction,
        allergies: str,
    ):
        await interaction.response.defer(ephemeral=True)
        allergy_list = [a.strip().lower() for a in allergies.split(",") if a.strip()]
        db.put_user_profile(str(interaction.user.id), allergies=allergy_list)
        formatted = ", ".join(allergy_list) if allergy_list else "none"
        await interaction.followup.send(
            f"Allergies updated: **{formatted}**\n"
            f"Byte will never include these in recipes or meal plans.",
            ephemeral=True,
        )

    @app_commands.command(name="set_restrictions", description="Set dietary restrictions (comma-separated, e.g. gluten-free, dairy-free)")
    async def set_restrictions(
        self,
        interaction: discord.Interaction,
        restrictions: str,
    ):
        await interaction.response.defer(ephemeral=True)
        restriction_list = [r.strip().lower() for r in restrictions.split(",") if r.strip()]
        db.put_user_profile(str(interaction.user.id), dietary_restrictions=restriction_list)
        formatted = ", ".join(restriction_list) if restriction_list else "none"
        await interaction.followup.send(
            f"Dietary restrictions updated: **{formatted}**",
            ephemeral=True,
        )

    @app_commands.command(name="set_goals", description="Set your fitness goals")
    async def set_goals(self, interaction: discord.Interaction, goals: str):
        await interaction.response.defer(ephemeral=True)
        db.put_user_profile(str(interaction.user.id), fitness_goals=goals)
        await interaction.followup.send(
            f"Fitness goals updated: **{goals}**\n"
            f"Byte will factor these into workout and nutrition advice.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
