import discord
from discord import app_commands
from discord.ext import commands

from bot import db
from bot.config import config


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="set_chat_channel",
        description="Set the channel where Byte responds to free-form messages (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_chat_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        db.set_guild_chat_channel(guild_id, str(channel.id), channel.name)
        await interaction.followup.send(
            f"Byte will now respond to free-form messages in {channel.mention}.\n"
            f"Users can also @mention Byte in any channel.",
            ephemeral=True,
        )

    @set_chat_channel.error
    async def set_chat_channel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You need Administrator permission to set the chat channel.",
                ephemeral=True,
            )

    @app_commands.command(name="bot_status", description="Check Byte's connection and configuration status")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        latency_ms = round(self.bot.latency * 1000)
        guild_config = db.get_guild_config(str(interaction.guild.id)) if interaction.guild else None
        chat_channel = (
            guild_config.get("bot_chat_channel_name", config.bot_chat_channel)
            if guild_config
            else config.bot_chat_channel
        )
        await interaction.followup.send(
            f"**Byte Status**\n"
            f"- Latency: {latency_ms}ms\n"
            f"- Environment: {config.environment}\n"
            f"- DynamoDB table: `{config.dynamodb_table_name}`\n"
            f"- Chat channel: `#{chat_channel}`\n"
            f"- Guilds: {len(self.bot.guilds)}",
            ephemeral=True,
        )

    @app_commands.command(name="help", description="Overview of all Byte commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Byte — Command Overview",
            description=(
                "Your personal AI health & fitness coach.\n"
                "Chat freely in **#byte-chat** or **@Byte** me anywhere.\n"
                "Use `/commands category:…` for full details and examples on any group."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="🍽️ Recipes",
            value=(
                "`/recipe_ideas diet: cuisine: restrictions:` — AI recipe generation\n"
                "`/save_recipe name: diet_tag: ingredients: calories:` — Save a recipe\n"
                "`/my_recipes diet_filter:` — List saved recipes\n"
                "`/delete_recipe recipe_id:` — Remove a recipe\n"
                "⭐ React to any Byte message to auto-save the recipe"
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Meal Planning",
            value=(
                "`/meal_plan diet: days: calories:` — Weekly meal plan\n"
                "`/grocery_list servings:` — Shopping list from latest plan"
            ),
            inline=False,
        )
        embed.add_field(
            name="💪 Workouts",
            value=(
                "`/workout_plan type: duration: equipment:` — Generate a workout\n"
                "`/log_workout type: duration: exercises: notes: calories_burned:` — Log session\n"
                "`/my_workouts limit: type_filter:` — View history\n"
                "`/workout_analysis` — AI analysis of recent training"
            ),
            inline=False,
        )
        embed.add_field(
            name="👤 Profile",
            value=(
                "`/my_profile` · `/set_diet` · `/set_activity`\n"
                "`/set_allergies` · `/set_restrictions` · `/set_goals`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔔 Reminders",
            value=(
                "`/set_reminder message: schedule:` — Create reminder\n"
                "`/list_reminders` · `/delete_reminder reminder_id:`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Admin / Info",
            value=(
                "`/bot_status` · `/set_chat_channel channel:` (admin)\n"
                "`/help` · `/commands category:`"
            ),
            inline=False,
        )
        embed.set_footer(text="Powered by Claude AI · Byte v1.0  |  Use /commands for full details")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /commands — per-category detailed reference ───────────────────────────

    @app_commands.command(name="commands", description="Detailed command reference — pick a category")
    @app_commands.choices(category=[
        app_commands.Choice(name="Recipes",       value="recipes"),
        app_commands.Choice(name="Meal Planning", value="meals"),
        app_commands.Choice(name="Workouts",      value="workouts"),
        app_commands.Choice(name="Profile",       value="profile"),
        app_commands.Choice(name="Reminders",     value="reminders"),
        app_commands.Choice(name="Admin / Info",  value="admin"),
    ])
    async def commands_reference(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
    ):
        embeds = {
            "recipes": _embed_recipes(),
            "meals":   _embed_meals(),
            "workouts": _embed_workouts(),
            "profile": _embed_profile(),
            "reminders": _embed_reminders(),
            "admin":   _embed_admin(),
        }
        await interaction.response.send_message(
            embed=embeds[category.value], ephemeral=True
        )


# ── Detail embed builders (module-level helpers) ──────────────────────────────

def _embed_recipes() -> discord.Embed:
    e = discord.Embed(title="🍽️ Recipe Commands", color=discord.Color.orange())
    e.add_field(name="/recipe_ideas", value=(
        "Generate an AI recipe for a specific diet.\n"
        "**Required:** `diet` (choice)\n"
        "**Optional:** `cuisine` — style e.g. Italian, Mexican\n"
        "**Optional:** `restrictions` — one-time extra restrictions\n"
        "**Example:** `/recipe_ideas diet:Keto cuisine:Italian`"
    ), inline=False)
    e.add_field(name="/save_recipe", value=(
        "Manually save a recipe to your favorites.\n"
        "**Required:** `name`, `diet_tag`, `ingredients` (comma-separated)\n"
        "**Optional:** `calories` — per serving\n"
        "**Example:** `/save_recipe name:\"Egg Bowl\" diet_tag:keto ingredients:\"eggs, avocado\"`"
    ), inline=False)
    e.add_field(name="/my_recipes", value=(
        "List all your saved recipes.\n"
        "**Optional:** `diet_filter` — filter by diet type\n"
        "**Example:** `/my_recipes diet_filter:Vegan`"
    ), inline=False)
    e.add_field(name="/delete_recipe", value=(
        "Remove a saved recipe by its ID.\n"
        "**Required:** `recipe_id` — get from `/my_recipes`\n"
        "**Example:** `/delete_recipe recipe_id:a1b2c3d4`"
    ), inline=False)
    e.add_field(name="⭐ Auto-save", value=(
        "React with ⭐ to any message Byte sends and the recipe in that message "
        "will be automatically saved to your favorites. Byte will DM you a confirmation."
    ), inline=False)
    return e


def _embed_meals() -> discord.Embed:
    e = discord.Embed(title="📅 Meal Planning Commands", color=discord.Color.yellow())
    e.add_field(name="/meal_plan", value=(
        "Generate a full meal plan.\n"
        "**Required:** `diet` (choice)\n"
        "**Optional:** `days` — 1 to 7, defaults to 7\n"
        "**Optional:** `calories` — daily calorie target\n"
        "**Example:** `/meal_plan diet:Keto days:5 calories:1800`"
    ), inline=False)
    e.add_field(name="/grocery_list", value=(
        "Generate a grocery list from your most recent `/meal_plan`.\n"
        "**Optional:** `servings` — number of people, defaults to 1\n"
        "**Example:** `/grocery_list servings:2`\n"
        "**Note:** Run `/meal_plan` first — grocery list uses the stored plan."
    ), inline=False)
    return e


def _embed_workouts() -> discord.Embed:
    e = discord.Embed(title="💪 Workout Commands", color=discord.Color.blue())
    e.add_field(name="/workout_plan", value=(
        "Generate a personalized workout.\n"
        "**Required:** `type` — Strength, Cardio, HIIT, Yoga, Stretching, Full/Upper/Lower Body\n"
        "**Optional:** `duration` — minutes, 10–120, defaults to 45\n"
        "**Optional:** `equipment` — freeform e.g. dumbbells, none, resistance bands\n"
        "**Example:** `/workout_plan type:Strength duration:60 equipment:dumbbells`"
    ), inline=False)
    e.add_field(name="/log_workout", value=(
        "Log a completed workout to your history.\n"
        "**Required:** `type` (choice), `duration` (minutes)\n"
        "**Optional:** `exercises` — comma-separated list\n"
        "**Optional:** `notes`, `calories_burned`\n"
        "**Example:** `/log_workout type:Strength duration:45 exercises:\"squat, bench press\"`"
    ), inline=False)
    e.add_field(name="/my_workouts", value=(
        "View your workout history.\n"
        "**Optional:** `limit` — number of entries, 1–25, defaults to 10\n"
        "**Optional:** `type_filter` — filter by workout type\n"
        "**Example:** `/my_workouts limit:5 type_filter:Cardio`"
    ), inline=False)
    e.add_field(name="/workout_analysis", value=(
        "Get an AI analysis of your last 10 workouts.\n"
        "Byte will identify patterns, muscle group gaps, and suggest improvements.\n"
        "No parameters required."
    ), inline=False)
    return e


def _embed_profile() -> discord.Embed:
    e = discord.Embed(title="👤 Profile Commands", color=discord.Color.purple())
    e.description = (
        "Your profile is used to personalise every AI response. "
        "Allergies are **always** excluded from recipes and meal plans."
    )
    e.add_field(name="/my_profile", value="View all your current profile settings. (ephemeral)", inline=False)
    e.add_field(name="/set_diet diet:[choice]", value=(
        "Set your preferred diet type. Used in all recipe and meal plan AI responses.\n"
        "Choices: Standard, Keto, Paleo, Vegan, Vegetarian, Mediterranean, Carnivore, Whole30"
    ), inline=False)
    e.add_field(name="/set_activity level:[choice]", value=(
        "Set your activity level for tailored workout and nutrition advice.\n"
        "Choices: Sedentary, Lightly active, Moderately active, Very active, Extremely active"
    ), inline=False)
    e.add_field(name="/set_allergies allergies:[required]", value=(
        "Set food allergies as a comma-separated list.\n"
        "⚠️ These are **never** included in any recipe or meal plan.\n"
        "**Example:** `/set_allergies allergies:\"peanuts, shellfish, tree nuts\"`"
    ), inline=False)
    e.add_field(name="/set_restrictions restrictions:[required]", value=(
        "Set dietary restrictions (different from allergies — preference-based).\n"
        "**Example:** `/set_restrictions restrictions:\"gluten-free, dairy-free\"`"
    ), inline=False)
    e.add_field(name="/set_goals goals:[required]", value=(
        "Describe your fitness goals in plain text.\n"
        "**Example:** `/set_goals goals:\"lose 15 lbs and build core strength\"`"
    ), inline=False)
    return e


def _embed_reminders() -> discord.Embed:
    e = discord.Embed(title="🔔 Reminder Commands", color=discord.Color.red())
    e.add_field(name="/set_reminder", value=(
        "Create a recurring reminder.\n"
        "**Required:** `message` — what to remind you\n"
        "**Required:** `schedule` — freeform e.g. daily, weekly, every Monday\n"
        "Reminders are dispatched by a weekly AWS EventBridge Lambda trigger.\n"
        "**Example:** `/set_reminder message:\"Plan meals for the week\" schedule:weekly`"
    ), inline=False)
    e.add_field(name="/list_reminders", value=(
        "View all your active reminders and their IDs. (ephemeral)"
    ), inline=False)
    e.add_field(name="/delete_reminder reminder_id:[required]", value=(
        "Delete a reminder by its ID.\n"
        "Get IDs from `/list_reminders`.\n"
        "**Example:** `/delete_reminder reminder_id:ab12cd34`"
    ), inline=False)
    return e


def _embed_admin() -> discord.Embed:
    e = discord.Embed(title="⚙️ Admin & Info Commands", color=discord.Color.greyple())
    e.add_field(name="/bot_status", value=(
        "Show Byte's current connection status.\n"
        "Displays: latency, environment (local/production), DynamoDB table, chat channel, guild count."
    ), inline=False)
    e.add_field(name="/set_chat_channel channel:[required]", value=(
        "Set which text channel Byte listens to for free-form messages.\n"
        "**Requires Administrator permission.**\n"
        "Byte always responds to @mentions regardless of this setting.\n"
        "**Example:** `/set_chat_channel channel:#byte-chat`"
    ), inline=False)
    e.add_field(name="/help", value=(
        "Quick overview of all commands grouped by category with parameter hints.\n"
        "Use this for a fast reminder of what's available."
    ), inline=False)
    e.add_field(name="/commands category:[choice]", value=(
        "This command — detailed reference for one category.\n"
        "Shows every parameter, required vs optional, and a usage example.\n"
        "Categories: Recipes, Meal Planning, Workouts, Profile, Reminders, Admin"
    ), inline=False)
    return e


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
