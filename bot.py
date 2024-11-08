import discord
from discord.ext import commands
from aiohttp import ClientSession
from typing import Optional

class CustomBot(commands.Bot):
    web_session: ClientSession = None
    def __init__(
        self,
        *args,
        web_session: ClientSession,
        testing_guild_id: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.web_session = web_session
        self.testing_guild_id = testing_guild_id
        cogs_list = [
            'notifier',
            'leaderboard',
            'translator',
        ]

        for cog in cogs_list:
            self.load_extension(f'cogs.{cog}')