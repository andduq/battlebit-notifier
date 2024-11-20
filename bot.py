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
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.web_session = web_session
        cogs_list = [
            'notifier',
            'leaderboard',
            'translator',
            'guildevents',
        ]

        for cog in cogs_list:
            self.load_extension(f'cogs.{cog}')