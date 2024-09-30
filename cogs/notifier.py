import asyncio
import aiohttp
from discord.ext import commands
import discord
import re
import json
import os
import constants
import discord
from discord.ext import commands
from filter import Filter

SERVER_LIST_URL = "https://publicapi.battlebit.cloud/Servers/GetServerList"
USER_FILTERS_PATH = "user_filters.json"

class Notifier(commands.Cog):
    server_list = []
    bot: commands.Bot = None
    server_message = None
    session: aiohttp.ClientSession = None
    server_ids: set[int] = set()
    sent_notifications: dict[discord.User, set[int]] = {}  # user -> set of server ids
    user_filters: dict[discord.User, list[Filter]] = {}

    def __init__(self, bot: discord.Client):
        self.bot = bot

    # add listener for on_ready event
    @commands.Cog.listener()
    async def on_ready(self):
        await self.start()
    
    @commands.guild_only()
    @discord.slash_command(
        name="start_notify",
        description=f"Get notified when a server matches the specified filters.")
    async def start_notify(self, ctx: discord.ApplicationContext, map : str, region : str | None, min_players : int | None, max_players : int | None, gamemode : str | None):
        self.add_filter(ctx.author, Filter(min_players=min_players, max_players=max_players, map=map, region=region, game_mode=gamemode))
        await ctx.send_response(
            f"Filter has been added.", ephemeral=True, delete_after=5
        )

    @commands.guild_only()
    @discord.slash_command(
        name="stop_notify",
        description=f"Stop getting notified for the specified filter.")
    async def stop_notify(self, ctx: discord.ApplicationContext, filter_index : int):
        self.remove_filter(ctx.author, filter_index)
        await ctx.send_response(
            f"Filter has been removed.", ephemeral=True, delete_after=5
        )

    @commands.guild_only()
    @discord.slash_command(
        name="list_filters",
        description=f"List all notification filters.")
    async def list_filters(self, ctx: discord.ApplicationContext):
        filters = self.get_filters_for_user(ctx.author)
        if not filters:
            await ctx.send_response(
                f"No filters set.", ephemeral=True, delete_after=5
            )
            return
        filters_str = "\n".join([f"{i}: {filter}" for i, filter in enumerate(filters)])
        await ctx.send_response(
            f"Filters:\n{filters_str}", ephemeral=True, delete_after=30
        )

    @commands.guild_only()
    @discord.slash_command(
        name="clear_filters",
        description=f"Clear all notification filters.")
    async def clear_filters(self, ctx: discord.ApplicationContext):
        self.clear_filters(ctx.author)
        await ctx.send_response(
            f"Filters have been cleared.", ephemeral=True, delete_after=5
        )


    async def fetch_server_list(self) -> None:
        async with self.session.get(SERVER_LIST_URL) as response:
            self.server_list = await response.json(
                content_type=None, encoding="utf-8-sig"
            )
            print(f"Fetched {len(self.server_list)} servers, status: {response.status}")

    def set_user_filters(self, user_filters: dict[discord.User, list[Filter]]) -> None:
        self.user_filters = user_filters

    def get_user_filters(self) -> dict[discord.User, list[Filter]]:
        return self.user_filters

    def format_server_name(self, server_name: str) -> str:
        # Sanitize the server name to prevent embedding links
        url_pattern = re.compile(r"((https?:\/\/)?[^\s.]+\.[\w][^\s]+)")
        return url_pattern.sub(r"\<\g<1>\>", server_name)

    def get_region_flag(self, region: str) -> str:
        region_flags = {
            "America_Central": ":flag_us:",
            "Europe_Central": ":flag_eu:",
            "Asia_Central": ":flag_white:",
            "Brazil_Central": ":flag_br:",
            "Australia_Central": ":flag_au:",
            "Japan_Central": ":flag_jp:",
        }
        return region_flags.get(region, "")

    async def notify_users(self) -> None:
        for server in self.server_list:
            server["Id"] = hash(f"{server['Name']}{server['Map']}")
            for user, filters in self.user_filters.items():
                for filter in filters:
                    if filter.apply(server):
                        # We have a match
                        if server["Id"] not in self.sent_notifications.get(user, set()):
                            # We haven't sent a notification for this server to this user yet
                            await self.send_notification(user, server)
                            self.sent_notifications.setdefault(user, set()).add(
                                server["Id"]
                            )

        # Create a new set that contains every server ID in the current server list
        current_server_ids = {server["Id"] for server in self.server_list}

        # Update the sent_notifications dictionary to only include server IDs that are still in the server list (removing invalid server IDs due to map change)
        for user, sent_ids in self.sent_notifications.items():
            print(
                f"User {user} has been sent notifications for {len(sent_ids)} servers"
            )

            still_valid_servers = sent_ids & current_server_ids
            invalid_servers = sent_ids - current_server_ids
            self.sent_notifications[user] = still_valid_servers

            if len(invalid_servers) > 0:
                print(
                    f"Cleared notifications for {len(invalid_servers)} servers that changed map for user {user}"
                )

    async def send_notification(self, user: discord.User, server: dict) -> None:
        formatted_server_name = self.format_server_name(server["Name"])
        region_flag = self.get_region_flag(server["Region"])
        queue_str = f"(+{server['QueuePlayers']})" if server["QueuePlayers"] > 0 else ""
        embed = discord.Embed(
            title="Server notification",
            description=f"<@{user.id}>, a server has been found matching your request.",
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
        await user.send(embed=embed, file=file)



    async def fetch_and_notify(self) -> None:
        while True:
            await self.fetch_server_list()
            await self.notify_users()
            await asyncio.sleep(5)


    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        fetch_notify_task = asyncio.create_task(self.fetch_and_notify())
        
        main_dir = os.path.dirname(os.path.abspath(__file__))
        user_filters_path = os.path.join(main_dir, USER_FILTERS_PATH)

        if not os.path.exists(user_filters_path):
            with open(user_filters_path, "w") as f:
                f.write("{}")

        try:
            with open(user_filters_path, "r") as f:
                user_filters_json = json.load(f)
                self.user_filters = {
                    await self.bot.fetch_user(user_id): [Filter.from_json(filter) for filter in filters]
                    for user_id, filters in user_filters_json.items()
                }
                total_filters = sum(len(filters) for filters in self.user_filters.values())
                print(f"Loaded {total_filters} filters for {len(self.user_filters)} users.") 
        except json.JSONDecodeError:
            print(f"Error loading filters from {USER_FILTERS_PATH}. Using empty filters.")
            self.user_filters = {}

        # Check folder "map_icons" exists next to the script, if not create it then download the map icons using https://cdn.gametools.network/maps/battlebit/{map_name}.jpg using gather
        map_icons_dir = os.path.join(main_dir, "map_icons")
        if not os.path.exists(map_icons_dir):
            os.mkdir(map_icons_dir)

        map_icons = [map for map in constants.game_maps if not os.path.exists(os.path.join(map_icons_dir, f"{map}.jpg"))]
        await asyncio.gather(*[self.download_map_icon(map) for map in map_icons])

        await asyncio.gather(fetch_notify_task)

    async def download_map_icon(self, map: str) -> None:
        url = f"https://cdn.gametools.network/maps/battlebit/{map}.jpg"
        async with self.session.get(url) as response:
            if response.status == 200:
                with open(f"map_icons/{map}.jpg", "wb") as f:
                    f.write(await response.read())
            else:
                print(f"Failed to download map icon for {map}")

    def add_filter(self, user: discord.User, filter: Filter) -> None:
        self.user_filters.setdefault(user, []).append(filter)
        
        main_dir = os.path.dirname(os.path.abspath(__file__))
        user_filters_path = os.path.join(main_dir, USER_FILTERS_PATH)

        with open(user_filters_path, "w") as f:
            user_filters = {str(user.id): [filter.to_json() for filter in filters] for user, filters in self.user_filters.items()}
            json.dump(user_filters, f)

    def remove_filter(self, user: discord.User, filter_index: int) -> None:
        if user in self.user_filters:
            if filter_index < len(self.user_filters[user]):
                del self.user_filters[user][filter_index]
        
        main_dir = os.path.dirname(os.path.abspath(__file__))
        user_filters_path = os.path.join(main_dir, USER_FILTERS_PATH)

        with open(user_filters_path, "w") as f:
            user_filters = {str(user.id): [filter.to_json() for filter in filters] for user, filters in self.user_filters.items()}
            json.dump(user_filters, f)

    def get_filters_for_user(self, user: discord.User) -> list[Filter]:
        return self.user_filters.get(user, [])



    def clear_filters(self, user: discord.User) -> None:
        self.user_filters.pop(user, None)


def setup(bot):
    bot.add_cog(Notifier(bot))
