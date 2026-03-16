import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.claude_client import claude
from bot.utils.formatters import send_chunked, recipe_list_embed

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


class Recipes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="recipe_ideas", description="Generate a recipe tailored to your diet")
    @app_commands.choices(diet=DIET_CHOICES)
    async def recipe_ideas(
        self,
        interaction: discord.Interaction,
        diet: app_commands.Choice[str],
        cuisine: str | None = None,
        restrictions: str | None = None,
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)

        response = await claude.generate_recipe(
            diet=diet.value,
            cuisine=cuisine,
            restrictions=restrictions,
            profile=profile,
        )

        await send_chunked(
            interaction.channel,
            f"Here's a **{diet.name}** recipe for you! React with ⭐ to save it.\n\n{response}",
        )
        await interaction.followup.send("Recipe generated above!", ephemeral=True)

    @app_commands.command(name="save_recipe", description="Save a recipe to your favorites")
    async def save_recipe(
        self,
        interaction: discord.Interaction,
        name: str,
        diet_tag: str,
        ingredients: str,
        calories: int | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        ingredient_list = [i.strip() for i in ingredients.split(",") if i.strip()]
        recipe_id = db.save_recipe(
            user_id=user_id,
            name=name,
            ingredients=ingredient_list,
            instructions=[],
            diet_tags=[diet_tag.strip().lower()],
            calories=calories,
        )
        await interaction.followup.send(
            f"Saved **{name}** to your recipes! (ID: `{recipe_id}`)\n"
            f"View all recipes with `/my_recipes`.",
            ephemeral=True,
        )

    @app_commands.command(name="my_recipes", description="List your saved recipes")
    @app_commands.choices(diet_filter=DIET_CHOICES)
    async def my_recipes(
        self,
        interaction: discord.Interaction,
        diet_filter: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        filter_value = diet_filter.value if diet_filter else None
        recipes = db.get_recipes(user_id, diet_filter=filter_value)
        embed = recipe_list_embed(recipes)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="delete_recipe", description="Remove a saved recipe by ID")
    async def delete_recipe(self, interaction: discord.Interaction, recipe_id: str):
        await interaction.response.defer(ephemeral=True)
        db.delete_recipe(str(interaction.user.id), recipe_id)
        await interaction.followup.send(
            f"Recipe `{recipe_id}` removed from your saved recipes.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Recipes(bot))
