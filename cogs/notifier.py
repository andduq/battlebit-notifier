import asyncio
import aiohttp
from discord.ext import commands
import discord
from typing import Dict, List
import os
import logging
from filter import Filter
from firestore_helper import get_firestore_client
import constants
import re
from bot import CustomBot

DEBUG_WEBHOOK_URL = os.getenv("DEBUG_WEBHOOK_URL")
SERVER_LIST_URL = "https://publicapi.battlebit.cloud/Servers/GetServerList"
MAP_ICONS_URL = "https://cdn.gametools.network/maps/battlebit/"
SERVER_FETCH_RETRY_INTERVAL = 5
SERVER_FETCH_RETRY_COUNT = 3

log = logging.getLogger("Notifier")


class Notifier(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot
        self.server_list: List[dict] = []  # List of server data
        self.session: aiohttp.ClientSession = bot.web_session
        self.sent_notifications: Dict[int, set[int]] = {}  # user_id -> set of server ids
        self.user_filters: Dict[str, Dict[str, List[Filter]]] = {}  # guild_id -> user_id -> list of Filters
        self.db = get_firestore_client()

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Bot is ready.")
        await self.preload_filters()
        await self.fetch_map_icons()
        asyncio.create_task(self.fetch_and_notify())

    @commands.guild_only()
    @discord.slash_command(name="start_notify", description="Get notified for matching servers.")
    async def start_notify(self, ctx: discord.ApplicationContext, map: str, region: str = None,
                           min_players: int = None, max_players: int = None, gamemode: str = None):
        if not self._validate_filter_input(ctx, map, region, gamemode):
            return

        filter_obj = Filter(min_players=min_players, max_players=max_players, map=map, region=region, game_mode=gamemode)
        self.add_filter(ctx, filter_obj)
        await ctx.send_response("Filter has been added.", ephemeral=True)

    @commands.guild_only()
    @discord.slash_command(name="stop_notify", description="Stop notifications for a filter.")
    async def stop_notify(self, ctx: discord.ApplicationContext, filter_index: int):
        self.remove_filter(ctx.author, ctx.guild_id, filter_index)
        await ctx.send_response("Filter has been removed.", ephemeral=True)

    @commands.guild_only()
    @discord.slash_command(name="list_filters", description="List your active filters.")
    async def list_filters(self, ctx: discord.ApplicationContext):
        filters = self.get_filters_for_user(ctx.author, ctx.guild_id)
        if not filters:
            await ctx.send_response("No filters set.", ephemeral=True)
            return
        filters_str = "\n".join([f"{i}: {filter}" for i, filter in enumerate(filters)])
        await ctx.send_response(f"Filters:\n{filters_str}", ephemeral=True)

    @commands.guild_only()
    @discord.slash_command(name="clear_filters", description="Clear all your filters.")
    async def clear_filters(self, ctx: discord.ApplicationContext):
        self.clear_filters(ctx.author, ctx.guild_id)
        await ctx.send_response("Filters have been cleared.", ephemeral=True)

    async def fetch_map_icons(self):
        """Download missing map icons."""
        map_icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_icons")
        os.makedirs(map_icons_dir, exist_ok=True)

        missing_maps = [map for map in constants.MAPS if not os.path.exists(f"{map_icons_dir}/{map}.jpg")]
        await asyncio.gather(*(self.download_map_icon(map) for map in missing_maps))

    async def download_map_icon(self, map: str):
        """Download a single map icon."""
        url = f"{MAP_ICONS_URL}{map}.jpg"
        async with self.session.get(url) as response:
            if response.status == 200:
                with open(f"map_icons/{map}.jpg", "wb") as f:
                    f.write(await response.read())
                log.info(f"Downloaded icon for {map}")
            else:
                log.warning(f"Failed to download icon for {map} (status: {response.status})")

    async def fetch_server_list(self):
        """Fetch the server list from the API."""
        for attempt in range(SERVER_FETCH_RETRY_COUNT):
            try:
                async with self.session.get(SERVER_LIST_URL) as response:
                    self.server_list = await response.json(content_type=None, encoding="utf-8-sig")
                    log.info(f"Fetched {len(self.server_list)} servers (status: {response.status})")
                    return
            except Exception as e:
                log.warning(f"Failed to fetch servers (attempt {attempt + 1}): {e}")
                await asyncio.sleep(SERVER_FETCH_RETRY_INTERVAL)
        
        log.error("Max retries reached. Could not fetch server list.")
        if DEBUG_WEBHOOK_URL:
            async with self.session.post(DEBUG_WEBHOOK_URL, json={"content": f"Failed to fetch server list after {SERVER_FETCH_RETRY_COUNT} retries."}) as response:
                log.info(f"Sent message to debug webhook, status: {response.status}")

    async def fetch_and_notify(self):
        """Fetch server list periodically and notify users of matches."""
        while True:
            await self.fetch_server_list()
            await self.notify_users()
            await asyncio.sleep(5)

    async def notify_users(self):
        """Notify users about matching servers."""
        for server in self.server_list:
            server_id = hash(f"{server['Name']}{server['Map']}")
            server["Id"] = server_id

            for guild_id, user_filters in self.user_filters.items():
                for user_id, filters in user_filters.items():
                    for filter_obj in filters:
                        if filter_obj.apply(server) and server_id not in self.sent_notifications.setdefault(int(user_id), set()):
                            user = await self.bot.fetch_user(user_id)
                            await self.send_notification(user, server)
                            self.sent_notifications[int(user_id)].add(server_id)
                            
        # Create a new set that contains every server ID in the current server list
        current_server_ids = {server["Id"] for server in self.server_list}
        # Update the sent_notifications dictionary to only include server IDs that are still in the server list (removing invalid server IDs due to map change)
        for user, sent_ids in self.sent_notifications.items():
            still_valid_servers = sent_ids & current_server_ids
            self.sent_notifications[user] = still_valid_servers

    async def send_notification(self, user: discord.User, server: dict):
        """Send a DM to the user with server details."""
        formatted_server_name = self.format_server_name(server["Name"])
        region_flag = self.get_region_flag(server["Region"])
        queue_str = f"(+{server['QueuePlayers']})" if server["QueuePlayers"] > 0 else ""
        embed = discord.Embed(
            title="Server Match Found",
            description=f"<@{user.id}>, a server has been found matching your criterias.",
            color=discord.Color.yellow(),
        )
        embed.add_field(
            name=formatted_server_name,
            value=f"**Players**: {server['Players']}{queue_str}/{server['MaxPlayers']}\n**Map**: {server['Map']}\n**Region**: {region_flag}\n**Gamemode**: {server['Gamemode']}",
            inline=False,
        )
        main_dir = os.path.dirname(os.path.abspath(__file__))
        map_icon_path = os.path.join(main_dir, "map_icons", f"{server['Map']}.jpg")
        if os.path.exists(map_icon_path):
            file = discord.File(map_icon_path, filename=f"{server['Map']}.jpg")
            embed.set_thumbnail(url=f"attachment://{server['Map']}.jpg")

        embed.timestamp = discord.utils.utcnow()

        try:
            await user.send(embed=embed, file=file)
            log.info(f"Notification sent to {user.name} for server {server['Name']}.")
        except Exception as e:
            log.warning(f"Cannot send DM to {user.name}. Exception: {e}")	

    def format_server_name(self, server_name: str) -> str:
        """Sanitize server name to exclude URLs."""
        return re.sub(r"(https?://\S+)", r"<\1>", server_name)

    def get_region_flag(self, region: str) -> str:
        region_flags = {
            "America_Central": ":flag_us:",
            "Europe_Central": ":flag_eu:",
            "Asia_Central": ":flag_white:",
            "Brazil_Central": ":flag_br:",
            "Australia_Central": ":flag_au:",
            "Japan_Central": ":flag_jp:"
        }
        return region_flags.get(region, ":question:")

    async def preload_filters(self):
        """Load filters from Firestore."""
        guilds_ref = self.db.collection("guilds")
        guilds = guilds_ref.stream()


        total_guilds = 0
        total_users = 0
        total_filters = 0
        for guild_doc in guilds:
            total_guilds += 1
            guild_id = guild_doc.id
            users_ref = guilds_ref.document(guild_id).collection("users")
            users = users_ref.stream()

            for user_doc in users:
                total_users += 1
                user_id = user_doc.id
                user_data = user_doc.to_dict()
                filters = [Filter.from_json(f) for f in user_data.get("filters", [])]
                total_filters += len(filters)
                if guild_id not in self.user_filters:
                    self.user_filters[guild_id] = {}
                self.user_filters[guild_id][user_id] = filters

        log.info(f"Filters preloaded. Guilds: {total_guilds}, Users: {total_users}, Filters: {total_filters}")

    def _validate_filter_input(self, ctx: discord.ApplicationContext, map: str, region: str = None, gamemode: str = None) -> bool:
        if map not in constants.MAPS:
            ctx.send_response(f"Invalid map. Valid maps: {', '.join(constants.MAPS)}", ephemeral=True)
            return False
        if region and region not in constants.REGIONS:
            ctx.send_response(f"Invalid region. Valid regions: {', '.join(constants.REGIONS)}", ephemeral=True)
            return False
        if gamemode and gamemode not in constants.GAMEMODES:
            ctx.send_response(f"Invalid gamemode. Valid gamemodes: {', '.join(constants.GAMEMODES)}", ephemeral=True)
            return False
        return True

    def add_filter(self, ctx: discord.ApplicationContext, filter_obj: Filter):
        """Add a filter for a user."""
        guild_id, user_id = str(ctx.guild_id), str(ctx.author.id)

        self.user_filters.setdefault(guild_id, {}).setdefault(user_id, []).append(filter_obj)
        user_ref = self.db.collection("guilds").document(guild_id).collection("users").document(user_id)
        user_ref.set({
            "username": ctx.author.name,
            "filters": [f.to_json() for f in self.user_filters[guild_id][user_id]]
        }, merge=True)
        log.info(f"Filter added for user {ctx.author.name} in guild {ctx.guild.name}.")

    def remove_filter(self, user: discord.User, guild_id: int, filter_index: int):
        """Remove a filter for a user."""
        guild_id, user_id = str(guild_id), str(user.id)

        if guild_id in self.user_filters and user_id in self.user_filters[guild_id]:
            try:
                del self.user_filters[guild_id][user_id][filter_index]
                user_ref = self.db.collection("guilds").document(guild_id).collection("users").document(user_id)
                user_ref.set({
                    "filters": [f.to_json() for f in self.user_filters[guild_id][user_id]]
                }, merge=True)
                log.info(f"Filter {filter_index} removed for {user.name}.")
            except IndexError:
                log.warning(f"Invalid filter index {filter_index} for user {user.name}.")

    def clear_filters(self, user: discord.User, guild_id: int):
        """Clear all filters for a user."""
        guild_id, user_id = str(guild_id), str(user.id)

        if guild_id in self.user_filters:
            self.user_filters[guild_id].pop(user_id, None)
        user_ref = self.db.collection("guilds").document(guild_id).collection("users").document(user_id)
        user_ref.delete()
        log.info(f"All filters cleared for user {user.name}.")

    def get_filters_for_user(self, user: discord.User, guild_id: int) -> List[Filter]:
        """Retrieve filters for a user."""
        return self.user_filters.get(str(guild_id), {}).get(str(user.id), [])

def setup(bot):
    bot.add_cog(Notifier(bot))
