import json
import requests
import discord
from discord.ext import commands
import time
from typing import List
import aiohttp
from bot import CustomBot
from datetime import datetime
from table2ascii import table2ascii as t2a, PresetStyle

LEADERBOARD_URL = "https://publicapi.battlebit.cloud/Leaderboard/Get"

class Leaderboard(commands.Cog):
    bot: CustomBot
    last_fetch: datetime
    last_cached_leaderboard: List[dict] = None
    cached_leaderboard: List[dict] = None

    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.last_fetch = datetime.now()

    @commands.guild_only()
    @commands.slash_command(
        name="topclans",
        description=f"Show the top n clans with more than min_players players")
    async def leaderboard(self, ctx: discord.ApplicationContext, n: int = 10, min_players: int = 3):
        await self.fetch_leaderboard()
        top_clans = self.cached_leaderboard[0]["TopClans"]

        cleaned_data = [clan for clan in top_clans if int(clan["MaxPlayers"]) > min_players]
        sorted_data = sorted(cleaned_data, key=lambda x: int(x["XP"]) / int(x['MaxPlayers']), reverse=True)

        max_n = min(n, len(sorted_data))
        data = []
        for i, clan in enumerate(sorted_data[:max_n]):
            xp_per_player = int(clan['XP']) / int(clan['MaxPlayers'])
            arrow, prev_xp_per_player = self.get_arrow_and_prev_xp_per_player(clan)

            prev_score_str = ""
            if prev_xp_per_player != 0 and prev_xp_per_player != xp_per_player:
                prev_score_str = f"({self.format_number(prev_xp_per_player)} previously)"
                if arrow != "":
                    prev_score_str = f"**{prev_score_str}**"

            data.append([f"{i+1}", f"{clan['Clan']} {arrow}", clan['Tag'], self.format_number(clan['XP']), clan['MaxPlayers'], f"{self.format_number(xp_per_player)} {prev_score_str}"])

        table = t2a(
            header=["Rank", "Clan", "Tag", "Total XP", "Players", "XP/player"],
            body=data,
            style=PresetStyle.thin_compact
        )

        message = f"```{table}\nLast updated {time.strftime('%Y-%m-%d %H:%M:%S', self.last_fetch.timetuple())}```"

        try:
            await ctx.send_response(message, ephemeral=True)
        except discord.HTTPException:
            with open("leaderboard.txt", "w", encoding="utf-8-sig") as f:
                f.write(table)
            with open("leaderboard.txt", "rb") as f:
                await ctx.send_response("Leaderboard is too long, sending as a file", file=discord.File(f, "leaderboard.txt"), ephemeral=True)



    def get_arrow_and_prev_xp_per_player(self, clan):
        prev_xp_per_player = 0
        if self.last_cached_leaderboard is not None:
            for old_clan in self.last_cached_leaderboard[0]["TopClans"]:
                if old_clan["Tag"] == clan["Tag"]:
                    prev_xp_per_player = int(old_clan['XP']) / int(old_clan['MaxPlayers'])
                    if int(clan["XP"]) > int(old_clan["XP"]):
                        return "▲", prev_xp_per_player
                    elif int(clan["XP"]) < int(old_clan["XP"]):
                        return "▼", prev_xp_per_player
        return "", prev_xp_per_player

    def format_number(self, num):
        return f"{float(num):,.2f}"

    async def fetch_leaderboard(self):
        if self.cached_leaderboard is not None and (datetime.now() - self.last_fetch).seconds < 60:
            return

        async with self.bot.web_session.get(LEADERBOARD_URL) as response:
            if response.status != 200:
                print(f"Failed to fetch leaderboard: {response.status}")
                return

            leaderboard = json.loads(await response.text(encoding='utf-8-sig'))

            if self.last_cached_leaderboard is None:
                self.last_cached_leaderboard = leaderboard

            self.cached_leaderboard = leaderboard
            self.last_fetch = datetime.now()

def setup(bot):
    bot.add_cog(Leaderboard(bot))