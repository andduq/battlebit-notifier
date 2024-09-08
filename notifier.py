import asyncio
import aiohttp
from discord.ext import commands
import discord
import re

SERVER_LIST_URL = "https://publicapi.battlebit.cloud/Servers/GetServerList"


class Notifier:
    refresh_interval = 5
    notification_channel_id: int | None = None
    server_list = []
    subscribers: list[int] = []
    bot: commands.Bot = None
    servers_to_track = {}
    server_message = None
    desired_max_players = 254
    desired_min_players = 100
    desired_region = "Any"
    desired_map = "Any"
    session: aiohttp.ClientSession = None
    channel: discord.TextChannel = None
    users_to_notify: dict[str, list[discord.User]] = {}
    notified_users: dict[str, dict[str, set[discord.User]]] = {}

    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def fetch_server_list(self):
        async with self.session.get(SERVER_LIST_URL) as response:
            self.server_list = await response.json(
                content_type=None, encoding="utf-8-sig"
            )

    def set_region(self, region: str):
        if region == "Any":
            self.desired_region = "Any"
            return

        self.desired_region = region

    def format_server_name(self, string):
        url_pattern = re.compile(r"((https?:\/\/)?[^\s.]+\.[\w][^\s]+)")
        return url_pattern.sub(r"\<\g<1>\>", string)

    def get_region_flag(self, region):
        region_flags = {
            "America_Central": ":flag_us:",
            "Europe_Central": ":flag_eu:",
            "Asia_Central": ":flag_white:",
            "Brazil_Central": ":flag_br:",
            "Australia_Central": ":flag_au:",
            "Japan_Central": ":flag_jp:",
        }
        return region_flags.get(region, "")

    async def process_server_list(self):
        self.servers_to_track = {server["Name"]: server for server in self.server_list}

        filters = {
            "Map": self.desired_map,
            "Region": self.desired_region,
            "MaxPlayers": self.desired_max_players,
            "Players": self.desired_min_players,
        }

        for key, value in filters.items():
            if value != "Any" and value != -1:
                self.servers_to_track = self.apply_filter(key, value)

        if self.users_to_notify:
            new_servers = {
                name: server
                for name, server in self.servers_to_track.items()
                if name not in self.notified_users
            }
            for server_name, server in new_servers.items():
                map_lower = server["Map"]
                if map_lower in self.users_to_notify:
                    users_to_notify = [
                        user
                        for user in self.users_to_notify[map_lower]
                        if user
                        not in self.notified_users.get(server_name, {}).get(
                            map_lower, set()
                        )
                    ]
                    for user in users_to_notify:
                        formatted_server_name = self.format_server_name(server_name)
                        region_flag = self.get_region_flag(server["Region"])
                        queue_str = (
                            f"(+{server['QueuePlayers']})"
                            if server["QueuePlayers"] > 0
                            else ""
                        )
                        embed = discord.Embed(
                            title="Server notification",
                            description="A server has been found matching your request.",
                            color=discord.Color.yellow(),
                        )
                        embed.add_field(
                            name=formatted_server_name,
                            value=f"**Players**: {server['Players']}{queue_str}/{server['MaxPlayers']}\n**Map**: {server['Map']}\n**Region**: {region_flag}",
                            inline=False,
                        )
                        embed.timestamp = discord.utils.utcnow()
                        await user.send(embed=embed)
                    self.notified_users.setdefault(server_name, {}).setdefault(
                        map_lower, set()
                    ).update(users_to_notify)

            for server_name, server in self.servers_to_track.items():
                if (
                    server_name in self.notified_users
                    and server["Map"] not in self.notified_users[server_name]
                ):
                    self.notified_users[server_name].clear()

    def apply_filter(self, key, value):
        if key == "MaxPlayers" or key == "Players":
            value = int(value)
            return {
                name: server
                for name, server in self.servers_to_track.items()
                if server[key] >= value
            }
        else:
            return {
                name: server
                for name, server in self.servers_to_track.items()
                if server[key] == value
            }

    async def create_server_message(self):
        embed = discord.Embed(title="Servers", color=discord.Color.green())
        sorted_servers = sorted(
            self.servers_to_track.items(), key=lambda x: x[1]["Players"], reverse=True
        )
        if len(sorted_servers) == 0:
            embed = discord.Embed(title="No servers found", color=discord.Color.red())

        for server_name, server in sorted_servers:
            formatted_server_name = self.format_server_name(server_name)
            region_flag = self.get_region_flag(server["Region"])
            queue_str = (
                f"(+{server['QueuePlayers']})" if server["QueuePlayers"] > 0 else ""
            )
            embed.add_field(
                name=formatted_server_name,
                value=f"    **Players**: {server['Players']}{queue_str}/{server['MaxPlayers']}\n    **Map**: {server['Map']}\n    **Region**: {region_flag}",
                inline=False,
            )

        return embed

    async def start(self):
        self.session = aiohttp.ClientSession()
        while True:
            if self.channel is not None:
                await self.fetch_server_list()
                await self.process_server_list()
                servers_embed = await self.create_server_message()
                filters_embed = discord.Embed(
                    title="Server filters", color=discord.Color.blue()
                )
                filters_embed.add_field(
                    name="Filters that are currently applied",
                    value=f"**Region**: {self.desired_region}\n**Map**: {self.desired_map}\n**Min players**: {self.desired_min_players}\n**Max players**: {self.desired_max_players}",
                    inline=False,
                )
                if self.server_message is None:
                    self.server_message = await self.channel.send(
                        embeds=[servers_embed, filters_embed]
                    )
                else:
                    await self.server_message.edit(
                        embeds=[servers_embed, filters_embed]
                    )
                await asyncio.sleep(self.refresh_interval)
            else:
                await asyncio.sleep(1)

    def add_notification(self, user: discord.User, map: str):
        if map not in self.users_to_notify:
            self.users_to_notify[map] = []
        self.users_to_notify[map].append(user)

    def remove_notification(self, user: discord.User, map: str):
        if map in self.users_to_notify:
            self.users_to_notify[map].remove(user)
            if len(self.users_to_notify[map]) == 0:
                del self.users_to_notify[map]

        servers_to_remove = []
        for server_name, server_maps in self.notified_users.items():
            if map in server_maps:
                server_maps[map].remove(user)
                if len(server_maps[map]) == 0:
                    del server_maps[map]
                if len(server_maps) == 0:
                    servers_to_remove.append(server_name)

        for server_name in servers_to_remove:
            del self.notified_users[server_name]

    async def set_channel(self, channel: discord.TextChannel, purge_channel: bool):
        self.channel = channel
        if purge_channel:
            await channel.purge()

    def get_notified_maps(self, user: discord.User):
        return [map for map, users in self.users_to_notify.items() if user in users]
