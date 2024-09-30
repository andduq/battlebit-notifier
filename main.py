import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncio
import logging.handlers
from typing import List, Optional
from aiohttp import ClientSession
from bot import CustomBot

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")




async def main():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        filename='discord.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,  # Rotate through 5 files
    )
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    intents = discord.Intents.default()
    intents.message_content = True

    async with ClientSession() as session:
        bot = CustomBot(
                commands.when_mentioned_or('!'),
                intents=intents,
                web_session=session,
                testing_guild_id=int(GUILD_ID))

        await bot.start(TOKEN)

asyncio.run(main())