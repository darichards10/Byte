"""
Discord message formatting utilities.
"""

import discord


DISCORD_MAX_LENGTH = 2000
CHUNK_SIZE = 1900  # leave headroom for chunk labels


def chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """
    Split text into chunks that fit within Discord's message limit.
    Tries to split on newlines to avoid cutting mid-sentence.
    """
    if len(text) <= size:
        return [text]

    chunks = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        # Try to split on last newline within the size limit
        split_at = text.rfind("\n", 0, size)
        if split_at == -1:
            split_at = size
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks


async def send_chunked(
    target: discord.abc.Messageable,
    text: str,
    reply_to: discord.Message | None = None,
) -> None:
    """Send a potentially long response, chunking it if needed."""
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"{chunk}\n*(part {i + 1}/{len(chunks)})*"
        if reply_to and i == 0:
            await reply_to.reply(chunk)
        else:
            await target.send(chunk)


def profile_embed(profile: dict, username: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"Byte Profile — {username}",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Preferred Diet",
        value=profile.get("preferred_diet", "standard").title(),
        inline=True,
    )
    embed.add_field(
        name="Activity Level",
        value=profile.get("activity_level", "moderately_active").replace("_", " ").title(),
        inline=True,
    )
    restrictions = profile.get("dietary_restrictions", [])
    embed.add_field(
        name="Dietary Restrictions",
        value=", ".join(restrictions) if restrictions else "None",
        inline=False,
    )
    allergies = profile.get("allergies", [])
    embed.add_field(
        name="Allergies",
        value=", ".join(allergies) if allergies else "None",
        inline=False,
    )
    embed.add_field(
        name="Fitness Goals",
        value=profile.get("fitness_goals") or "Not set",
        inline=False,
    )
    return embed


def recipe_list_embed(recipes: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="Your Saved Recipes",
        color=discord.Color.orange(),
    )
    if not recipes:
        embed.description = "No saved recipes yet. Ask Byte for a recipe and save it with /save_recipe!"
        return embed

    for recipe in recipes[:10]:  # cap at 10 for embed field limits
        tags = ", ".join(recipe.get("diet_tags", [])) or "untagged"
        calories = recipe.get("calories")
        cal_text = f" • {calories} cal/serving" if calories else ""
        embed.add_field(
            name=recipe.get("name", "Unnamed"),
            value=f"ID: `{recipe.get('recipe_id', '?')}` • {tags}{cal_text}",
            inline=False,
        )
    return embed


def workout_list_embed(workouts: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="Your Workout History",
        color=discord.Color.blue(),
    )
    if not workouts:
        embed.description = "No workouts logged yet. Use /log_workout to log your first session!"
        return embed

    for w in workouts:
        date = w.get("logged_at", "")[:10]
        wtype = w.get("workout_type", "?").replace("_", " ").title()
        duration = w.get("duration_min", "?")
        calories = w.get("calories_burned")
        cal_text = f" • {calories} cal burned" if calories else ""
        exercises = w.get("exercises", [])
        ex_text = f"\n{', '.join(exercises[:3])}" if exercises else ""
        embed.add_field(
            name=f"{date} — {wtype} ({duration} min){cal_text}",
            value=ex_text or "\u200b",  # zero-width space if no exercises
            inline=False,
        )
    return embed
