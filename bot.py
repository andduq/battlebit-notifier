from discord.ext import commands
from aiohttp import ClientSession
from typing import Optional
import discord

class CustomBot(commands.Bot):
    web_session: ClientSession = None
    notification_channel: discord.TextChannel = None

    def __init__(
        self,
        *args,
        web_session: ClientSession,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.web_session = web_session
        cogs_list = [
            'leaderboard',
            'translator',
            'notifier',
            'profile-creator',
        ]

        for cog in cogs_list:
            self.load_extension(f'cogs.{cog}')


    async def get_notification_channel(self) -> discord.TextChannel:
        if self.notification_channel:
            return self.notification_channel
        
        await self.wait_until_ready()
        
        for channel in self.get_all_channels():
            if channel.name == "bot-notifications":
                self.notification_channel = channel
                return channel