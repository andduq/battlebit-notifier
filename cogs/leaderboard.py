import json
import discord
from discord.ext import commands, tasks
from discord.commands import option
from typing import List
from bot import CustomBot
from datetime import datetime
from table2ascii import table2ascii as t2a, PresetStyle
import os
import logging
from typing import Tuple
from firestore_helper import get_firestore_client
from fuzzywuzzy import fuzz

LEADERBOARD_URL = "https://publicapi.battlebit.cloud/Leaderboard/Get"
log = logging.getLogger("Leaderboard")

class Leaderboard(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot : CustomBot = bot
        self.last_fetch: datetime
        self.last_cached_leaderboard: List[dict] = None
        self.cached_leaderboard: List[dict] = None
        self.db = get_firestore_client()
        self.notification_channel : discord.TextChannel = None

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("Leaderboard cog is ready")
        self.notification_channel = await self.bot.get_notification_channel()

        if not self.db.collection("clan").document("statistics").get().to_dict().get("global_rank"):
            self.db.collection("clan").document("statistics").set({"global_rank": 0})
        
        self.fetch_leaderboard_loop.start()
        
        
    @commands.guild_only()
    @commands.slash_command(
        name="topclans",
        description=f"Show the top n clans with more than min_players players",
    )
    async def leaderboard(
        self, ctx: discord.ApplicationContext, n: int = 10, min_players: int = 3
    ) -> None:
        top_clans = self.cached_leaderboard[0]["TopClans"]

        cleaned_data = [
            clan for clan in top_clans if int(clan["MaxPlayers"]) > min_players
        ]
        
        sorted_data = sorted(
            cleaned_data,
            key=lambda x: int(x["XP"]) / int(x["MaxPlayers"]),
            reverse=True,
        )

        max_n = min(n, len(sorted_data))
        data = []
        for i, clan in enumerate(sorted_data[:max_n]):
            xp_per_player = int(clan["XP"]) / int(clan["MaxPlayers"])
            arrow, prev_xp_per_player = self.get_arrow_and_prev_xp_per_player(clan)

            prev_score_str = ""
            if prev_xp_per_player != 0 and prev_xp_per_player != xp_per_player:
                prev_score_str = (
                    f"({self.format_number(prev_xp_per_player)} previously)"
                )
                if arrow != "":
                    prev_score_str = f"{prev_score_str}"

            data.append(
                [
                    f"{i+1}",
                    f"{clan['Clan']} {arrow}",
                    clan["Tag"],
                    self.format_number(clan["XP"]),
                    clan["MaxPlayers"],
                    f"{self.format_number(xp_per_player)} {prev_score_str}",
                ]
            )

        table = t2a(
            header=["Rank", "Clan", "Tag", "Total XP", "Players", "XP/player"],
            body=data,
            style=PresetStyle.thin_compact,
        )

        message = f"```{table}```"

        try:
            await ctx.send_response(message)
        except discord.HTTPException:
            if os.path.exists("leaderboard.txt"):
                os.remove("leaderboard.txt")
            with open("leaderboard.txt", "w", encoding="utf-8-sig") as f:
                f.write(message)
            with open("leaderboard.txt", "rb") as f:
                await ctx.send_response(
                    "Leaderboard is too long, sending as a file",
                    file=discord.File(f, "leaderboard.txt"))
    def get_arrow_and_prev_xp_per_player(self, clan) -> Tuple[str, float]:
        prev_xp_per_player = 0
        if self.last_cached_leaderboard is not None:
            for old_clan in self.last_cached_leaderboard[0]["TopClans"]:
                if old_clan["Tag"] == clan["Tag"]:
                    prev_xp_per_player = int(old_clan["XP"]) / int(
                        old_clan["MaxPlayers"]
                    )
                    if int(clan["XP"]) > int(old_clan["XP"]):
                        return "▲", prev_xp_per_player
        return "", prev_xp_per_player

    def format_number(self, num):
        return f"{float(num):,.2f}"

    @tasks.loop(seconds=5)
    async def fetch_leaderboard_loop(self) -> None:

        log.info("Fetching leaderboard...")
        async with self.bot.web_session.get(LEADERBOARD_URL) as response:
            if response.status != 200:
                log.error(f"Failed to fetch leaderboard: {response.status}")
                return

            leaderboard = json.loads(await response.text(encoding="utf-8-sig"))

            if self.cached_leaderboard is None:
                self.last_cached_leaderboard = self.cached_leaderboard = leaderboard
            else:
                self.last_cached_leaderboard = self.cached_leaderboard
                self.cached_leaderboard = leaderboard

            self.last_fetch = datetime.now()

        top_clans = leaderboard[0]["TopClans"]
        previous_rank = self.db.collection("clan").document("statistics").get().to_dict().get("global_rank", 0)
        for rank, clan in enumerate(top_clans):
            if clan["Tag"] == "1S1K":
                new_rank = rank + 1
                if new_rank != previous_rank:
                    self.db.collection("clan").document("statistics").set({"global_rank": new_rank})
                    try:
                        rank_difference = abs(new_rank - previous_rank)
                        improved = new_rank < previous_rank
                        direction = "⬆️" if improved else "⬇️"
                        change_str = f"{direction} `{'+' if improved else '-'}{rank_difference}`"
                        embed = discord.Embed(
                            title="🌟 Global Rank Update 🌟",
                            description=(
                                f"1S1K's global rank has **{'improved' if improved else 'dropped'}**!"
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

                        await self.notification_channel.send(":loudspeaker: • @everyone", embed=embed)
                            
                    except Exception as e:
                        log.warning(f"Cannot send notification to channel {self.notification_channel}. Exception: {e}")

    @commands.guild_only()
    @commands.slash_command(
        name="leaderboard_search",
        description="Search for an entry in the leaderboard",
    )
    @option(
        name="category",
        description="The category to search in",
        type=str,
        required=True,
        autocomplete=discord.utils.basic_autocomplete(["TopClans", "MostXP", "MostHeals", "MostRevives", "MostVehiclesDestroyed", "MostVehicleRepairs", "MostRoadkills", "MostLongestKill", "MostObjectivesComplete", "MostKills"])
    )
    async def leaderboard_search(
        self, 
        ctx: discord.ApplicationContext, 
        category: str, 
        query: str, 
        max_results: int = 10, 
        min_similarity: float = 0.6 
    ) -> None:
        await ctx.defer()
        
        try:
            if not self.cached_leaderboard:
                await ctx.send_followup("Leaderboard data not available yet. Please try again in a few seconds.")
                return

            category_index = next((i for i, item in enumerate(self.cached_leaderboard) 
                                 if list(item.keys())[0] == category), None)
            
            if category_index is None:
                await ctx.send_followup(f"Invalid category: {category}")
                return

            if category == "TopClans":
                await self._search_clans(ctx, query, max_results, min_similarity)
            else:
                await self._search_players(ctx, category, query, max_results, min_similarity)

        except Exception as e:
            log.error(f"Error in leaderboard search: {e}")
            await ctx.send_followup("An error occurred while searching the leaderboard.")

    async def _search_clans(self, ctx, query: str, max_results: int, min_similarity: float) -> None:
        clans = self.cached_leaderboard[0]["TopClans"]
        hits = []
        
        for i, clan in enumerate(clans):
            clan_similarity = fuzz.token_set_ratio(query.lower(), clan["Clan"].lower()) / 100
            tag_similarity = fuzz.token_set_ratio(query.lower(), clan["Tag"].lower()) / 100
            max_similarity = max(clan_similarity, tag_similarity)
            
            if max_similarity >= min_similarity:
                xp_per_player = int(clan["XP"]) / int(clan["MaxPlayers"])
                hits.append({
                    "similarity": max_similarity,
                    "rank": i + 1,
                    "clan": clan["Clan"],
                    "tag": clan["Tag"],
                    "xp": self.format_number(int(clan["XP"])),
                    "players": clan["MaxPlayers"],
                    "xp_per_player": self.format_number(xp_per_player)
                })
        
        hits.sort(key=lambda x: x["similarity"], reverse=True)
        hits = hits[:max_results]
        
        if not hits:
            await ctx.send_followup(f"No clans found matching '{query}' with similarity >= {min_similarity:.2f}")
            return

        header = ["Rank", "Clan", "Tag", "Total XP", "Players", "XP/player", "Match"]
        data = [[
            str(hit["rank"]),
            hit["clan"],
            hit["tag"],
            hit["xp"],
            str(hit["players"]),
            hit["xp_per_player"],
            f"{hit['similarity']:.2f}"
        ] for hit in hits]

        table = t2a(header=header, body=data, style=PresetStyle.thin_compact)
        await ctx.send_followup(f"```\nSearch results for '{query}' in clans:\n{table}```")

    async def _search_players(self, ctx, category: str, query: str, max_results: int, min_similarity: float) -> None:
        players = next(item[category] for item in self.cached_leaderboard if category in item)
        hits = []
        
        for i, player in enumerate(players):
            similarity = fuzz.token_set_ratio(query.lower(), player["Name"].lower()) / 100
            if similarity >= min_similarity:
                hits.append({
                    "similarity": similarity,
                    "rank": i + 1,
                    "name": player["Name"],
                    "value": self.format_number(float(player["Value"]))
                })
        
        hits.sort(key=lambda x: x["similarity"], reverse=True)
        hits = hits[:max_results]
        
        if not hits:
            await ctx.send_followup(f"No players found matching '{query}' with similarity >= {min_similarity:.2f}") 
            return

        header = ["Rank", "Name", "Value", "Match"]
        data = [[
            str(hit["rank"]), 
            hit["name"], 
            hit["value"],
            f"{hit['similarity']:.2f}"
        ] for hit in hits]
        
        table = t2a(header=header, body=data, style=PresetStyle.thin_compact)
        await ctx.send_followup(f"```\nSearch results for '{query}' in {category}:\n{table}```")

def setup(bot : CustomBot) -> None:
    bot.add_cog(Leaderboard(bot))