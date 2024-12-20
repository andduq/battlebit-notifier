import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
import asyncio
import logging.handlers
from aiohttp import ClientSession
from bot import CustomBot
import sys

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

async def main():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    logfile_handler = logging.handlers.RotatingFileHandler(
        filename="discord.log",
        encoding="utf-8",
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,  # Rotate through 5 files
    )
    console_handler = logging.StreamHandler(sys.stdout)

    dt_fmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
    )

    logfile_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(logfile_handler)
    logger.addHandler(console_handler)
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guild_reactions = True
    intents.guilds = True

    async with ClientSession() as session:
        bot = CustomBot(
            commands.when_mentioned_or("!"),
            intents=intents,
            web_session=session,
        )

        await bot.start(TOKEN)

asyncio.run(main())
