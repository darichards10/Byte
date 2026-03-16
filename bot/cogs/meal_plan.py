import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.claude_client import claude
from bot.utils.formatters import send_chunked

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


class MealPlan(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="meal_plan",
        description="Generate a weekly meal plan tailored to your diet",
    )
    @app_commands.choices(diet=DIET_CHOICES)
    async def meal_plan(
        self,
        interaction: discord.Interaction,
        diet: app_commands.Choice[str],
        days: int = 7,
        calories: int | None = None,
    ):
        if days < 1 or days > 7:
            await interaction.response.send_message(
                "Days must be between 1 and 7.", ephemeral=True
            )
            return

        await interaction.response.defer()
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)

        # Use profile diet if not specified differently
        effective_diet = diet.value

        plan_text = await claude.generate_meal_plan(
            diet=effective_diet,
            days=days,
            calories=calories,
            profile=profile,
        )

        # Store the meal plan so /grocery_list can reference it
        db.put_user_profile(user_id, last_meal_plan=plan_text, last_meal_plan_diet=effective_diet)

        header = f"**{days}-Day {diet.name} Meal Plan**"
        if calories:
            header += f" (~{calories} cal/day)"
        header += "\n\n"

        await send_chunked(interaction.channel, header + plan_text)
        await interaction.followup.send(
            "Meal plan posted above! Use `/grocery_list` to generate a shopping list from it.",
            ephemeral=True,
        )

    @app_commands.command(
        name="grocery_list",
        description="Generate a grocery list from your most recent meal plan",
    )
    async def grocery_list(
        self,
        interaction: discord.Interaction,
        servings: int = 1,
    ):
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        profile = db.get_or_create_profile(user_id, interaction.user.display_name)

        last_plan = profile.get("last_meal_plan")
        if not last_plan:
            await interaction.followup.send(
                "No meal plan found. Generate one first with `/meal_plan`!",
                ephemeral=True,
            )
            return

        grocery_text = await claude.generate_grocery_list(
            meal_plan_text=last_plan,
            servings=servings,
            profile=profile,
        )

        serving_label = f"(for {servings} people)" if servings > 1 else ""
        await send_chunked(
            interaction.channel,
            f"**Grocery List** {serving_label}\n\n{grocery_text}",
        )
        await interaction.followup.send("Grocery list posted above!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MealPlan(bot))
