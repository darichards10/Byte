import discord
from discord import app_commands
from discord.ext import commands

from bot import db


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="set_reminder", description="Set a recurring health or fitness reminder")
    async def set_reminder(
        self,
        interaction: discord.Interaction,
        message: str,
        schedule: str,
    ):
        """
        Args:
            message: The reminder message to send (e.g. "Time to drink water!")
            schedule: Human-readable schedule (e.g. "daily", "weekly", "every Monday")
                      Stored as-is; the Lambda dispatcher interprets this.
        """
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        channel_id = str(interaction.channel.id)

        reminder_id = db.save_reminder(
            user_id=user_id,
            message=message,
            channel_id=channel_id,
            schedule=schedule,
        )

        await interaction.followup.send(
            f"Reminder set! (ID: `{reminder_id}`)\n"
            f"**Message:** {message}\n"
            f"**Schedule:** {schedule}\n\n"
            f"Note: Reminders are sent by the weekly EventBridge trigger. "
            f"For custom schedules, update the Lambda rule in AWS.",
            ephemeral=True,
        )

    @app_commands.command(name="list_reminders", description="View your active reminders")
    async def list_reminders(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reminders = db.get_reminders(str(interaction.user.id))

        if not reminders:
            await interaction.followup.send(
                "No reminders set. Use `/set_reminder` to create one!",
                ephemeral=True,
            )
            return

        lines = ["**Your Reminders:**\n"]
        for r in reminders:
            status = "active" if r.get("enabled") else "paused"
            lines.append(
                f"- `{r['reminder_id']}` — {r['message']} | {r['schedule']} | {status}"
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="delete_reminder", description="Delete a reminder by ID")
    async def delete_reminder(self, interaction: discord.Interaction, reminder_id: str):
        await interaction.response.defer(ephemeral=True)
        db.delete_reminder(str(interaction.user.id), reminder_id)
        await interaction.followup.send(
            f"Reminder `{reminder_id}` deleted.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
