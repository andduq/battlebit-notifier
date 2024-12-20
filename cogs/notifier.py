import discord
from discord.ext import commands
import logging
from bot import CustomBot

log = logging.getLogger("Notifier")

class Notifier(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.notification_channel: int = None

    @commands.Cog.listener()
    async def on_ready(self):
        for channel in self.bot.get_all_channels():
            if channel.name == "bot-notifications":
                self.notification_channel = channel.id
                #clear the channel
                break

        channel = self.bot.get_channel(self.notification_channel)
        async for message in channel.history(limit=200):
            await message.delete()
            

    @commands.Cog.listener()
    async def on_1s1k_rank_change(self, previous_rank: int, new_rank: int):
        log.info(f"1s1k rank changed from {previous_rank} to {new_rank}")

        if self.notification_channel:
            try:
                channel = self.bot.get_channel(self.notification_channel)
                rank_difference = abs(new_rank - previous_rank)
                improved = new_rank < previous_rank
                direction = "⬆️" if improved else "⬇️"
                change_str = f"{direction} `{'+' if improved else '-'}{rank_difference}`"
                embed = discord.Embed(
                    title="🌟 Global Rank Update 🌟",
                    description=(
                        f"@everyone 1S1K's global rank has **{'improved' if improved else 'dropped'}**!"
                    ),
                    color=discord.Color.green() if improved else discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.add_field(
                    name="Previous Rank",
                    value=f"`#{previous_rank}`",
                    inline=True
                )
                embed.add_field(
                    name="New Rank",
                    value=f"`#{new_rank}`",
                    inline=True
                )
                embed.add_field(
                    name="Change",
                    value=change_str,
                    inline=False
                )

                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(everyone=True))
                    
            except Exception as e:
                log.warning(f"Cannot send notification to channel {self.notification_channel}. Exception: {e}")
    
    
    @commands.Cog.listener()
    async def on_server_match(self, embed: discord.Embed, file: discord.File | None):
        try:
            await self.bot.get_channel(self.notification_channel).send(embed=embed, file=file)
        except Exception as e:
            log.warning(f"Cannot send notification to channel {self.notification_channel}. Exception: {e}")


def setup(bot : CustomBot) -> None:
    bot.add_cog(Notifier(bot))