import asyncio
import aiohttp
from discord.ext import commands
import discord
import re
import json
import os

SERVER_LIST_URL = "https://publicapi.battlebit.cloud/Servers/GetServerList"
USER_FILTERS_PATH = "user_filters.json"

class Filter:
    def __init__(
        self,
        min_players: int | None,
        max_players: int | None,
        region: str | None,
        map: str | None,
        game_mode: str | None,
    ):
        self.min_players = min_players
        self.max_players = max_players
        self.region = region
        self.map = map
        self.game_mode = game_mode

    def apply(self, server) -> bool:
        conditions = []
        if self.min_players is not None:
            conditions.append(int(server["Players"]) >= self.min_players)
        if self.max_players is not None:
            conditions.append(int(server["MaxPlayers"]) <= self.max_players)
        if self.region is not None:
            conditions.append(server["Region"] == self.region)
        if self.map is not None:
            conditions.append(server["Map"] == self.map)
        if self.game_mode is not None:
            conditions.append(server["Gamemode"] == self.game_mode)
        return all(conditions)

    def __str__(self) -> str:
        map = self.map if self.map is not None else "Any"
        region = self.region if self.region is not None else "Any"
        min_players = self.min_players if self.min_players is not None else "Any"
        max_players = self.max_players if self.max_players is not None else "Any"
        game_mode = self.game_mode if self.game_mode is not None else "Any"
        return f"Map: {map}, Region: {region}, Min players: {min_players}, Max players: {max_players}, Game mode: {game_mode}"

    def get_embed(self) -> discord.Embed:
        filter_embed = discord.Embed(title="Filter", color=discord.Color.blue())
        map = self.map if self.map is not None else "Any"
        region = self.region if self.region is not None else "Any"
        min_players = self.min_players if self.min_players is not None else "Any"
        max_players = self.max_players if self.max_players is not None else "Any"
        game_mode = self.game_mode if self.game_mode is not None else "Any"
        filter_embed.add_field(
            name="Filters that are currently applied",
            value=f"**Region**: {region}\n**Map**: {map}\n**Min players**: {min_players}\n**Max players**: {max_players}\n**Gamemode**: {game_mode}",
            inline=False,
        )
        return filter_embed
    
    def to_json(self) -> dict:
        return {
            "map": self.map,
            "region": self.region,
            "min_players": self.min_players,
            "max_players": self.max_players,
            "game_mode": self.game_mode
        }
    
    @staticmethod
    def from_json(json):
        return Filter(
            json["min_players"],
            json["max_players"],
            json["region"],
            json["map"],
            json["game_mode"]
        )


class Notifier:
    server_list = []
    bot: commands.Bot = None
    server_message = None
    session: aiohttp.ClientSession = None
    dashboard_channel: discord.TextChannel = None
    server_ids: set[int] = set()
    sent_notifications: dict[discord.User, set[int]] = {}  # user -> set of server ids
    user_filters: dict[discord.User, list[Filter]] = {}
    filter_event = asyncio.Event()

    dashboard_filter = Filter(
        map=None, min_players=None, max_players=None, region=None, game_mode=None
    )

    def __init__(self, bot: discord.Client):
        self.bot = bot

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

    def set_region(self, region: str) -> None:
        self.dashboard_filter.region = None if region == "Any" else region
        self.filter_event.set()

    def set_map(self, map: str) -> None:
        self.dashboard_filter.map = None if map == "Any" else map
        self.filter_event.set()

    def set_min_players(self, min_players: int) -> None:
        self.dashboard_filter.min_players = None if min_players == -1 else min_players
        self.filter_event.set()

    def set_max_players(self, max_players: int) -> None:
        self.dashboard_filter.max_players = None if max_players == -1 else max_players
        self.filter_event.set()

    def set_gamemode(self, game_mode: str) -> None:
        self.dashboard_filter.game_mode = None if game_mode == "Any" else game_mode
        self.filter_event.set()

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
        embed.timestamp = discord.utils.utcnow()
        await user.send(embed=embed)

    async def create_dashboard_embed(self) -> discord.Embed:
        embed = discord.Embed(title="Servers", color=discord.Color.green())
        filtered_servers = [
            server for server in self.server_list if self.dashboard_filter.apply(server)
        ]
        sorted_servers = sorted(
            filtered_servers, key=lambda server: server["Players"], reverse=True
        )
        if len(sorted_servers) == 0:
            embed = discord.Embed(title="No servers found", color=discord.Color.red())

        # Only show the top 20 servers due to Discord's embed field limit
        for server in sorted_servers[:20]:
            formatted_server_name = self.format_server_name(server["Name"])
            region_flag = self.get_region_flag(server["Region"])
            queue_str = (
                f"(+{server['QueuePlayers']})" if server["QueuePlayers"] > 0 else ""
            )
            embed.add_field(
                name=formatted_server_name,
                value=f"**Players**: {server['Players']}{queue_str}/{server['MaxPlayers']}\n**Map**: {server['Map']}\n**Region**: {region_flag}\n**Gamemode**: {server['Gamemode']}",
                inline=False,
            )

        return embed

    async def fetch_and_notify(self) -> None:
        while True:
            await self.fetch_server_list()
            await self.notify_users()
            await asyncio.sleep(5)

    async def update_dashboard(self):
        while True:
            if self.dashboard_channel is not None:
                servers_embed = await self.create_dashboard_embed()
                filters_embed = self.dashboard_filter.get_embed()
                if self.server_message is None:
                    self.server_message = await self.dashboard_channel.send(
                        embeds=[servers_embed, filters_embed]
                    )
                else:
                    try :
                        await self.server_message.edit(
                            embeds=[servers_embed, filters_embed]
                        )
                    except discord.errors.NotFound:
                        self.server_message = await self.dashboard_channel.send(
                            embeds=[servers_embed, filters_embed]
                        )

            try:
                # If a filter has been updated, skip the sleep and update the dashboard immediately for a more responsive experience
                await asyncio.wait_for(self.filter_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                continue

            self.filter_event.clear()

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        fetch_notify_task = asyncio.create_task(self.fetch_and_notify())
        dashboard_task = asyncio.create_task(self.update_dashboard())

        
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

        await asyncio.gather(fetch_notify_task, dashboard_task)

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

    async def set_dashboard_channel(
        self, channel: discord.TextChannel, purge_channel: bool
    ) -> None:
        self.dashboard_channel = channel
        if purge_channel:
            await channel.purge()

        self.filter_event.set()

    def clear_filters(self, user: discord.User) -> None:
        self.user_filters.pop(user, None)
