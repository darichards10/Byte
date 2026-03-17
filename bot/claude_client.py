"""
Anthropic Claude SDK wrapper for Byte Bot.

Responsibilities:
- Build system prompts from user profiles (rebuilt fresh every call — allergies always current)
- Maintain sliding window conversation history (last 20 messages)
- Provide domain-specific generation methods (meal plan, grocery list, workout, recipe)
"""

import logging
from anthropic import AsyncAnthropic
from bot.config import config

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024  # keeps responses under Discord's 2000-char limit
MAX_HISTORY_MESSAGES = 20  # sliding window — 10 turns

_BASE_SYSTEM_PROMPT = """You are Byte, a friendly personal health and fitness AI assistant living in a Discord server.

You specialize in:
- Recipe suggestions and meal planning tailored to dietary restrictions and allergies
- Personalized workout planning and fitness advice
- Grocery list generation from meal plans
- General nutrition, diet, and health guidance
- Tracking and remembering favorite recipes, past workouts, and food/meal logs (via slash commands)

Formatting rules (important — you live inside Discord):
- Keep responses under 1900 characters
- Use **bold** for headers and emphasis
- Use bullet points (-) for lists
- Use short paragraphs — avoid walls of text
- Do NOT use markdown H1/H2/H3 headers (#, ##, ###) — they don't render in Discord
- For recipes: always include ingredients list, brief instructions, and approximate macros per serving
- For workouts: always include exercise name, sets x reps, and rest time

When a user asks you to "save" something, remind them to use the appropriate slash command (e.g. /save_recipe, /log_food, /log_workout).
When a user mentions eating something or asks you to log food, remind them to use /log_food.
Never claim to perform actions you can't do (web browsing, accessing external APIs).
Be warm, encouraging, and concise.
"""


def _build_system_prompt(profile: dict | None) -> str:
    if not profile:
        return _BASE_SYSTEM_PROMPT

    sections = []

    if profile.get("preferred_diet") and profile["preferred_diet"] != "standard":
        sections.append(f"Preferred diet: {profile['preferred_diet']}")

    if profile.get("dietary_restrictions"):
        restrictions = ", ".join(profile["dietary_restrictions"])
        sections.append(f"Dietary restrictions: {restrictions}")

    if profile.get("allergies"):
        allergies = ", ".join(profile["allergies"])
        sections.append(
            f"ALLERGIES (CRITICAL — never include these in any recipe or meal plan): {allergies}"
        )

    if profile.get("fitness_goals"):
        sections.append(f"Fitness goals: {profile['fitness_goals']}")

    if profile.get("activity_level"):
        sections.append(f"Activity level: {profile['activity_level']}")

    if not sections:
        return _BASE_SYSTEM_PROMPT

    profile_block = "\n".join(f"- {s}" for s in sections)
    return f"{_BASE_SYSTEM_PROMPT}\n\nUser profile:\n{profile_block}"


class ClaudeClient:
    def __init__(self):
        self._client = AsyncAnthropic(api_key=config.anthropic_api_key)

    async def chat(
        self,
        user_message: str,
        history: list[dict],
        profile: dict | None = None,
    ) -> str:
        """
        General-purpose chat. Called by the on_message handler for freeform conversation.

        Args:
            user_message: The new message from the user.
            history: Existing conversation turns [{role, content}, ...].
            profile: User profile dict from DynamoDB (optional).

        Returns:
            Assistant response text.
        """
        system = _build_system_prompt(profile)

        messages = list(history)
        messages.append({"role": "user", "content": user_message})

        # Apply sliding window
        if len(messages) > MAX_HISTORY_MESSAGES:
            messages = messages[-MAX_HISTORY_MESSAGES:]

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    async def generate_recipe(
        self,
        diet: str,
        cuisine: str | None = None,
        restrictions: str | None = None,
        profile: dict | None = None,
    ) -> str:
        parts = [f"Generate a single {diet} recipe"]
        if cuisine:
            parts.append(f"in {cuisine} style")
        if restrictions:
            parts.append(f"with these additional restrictions for this request: {restrictions}")
        parts.append(
            "Include: recipe name, ingredients list with quantities, "
            "step-by-step instructions, and approximate macros per serving. "
            "Keep total response under 1800 characters."
        )
        prompt = " ".join(parts) + "."

        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def generate_meal_plan(
        self,
        diet: str,
        days: int = 7,
        calories: int | None = None,
        profile: dict | None = None,
    ) -> str:
        calorie_clause = f" targeting {calories} calories/day" if calories else ""
        prompt = (
            f"Generate a {days}-day {diet} meal plan{calorie_clause}. "
            f"Format each day as: **Day N** — Breakfast: X | Lunch: Y | Dinner: Z | Snack: W. "
            f"Keep it concise — one line per day. Total response under 1800 characters."
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def generate_grocery_list(
        self,
        meal_plan_text: str,
        servings: int = 1,
        profile: dict | None = None,
    ) -> str:
        serving_clause = f" for {servings} people" if servings > 1 else ""
        prompt = (
            f"From this meal plan, generate a consolidated grocery list{serving_clause} "
            f"grouped by category (Produce, Proteins, Dairy, Pantry, Other). "
            f"Remove duplicates and combine quantities. Keep under 1800 characters.\n\n"
            f"Meal plan:\n{meal_plan_text}"
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def generate_workout(
        self,
        workout_type: str,
        duration_min: int = 45,
        equipment: str | None = None,
        profile: dict | None = None,
    ) -> str:
        equip_clause = f" using {equipment}" if equipment else " with no equipment"
        prompt = (
            f"Generate a {duration_min}-minute {workout_type} workout{equip_clause}. "
            f"For each exercise include: exercise name, sets x reps (or duration), rest time. "
            f"Add a brief warm-up and cool-down section. Keep total under 1800 characters."
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def analyze_workout_history(
        self,
        workouts: list[dict],
        profile: dict | None = None,
    ) -> str:
        if not workouts:
            return "No workout history found. Log your first workout with /log_workout!"

        summary_lines = []
        for w in workouts[:10]:
            exercises = ", ".join(w.get("exercises", [])) or "not logged"
            summary_lines.append(
                f"- {w.get('logged_at', '')[:10]}: {w.get('workout_type', '?')} "
                f"{w.get('duration_min', '?')} min — {exercises}"
            )
        summary = "\n".join(summary_lines)

        prompt = (
            f"Here are my recent workouts:\n{summary}\n\n"
            f"Give me a brief analysis: patterns you notice, muscle groups I might be neglecting, "
            f"and one concrete suggestion to improve my training. Keep it under 400 words."
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def analyze_food_log(
        self,
        entries: list[dict],
        days: int = 7,
        profile: dict | None = None,
    ) -> str:
        if not entries:
            return "No food log entries found for the requested period. Start logging with `/log_food`!"

        summary_lines = []
        for e in entries[:20]:
            foods = ", ".join(e.get("foods", [])) or "not specified"
            cal_part = f" — {e['calories']} cal" if e.get("calories") is not None else ""
            macro_parts = []
            if e.get("protein_g") is not None:
                macro_parts.append(f"P:{e['protein_g']}g")
            if e.get("carbs_g") is not None:
                macro_parts.append(f"C:{e['carbs_g']}g")
            if e.get("fat_g") is not None:
                macro_parts.append(f"F:{e['fat_g']}g")
            macro_str = " " + " ".join(macro_parts) if macro_parts else ""
            summary_lines.append(
                f"- {e.get('logged_at', '')[:10]} {e.get('meal_type', '?')}: "
                f"{foods}{cal_part}{macro_str}"
            )
        summary = "\n".join(summary_lines)

        prompt = (
            f"Here is my food log for the past {days} day(s):\n{summary}\n\n"
            f"Please provide a brief nutritional analysis: patterns you notice, "
            f"any nutrients I might be under- or over-consuming, whether my eating "
            f"aligns with my fitness goals, and one concrete dietary suggestion. "
            f"Keep it under 400 words."
        )
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_build_system_prompt(profile),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


# Module-level singleton
claude = ClaudeClient()
