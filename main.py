import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import logging
from notifier import Notifier
import constants
from notifier import Filter
from discord import app_commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
GUILD = discord.Object(id=GUILD_ID)


class MyClient(discord.Client):
    notifier : Notifier = None
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Copy the global commands to the guild to avoid the 1 hour delay - only do this once if you add new commands
        sync = False
        if sync:
            self.tree.copy_global_to(guild=GUILD)
            await self.tree.sync(guild=GUILD)


intents = discord.Intents.default()
intents.message_content = True
client = MyClient(intents=intents)

@client.event
async def on_ready():
    client.notifier = Notifier(client)
    await client.notifier.start()

@commands.guild_only()
@client.tree.command(
    name="max_players",
    description="Filter for the maximum number of players in a server. -1 for any.",
    guild=GUILD
)

async def set_max_players(interaction: discord.Interaction, max_players: int):
    if not max_players in [8, 16, 32, 64, 128, 254] and max_players != -1:
        await interaction.response.send_message(
            "Invalid max players. Please select from 8, 16, 32, 64, 128, 254, or -1 for any.",
            ephemeral=True,
            delete_after=5,
        )
        return
    
    client.notifier.set_max_players(max_players)
    await interaction.response.send_message(
        f"Set max players to {max_players}.", ephemeral=True, delete_after=5
    )

@commands.guild_only()
@client.tree.command(
    name="min_players",
    description="Filter for the minimum number of players in a server. -1 for any.",
    guild=GUILD
)
async def set_min_players(interaction: discord.Interaction, min_players: int):
    if not (min_players >= 0 and min_players <= 254) and min_players != -1:
        await interaction.response.send_message(
            "Invalid min players. Please select a number between 0 and 254, or -1 for any.",
            ephemeral=True,
            delete_after=5,
        )
        return
    client.notifier.set_min_players(min_players)
    await interaction.response.send_message(
        f"Set min players to {min_players}.", ephemeral=True, delete_after=5
    )

@commands.guild_only()
@client.tree.command(
    name="region", description=f"Set a filter for the region of a server.",
    guild=GUILD
)
async def set_region(interaction: discord.Interaction):
    options = [
        discord.SelectOption(label=region, value=region) for region in constants.regions
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        region = select.values[0]
        client.notifier.set_region(region)
        await interaction.response.edit_message(content=f"Set region to {region}.", view=None, delete_after=5)

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a region:", view=view, ephemeral=True, delete_after=60
    )

@commands.guild_only()
@client.tree.command(name="map", description=f"Set a filter for the map of a server.", guild=GUILD)
async def set_map(interaction: discord.Interaction):
    options = [
        discord.SelectOption(label=map, value=map) for map in constants.game_maps
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        map = select.values[0]
        client.notifier.set_map(map)
        await interaction.response.edit_message(content=f"Set map to {map}.", view=None, delete_after=5)

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a map:", view=view, ephemeral=True, delete_after=60
    )

@commands.guild_only()
@client.tree.command(
    name="dashboard_channel", description=f"Set the channel for the dashboard.", guild=GUILD
)
async def set_dashboard_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    purge_channel: bool = False,
):
    await client.notifier.set_dashboard_channel(channel, purge_channel)
    await interaction.response.send_message(
        f"Set dashboard channel to {channel.mention}.", ephemeral=True, delete_after=5
    )


@commands.guild_only()
@client.tree.command(
    name="start_notify",
    description=f"Get notified when a server matches the specified filters.", guild=GUILD
)
async def start_notify(interaction: discord.Interaction, map : str, region : str | None, min_players : int | None, max_players : int | None, gamemode : str | None):

    client.notifier.add_filter(interaction.user, Filter(min_players=min_players, max_players=max_players, map=map, region=region, game_mode=gamemode))
    await interaction.response.send_message(
        f"Filter has been added.", ephemeral=True, delete_after=5
    )

@commands.guild_only()
@client.tree.command(
    name="stop_notify",
    description=f"Stop getting notified for the specified filter.", guild=GUILD
)
async def stop_notify(interaction: discord.Interaction, filter_index : int):
    client.notifier.remove_filter(interaction.user, filter_index)
    await interaction.response.send_message(
        f"Filter has been removed.", ephemeral=True, delete_after=5
    )

@commands.guild_only()
@client.tree.command(
    name="list_filters",
    description=f"List all notification filters.", guild=GUILD
)
async def list_filters(interaction: discord.Interaction):
    filters = client.notifier.get_filters_for_user(interaction.user)
    if not filters:
        await interaction.response.send_message(
            f"No filters set.", ephemeral=True, delete_after=5
        )
        return
    filters_str = "\n".join([f"{i}: {filter}" for i, filter in enumerate(filters)])
    await interaction.response.send_message(
        f"Filters:\n{filters_str}", ephemeral=True, delete_after=30
    )

@commands.guild_only()
@client.tree.command(
    name="clear_filters",
    description=f"Clear all notification filters.", guild=GUILD
)
async def clear_filters(interaction: discord.Interaction):
    client.notifier.clear_filters(interaction.user)
    await interaction.response.send_message(
        f"Filters have been cleared.", ephemeral=True, delete_after=5
    )

@commands.guild_only()
@client.tree.command(
    name="gamemode",
    description=f"Set a filter for the gamemode of a server.", guild=GUILD
)
async def gamemode(interaction: discord.Interaction):
    options = [
        discord.SelectOption(label=mode, value=mode) for mode in constants.gamemodes
    ]
    select = discord.ui.Select(options=options)

    async def select_callback(interaction: discord.Interaction):
        mode = select.values[0]
        client.notifier.set_gamemode(mode)
        await interaction.response.edit_message(content=f"Set gamemode to {mode}.", view=None, delete_after=5)

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message(
        "Please select a gamemode:", view=view, ephemeral=True, delete_after=60
    )


client.run(TOKEN, log_level=logging.DEBUG)
